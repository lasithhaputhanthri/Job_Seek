"""
Unified AI Agent Engine with Provenance, Token Accounting, and Quota-Aware Routing.
Provides centralized LLM interfaces with retry + jitter, response validation,
and startup health checks.
"""

import json
import logging
import os
import random
import threading
import time
from typing import Any, Dict, Optional, Tuple, Type, TypeVar
from pydantic import BaseModel
from dotenv import load_dotenv

from src.config import config

load_dotenv()
logger = logging.getLogger("AIEngine")
T = TypeVar("T", bound=BaseModel)


class AIEngine:
    """Centralized LLM provider powering all agents."""

    def __init__(self):
        self.gemini_key = config.GEMINI_API_KEY
        self.openai_key = config.OPENAI_API_KEY
        self.ollama_endpoint = config.OLLAMA_ENDPOINT

        self.gemini_client = None
        self.provider_name = "Semantic Reasoning Engine"
        self.is_live = False

        self.fast_model = config.GEMINI_MODEL
        self.pro_model = config.GEMINI_PRO_MODEL

        # Thread-safe Rate Limiting & Quota Management (15 RPM = 4.0s minimum spacing between calls)
        self._rate_limit_lock = threading.Lock()
        self._last_call_time = 0.0
        self._min_call_interval = config.LLM_MIN_CALL_INTERVAL
        self.daily_quota_exhausted = False

        # Telemetry & Token Tracking
        self.total_llm_calls = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost_usd = 0.0
        self.last_provenance: Dict[str, Any] = {
            "engine": "RULE_BASED",
            "model": "semantic-rules",
            "prompt_version": config.PROMPT_VERSION,
            "input_tokens": 0,
            "output_tokens": 0,
        }

        if self.gemini_key:
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=self.gemini_key)
                self.provider_name = f"Google Gemini Live AI ({self.fast_model})"
                self.is_live = True
            except Exception as e:
                logger.warning(f"[AIEngine] Gemini SDK initialization warning: {e}")

        elif self.openai_key:
            self.provider_name = f"OpenAI ({config.OPENAI_MODEL})"
            self.is_live = True

        elif self.ollama_endpoint:
            self.provider_name = f"Local Ollama ({self.ollama_endpoint})"
            self.is_live = True

    def health_check(self, require_live: bool = False) -> Tuple[bool, str]:
        """
        Validates LLM connectivity and configured model IDs.
        Fails fast if require_live is True and API is unavailable.
        """
        if not self.is_live:
            msg = "No live LLM API key configured (using Built-in Semantic Reasoning Engine)."
            if require_live:
                raise RuntimeError(
                    f"LLM Health Check Failed: {msg}\n"
                    "Please set GEMINI_API_KEY in .env or run with offline/mock flags."
                )
            return (True, msg)

        if self.gemini_client:
            try:
                # Minimal test call to verify model availability
                resp = self.gemini_client.models.generate_content(
                    model=self.fast_model,
                    contents="Ping. Respond with 'PONG'.",
                )
                if resp and resp.text:
                    return (True, f"Gemini connection verified with model '{self.fast_model}'.")
            except Exception as e:
                err_msg = (
                    f"Gemini API Health Check Failed for model '{self.fast_model}': {e}\n"
                    "Action Required:\n"
                    "1. Verify GEMINI_API_KEY in .env is valid and has quota.\n"
                    "2. Verify GEMINI_MODEL / GEMINI_PRO_MODEL in .env (recommended: 'gemini-3.5-flash')."
                )
                if require_live:
                    raise RuntimeError(err_msg)
                print(f"[AIEngine WARNING] {err_msg}")
                return (False, err_msg)

        return (True, f"Active provider: {self.provider_name}")

    def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        max_retries: int = 3,
    ) -> Optional[T]:
        """
        Executes structured prompt with retry + jitter, response validation,
        and token counting.
        """
        chosen_model = model or self.fast_model

        if self.gemini_client:
            return self._call_gemini_with_retry(
                prompt=prompt,
                response_schema=response_schema,
                system_instruction=system_instruction,
                model=chosen_model,
                max_retries=max_retries,
            )

        if self.openai_key:
            return self._call_openai_structured(
                prompt=prompt,
                response_schema=response_schema,
                system_instruction=system_instruction,
            )

        # Fallback to None if no live provider
        return None

    def _call_gemini_with_retry(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: Optional[str],
        model: str,
        max_retries: int,
    ) -> Optional[T]:
        """Executes Gemini structured completion with exponential backoff and jitter."""
        from google.genai import types

        cfg = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_schema,
            temperature=0.0,
            system_instruction=system_instruction,
        )

        if self.daily_quota_exhausted:
            return None

        active_model = model
        for attempt in range(1, max_retries + 1):
            try:
                # Thread-safe rate limiter: enforce minimum spacing between calls (15 RPM)
                with self._rate_limit_lock:
                    now = time.time()
                    elapsed = now - self._last_call_time
                    if elapsed < self._min_call_interval:
                        time.sleep(self._min_call_interval - elapsed)
                    self._last_call_time = time.time()

                self.total_llm_calls += 1
                resp = self.gemini_client.models.generate_content(
                    model=active_model,
                    contents=prompt,
                    config=cfg,
                )

                # Token Accounting
                in_tok = getattr(resp.usage_metadata, "prompt_token_count", 0) if resp.usage_metadata else 0
                out_tok = getattr(resp.usage_metadata, "candidates_token_count", 0) if resp.usage_metadata else 0
                self.total_input_tokens += in_tok
                self.total_output_tokens += out_tok

                # Cost estimate (standard rates ~$0.075 / 1M input, $0.30 / 1M output)
                est_cost = (in_tok * 0.000000075) + (out_tok * 0.00000030)
                self.total_cost_usd += est_cost

                self.last_provenance = {
                    "engine": "GEMINI_LIVE",
                    "model": active_model,
                    "prompt_version": config.PROMPT_VERSION,
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "cost_usd": est_cost,
                }

                data = json.loads(resp.text)
                return response_schema(**data)

            except Exception as e:
                err_str = str(e)

                # Check if Daily Quota (RPD) is reached
                if "per day limit exceeded" in err_str.lower() or "perday" in err_str.lower():
                    logger.warning(
                        "[AIEngine] Daily Free Tier quota (RPD) reached for Gemini API. "
                        "Seamlessly routing all remaining evaluations to Built-in Semantic Reasoning Engine."
                    )
                    self.daily_quota_exhausted = True
                    return None

                is_transient = any(code in err_str for code in ["429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE"])

                if is_transient and attempt < max_retries:
                    # Switch to alternate lite model (both support 500 RPD on free tier)
                    if active_model == "gemini-3.1-flash-lite":
                        active_model = "gemini-3.5-flash-lite"
                    else:
                        active_model = "gemini-3.1-flash-lite"
                    self.fast_model = active_model
                    self.pro_model = active_model
                    backoff = (1.5 ** attempt) + random.uniform(0.5, 1.5)
                    logger.warning(
                        f"[AIEngine] Transient LLM notice ({'429/RPM' if '429' in err_str else '503/Busy'}) on attempt {attempt}/{max_retries}. "
                        f"Switched model to '{active_model}'. Backing off for {backoff:.2f}s..."
                    )
                    time.sleep(backoff)
                    continue

                logger.warning(f"[AIEngine] LLM structured call error (attempt {attempt}/{max_retries}): {e}")
                if attempt == max_retries:
                    self.last_provenance = {
                        "engine": "FALLBACK_RULES",
                        "model": "semantic-rules",
                        "prompt_version": config.PROMPT_VERSION,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cost_usd": 0.0,
                    }
                    return None

        return None

    def _call_openai_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: Optional[str],
    ) -> Optional[T]:
        """Executes structured completion via OpenAI API."""
        try:
            import httpx

            headers = {
                "Authorization": f"Bearer {self.openai_key}",
                "Content-Type": "application/json",
            }
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": config.OPENAI_MODEL,
                "messages": messages,
                "response_format": {"type": "json_object"},
                "temperature": 0.0,
            }

            with httpx.Client(timeout=config.HTTP_TIMEOUT) as client:
                resp = client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    return response_schema(**parsed)
        except Exception as e:
            logger.warning(f"[AIEngine] OpenAI structured call error: {e}")
        return None


ai_engine = AIEngine()
