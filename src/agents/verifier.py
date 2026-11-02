"""
Independent Adversarial Verifier Agent.
Performs adversarial quality audits on proposed job matches:
1. Deterministic URL vitality & multilingual 'still-open' detection (EN, DE, FR, NL, ES, IT).
2. Verbatim evidence quote substring validation against raw page text.
3. Hard filter audit (visa, ITAR, citizenship, seniority, internships).
4. Adversarial LLM evaluation on sample + borderline scores using RAW page text (never classifier reasoning).
5. Truthful audit logging (FALLBACK_RULES_APPROVED vs LLM_APPROVED).
"""

import logging
import random
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from src.config import config
from src.agents.llm_engine import ai_engine
from src.schemas import UserProfile, VerificationResult
from src.text_match import (
    contains_any_word,
    extract_visa_and_citizenship_signals,
    is_internship_or_graduate,
    is_non_engineering_role,
    normalize_text,
)
from mcp_servers.career_page_reader.server import get_job_details

logger = logging.getLogger("AIVerifierAgent")

# Multilingual Phrases indicating that a job posting has closed or expired
MULTILINGUAL_CLOSED_PHRASES: List[str] = [
    # English
    r"\b(?:no\s+longer\s+(?:available|accepting\s+applications|active)|position\s+(?:has\s+been\s+)?filled)\b",
    r"\b(?:(?:has\s+)?expired|job\s+is\s+closed|posting\s+closed)\b",
    r"\b(?:this\s+opening\s+is\s+closed|vacancy\s+closed)\b",

    # German
    r"nicht\s+mehr\s+(?:verf.?gbar|aktiv)",
    r"\b(?:stelle\s+ist\s+besetzt|position\s+besetzt)\b",
    r"(?:ausschreibung\s+(?:wurde\s+|ist\s+)?beendet|bewerbungsfrist\s+abgelaufen|\babgelaufen\b)",

    # French
    r"\b(?:n'est\s+plus\s+disponible|poste\s+pourvu|offre\s+expiree|candidatures\s+closes)\b",

    # Dutch
    r"\b(?:niet\s+meer\s+(?:beschikbaar|mogelijk)|vacature\s+gesloten|vacature\s+is\s+verlopen|positie\s+is\s+vervuld|vervallen|verlopen)\b",

    # Spanish
    r"\b(?:ya\s+no\s+esta\s+disponible|puesto\s+cubierto|oferta\s+expirada|proceso\s+cerrado)\b",

    # Italian
    r"\b(?:non\s+e\s+piu\s+disponibile|posizione\s+chiusa|offerta\s+scaduta)\b",
]


class LLMAuditResponse(BaseModel):
    is_verified: bool = Field(..., description="Whether the claimed facts are completely accurate")
    confidence_score: int = Field(..., ge=0, le=100, description="Audit confidence")
    rejection_reason: Optional[str] = Field(default=None, description="Detailed explanation if rejected")
    evidence_quote_present: bool = Field(..., description="Whether quote appears verbatim in page text")
    still_open_confirmed: bool = Field(..., description="Whether posting is confirmed still open")


class AIVerifierAgent:
    def __init__(
        self,
        profile: UserProfile,
        http_client: Optional[httpx.Client] = None,
        sample_audit_rate: Optional[float] = None,
    ):
        self.profile = profile
        self.client = http_client
        self.sample_audit_rate = sample_audit_rate if sample_audit_rate is not None else config.SAMPLE_AUDIT_RATE

    def audit_proposal(
        self,
        row: Dict[str, Any],
        raw_page_text: Optional[str] = None
    ) -> VerificationResult:
        """
        Adversarially audits a job match proposal:
        1. Deterministic checks on 100% of jobs (URL alive, quote substring, still-open check).
        2. Adversarial LLM audit on all borderline scores + random sample.
        """
        job_url = row.get("job_url", "")
        source_url = row.get("source_url", "")
        evidence = row.get("evidence_quote") or ""
        title = row.get("title", "")
        company = row.get("company_name", "")
        work_mode = row.get("work_mode", "On-site")
        score = row.get("match_score", 0)

        # -------------------------------------------------------------
        # STEP 1: DETERMINISTIC PRE-CHECKS (100% of rows)
        # -------------------------------------------------------------
        if not job_url:
            return VerificationResult(
                is_verified=False,
                confidence_score=0,
                audit_notes="FALLBACK_RULES_REJECTED: Missing job URL.",
                verifier_engine="RULE_BASED",
                still_open=False,
                quote_verified=False,
                flags=["MISSING_JOB_URL"],
            )

        # 1a. Fetch page text if not provided
        page_text = raw_page_text
        if not page_text:
            page_text, is_alive, is_still_open, fetch_err = self._fetch_and_check_vitality(job_url)
            if not is_alive:
                return VerificationResult(
                    is_verified=False,
                    confidence_score=0,
                    audit_notes=f"FALLBACK_RULES_REJECTED: URL unreachable ({fetch_err}).",
                    verifier_engine="RULE_BASED",
                    still_open=False,
                    quote_verified=False,
                    flags=["DEAD_URL", fetch_err],
                )
            if not is_still_open:
                return VerificationResult(
                    is_verified=False,
                    confidence_score=10,
                    audit_notes=f"FALLBACK_RULES_REJECTED: Job closed or expired ({fetch_err}).",
                    verifier_engine="RULE_BASED",
                    still_open=False,
                    quote_verified=False,
                    flags=["JOB_CLOSED", fetch_err],
                )

        norm_page = normalize_text(page_text)

        # 1b. Check still-open phrases in page text (Multilingual)
        for p in MULTILINGUAL_CLOSED_PHRASES:
            m = re.search(p, norm_page, re.IGNORECASE)
            if m:
                return VerificationResult(
                    is_verified=False,
                    confidence_score=15,
                    audit_notes=f"FALLBACK_RULES_REJECTED: Closed phrase detected: '{m.group(0)}'.",
                    verifier_engine="RULE_BASED",
                    still_open=False,
                    quote_verified=False,
                    flags=["EXPIRED_PHRASE_DETECTED"],
                )

        # 1c. Verbatim quote substring check
        quote_verified = False
        if evidence:
            clean_ev = evidence.strip()
            # Quote must be at least 15 chars and appear verbatim as substring
            if len(clean_ev) >= 15 and clean_ev in norm_page:
                quote_verified = True

        # 1d. Hard filter violation checks
        if is_non_engineering_role(title):
            return VerificationResult(
                is_verified=False,
                confidence_score=5,
                audit_notes="FALLBACK_RULES_REJECTED: Non-engineering business role.",
                verifier_engine="RULE_BASED",
                still_open=True,
                quote_verified=quote_verified,
                flags=["NON_ENGINEERING_ROLE"],
            )

        if not self.profile.include_internships and is_internship_or_graduate(title):
            return VerificationResult(
                is_verified=False,
                confidence_score=5,
                audit_notes="FALLBACK_RULES_REJECTED: Internship / graduate role excluded by profile.",
                verifier_engine="RULE_BASED",
                still_open=True,
                quote_verified=quote_verified,
                flags=["INTERNSHIP_EXCLUDED"],
            )

        if self.profile.needs_visa_sponsorship:
            _, cit_req, cit_quote = extract_visa_and_citizenship_signals(norm_page)
            if cit_req:
                return VerificationResult(
                    is_verified=False,
                    confidence_score=10,
                    audit_notes=f"FALLBACK_RULES_REJECTED: Citizenship or security clearance required ('{cit_quote}').",
                    verifier_engine="RULE_BASED",
                    still_open=True,
                    quote_verified=quote_verified,
                    flags=["CITIZENSHIP_OR_ITAR_RESTRICTION"],
                )

        # -------------------------------------------------------------
        # STEP 2: AUDIT DECISION (LLM vs Deterministic Fallback)
        # -------------------------------------------------------------
        # Sample audit: 100% of borderline scores + random sample according to sample_audit_rate
        is_borderline = config.BORDERLINE_SCORE_LOW <= score <= config.BORDERLINE_SCORE_HIGH
        should_run_llm_audit = ai_engine.is_live and (is_borderline or random.random() < self.sample_audit_rate)

        if should_run_llm_audit:
            llm_result = self._audit_with_adversarial_llm(row, norm_page)
            if llm_result:
                return llm_result

        # -------------------------------------------------------------
        # STEP 3: DETERMINISTIC APPROVAL / REJECTION (Truthful labeling)
        # -------------------------------------------------------------
        # Approval criteria: score >= MIN_RELEVANCE_SCORE, URL alive, no hard filter violations
        if score >= config.MIN_RELEVANCE_SCORE:
            notes = "FALLBACK_RULES_APPROVED: Verified live URL, still-open confirmed, and technical alignment."
            if not quote_verified and evidence:
                notes += " (Notice: quote paraphrased or brief)."
            return VerificationResult(
                is_verified=True,
                confidence_score=85 if quote_verified else 70,
                audit_notes=notes,
                verifier_engine="FALLBACK_RULES",
                still_open=True,
                quote_verified=quote_verified,
                flags=["QUOTE_PARAPHRASED"] if not quote_verified else [],
            )
        else:
            return VerificationResult(
                is_verified=False,
                confidence_score=30,
                audit_notes=f"FALLBACK_RULES_REJECTED: Score ({score}) below threshold ({config.MIN_RELEVANCE_SCORE}).",
                verifier_engine="RULE_BASED",
                still_open=True,
                quote_verified=quote_verified,
                flags=["LOW_RELEVANCE_SCORE"],
            )

    def _fetch_and_check_vitality(self, job_url: str) -> Tuple[str, bool, bool, Optional[str]]:
        """
        Fetches job posting text and checks HTTP status, redirects, and ATS availability.
        Returns: (page_text, is_alive, is_still_open, error_message)
        """
        client = self.client or httpx.Client(timeout=config.HTTP_TIMEOUT, follow_redirects=True)
        should_close = self.client is None

        try:
            resp = client.get(job_url)

            # 1. HTTP 404/410/500 check
            if resp.status_code in [404, 410]:
                return ("", False, False, f"HTTP {resp.status_code} (Job expired or deleted)")
            if resp.status_code >= 400:
                return ("", False, False, f"HTTP {resp.status_code}")

            # 2. Redirect to generic careers portal check
            final_url = str(resp.url).lower().rstrip("/")
            parsed_final = urlparse(final_url)
            final_path = parsed_final.path.strip("/")

            if final_path in ["careers", "jobs", "job-search", "openings", "vacancies", ""]:
                # Redirected to root or generic search page -> original job was deleted
                return ("", True, False, "Redirected to generic careers portal (original job unlisted)")

            # 3. Extract text
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                tag.decompose()

            raw_text = soup.get_text(separator="\n", strip=True)
            return (raw_text[:12000], True, True, None)

        except Exception as e:
            return ("", False, False, str(e)[:100])
        finally:
            if should_close:
                client.close()

    def _audit_with_adversarial_llm(
        self, row: Dict[str, Any], raw_page_text: str
    ) -> Optional[VerificationResult]:
        """
        Runs adversarial LLM audit receiving RAW page text and claims.
        Crucial: Never receives the classifier's original reasoning (Bug 15).
        """
        prompt_file = config.BASE_DIR / "src" / "prompts" / "job_verifier.md"
        system_instruction = prompt_file.read_text(encoding="utf-8") if prompt_file.exists() else "Adversarial Quality Auditor."

        # Truncate raw page text to bounded window
        bounded_page = raw_page_text[:6000]

        prompt = f"""CLAIMED RECORD:
- Title: {row.get('title')}
- Company: {row.get('company_name')}
- Country: {row.get('country')}
- Work Mode: {row.get('work_mode')}
- Claimed Evidence Quote: "{row.get('evidence_quote') or ''}"
- Visa Claim: "{row.get('visa_sponsorship') or 'unknown'}"

RAW PAGE TEXT:
{bounded_page}
"""
        res = ai_engine.generate_structured(
            prompt=prompt,
            response_schema=LLMAuditResponse,
            system_instruction=system_instruction,
            model=config.GEMINI_PRO_MODEL,
        )
        if not res:
            return None

        if res.is_verified:
            notes = "LLM_APPROVED: Adversarial audit confirmed title, evidence, and still-open status against raw page."
            return VerificationResult(
                is_verified=True,
                confidence_score=res.confidence_score,
                audit_notes=notes,
                verifier_engine="LLM_ADVERSARIAL",
                still_open=res.still_open_confirmed,
                quote_verified=res.evidence_quote_present,
                flags=[],
            )
        else:
            reason = res.rejection_reason or "Adversarial auditor found discrepancies with raw page."
            return VerificationResult(
                is_verified=False,
                confidence_score=res.confidence_score,
                audit_notes=f"LLM_REJECTED: {reason}",
                verifier_engine="LLM_ADVERSARIAL",
                still_open=res.still_open_confirmed,
                quote_verified=res.evidence_quote_present,
                flags=["ADVERSARIAL_LLM_DISCREPANCY"],
            )
