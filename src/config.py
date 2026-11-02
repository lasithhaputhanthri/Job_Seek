"""
Centralized Configuration Module for Job_Seek.
Driven strictly by environment variables with safe defaults.
Contains all model names, thresholds, rate limits, timeouts, and system constants.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv

# Load .env without echoing secrets
load_dotenv()


class SystemConfig:
    # ---------------------------------------------------------
    # System Version & Prompts
    # ---------------------------------------------------------
    PROMPT_VERSION: str = "2.0.0"
    SYSTEM_NAME: str = "JobSeekBot"
    SYSTEM_VERSION: str = "2.0.0"

    # ---------------------------------------------------------
    # LLM Providers & Model Settings
    # ---------------------------------------------------------
    GEMINI_API_KEY: Optional[str] = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    # Defaulting to active Google Gemini model IDs from active API catalog
    # gemini-3.1-flash-lite provides high RPM and zero 429 rate-limiting on free tier
    GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
    GEMINI_PRO_MODEL: str = os.environ.get("GEMINI_PRO_MODEL", "gemini-3.1-flash-lite")

    OPENAI_API_KEY: Optional[str] = os.environ.get("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.environ.get("OPENAI_MODEL", "gpt-4o")

    OLLAMA_ENDPOINT: Optional[str] = os.environ.get("OLLAMA_ENDPOINT")

    # ---------------------------------------------------------
    # Scoring & Verification Thresholds
    # ---------------------------------------------------------
    # Single canonical relevance threshold: computed in code, not trusted from LLM
    MIN_RELEVANCE_SCORE: int = int(os.environ.get("MIN_RELEVANCE_SCORE", "50"))
    # Caps on missing evidence / weak descriptions
    MAX_SCORE_NO_DESCRIPTION: int = int(os.environ.get("MAX_SCORE_NO_DESCRIPTION", "60"))
    MAX_SCORE_NO_MUST_HAVE: int = int(os.environ.get("MAX_SCORE_NO_MUST_HAVE", "40"))

    # Adversarial verification thresholds
    SAMPLE_AUDIT_RATE: float = float(os.environ.get("SAMPLE_AUDIT_RATE", "0.20"))
    BORDERLINE_SCORE_LOW: int = int(os.environ.get("BORDERLINE_SCORE_LOW", "45"))
    BORDERLINE_SCORE_HIGH: int = int(os.environ.get("BORDERLINE_SCORE_HIGH", "65"))

    # Quality gates
    PRECISION_TARGET: float = float(os.environ.get("PRECISION_TARGET", "0.85"))
    DEAD_LINK_MAX: float = float(os.environ.get("DEAD_LINK_MAX", "0.05"))
    HUMAN_REVIEW_SAMPLE_SIZE: int = int(os.environ.get("HUMAN_REVIEW_SAMPLE_SIZE", "20"))

    # ---------------------------------------------------------
    # Concurrency, Budgets & Rate Limits
    # ---------------------------------------------------------
    GLOBAL_CONCURRENCY: int = int(os.environ.get("GLOBAL_CONCURRENCY", "8"))
    PER_HOST_CONCURRENCY: int = int(os.environ.get("PER_HOST_CONCURRENCY", "2"))
    PER_HOST_DELAY: float = float(os.environ.get("PER_HOST_DELAY", "0.5"))
    LLM_MIN_CALL_INTERVAL: float = float(os.environ.get("LLM_MIN_CALL_INTERVAL", "4.0"))

    MAX_LLM_CALLS: int = int(os.environ.get("MAX_LLM_CALLS", "500"))
    MAX_TOKENS: int = int(os.environ.get("MAX_TOKENS", "1000000"))
    MAX_RUNTIME_SECONDS: int = int(os.environ.get("MAX_RUNTIME_SECONDS", "3600"))
    MAX_HTTP_REQUESTS: int = int(os.environ.get("MAX_HTTP_REQUESTS", "5000"))
    MAX_CONSECUTIVE_EMPTY_BATCHES: int = int(os.environ.get("MAX_CONSECUTIVE_EMPTY_BATCHES", "3"))

    HTTP_TIMEOUT: float = float(os.environ.get("HTTP_TIMEOUT", "12.0"))
    USER_AGENT: str = os.environ.get(
        "USER_AGENT",
        "JobSeekBot/1.0 (+https://github.com/example/job_seek; legitimate-career-scout)"
    )

    # ---------------------------------------------------------
    # Filesystem & Database Paths
    # ---------------------------------------------------------
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DEFAULT_DB_PATH: Path = BASE_DIR / "data" / "job_hunter.db"
    BACKUP_DIR: Path = BASE_DIR / "data" / "backups"
    DEFAULT_PROFILE_PATH: Path = BASE_DIR / "data" / "profile.json"
    DEFAULT_TAXONOMY_PATH: Path = BASE_DIR / "data" / "taxonomy.json"
    DEFAULT_EXPORT_PATH: Path = BASE_DIR / "data" / "exports" / "job_hunt_results.xlsx"
    ARCHIVE_EXPORT_DIR: Path = BASE_DIR / "data" / "exports" / "archive"

    # ---------------------------------------------------------
    # Safety Check: Never log or expose secrets
    # ---------------------------------------------------------
    @classmethod
    def get_safe_summary(cls) -> Dict[str, Any]:
        """Returns non-sensitive configuration values safe for logging and reports."""
        return {
            "gemini_live": bool(cls.GEMINI_API_KEY),
            "gemini_model": cls.GEMINI_MODEL,
            "gemini_pro_model": cls.GEMINI_PRO_MODEL,
            "min_relevance_score": cls.MIN_RELEVANCE_SCORE,
            "sample_audit_rate": cls.SAMPLE_AUDIT_RATE,
            "precision_target": cls.PRECISION_TARGET,
            "dead_link_max": cls.DEAD_LINK_MAX,
            "global_concurrency": cls.GLOBAL_CONCURRENCY,
            "per_host_concurrency": cls.PER_HOST_CONCURRENCY,
            "max_llm_calls": cls.MAX_LLM_CALLS,
            "prompt_version": cls.PROMPT_VERSION,
        }


config = SystemConfig()
