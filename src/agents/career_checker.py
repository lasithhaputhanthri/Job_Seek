"""
Phase 4 & 6: Career Check Worker Agent.
Fetches jobs for a target company via career_page_reader MCP tools,
matches against candidate UserProfile using word-boundary filters and geo resolution,
and records verified proposals to local SQLite state.
"""

import logging
from typing import Any, Dict, List, Optional

from src.config import config
from mcp_servers.career_page_reader.server import list_jobs, get_job_details
from src.agents.classifier import AIJobClassifierAgent
from src.db import StateDatabase
from src.geo import resolve_country_from_location
from src.schemas import UserProfile
from src.text_match import contains_any_word, is_non_engineering_role

logger = logging.getLogger("CareerCheckerWorker")


class CareerCheckerWorker:
    def __init__(self, db: StateDatabase, profile: UserProfile):
        self.db = db
        self.profile = profile
        self.classifier = AIJobClassifierAgent(profile=self.profile)

        # Build search keywords for pre-filtering
        self.target_keywords = set(self.profile.target_roles)
        self.skill_keywords = set(self.profile.must_have_skills)

    def _score_job(self, title: str, location: str, details_text: str) -> Dict[str, Any]:
        """Calculates match score, engineering rationale, and evidence via classifier."""
        res = self.classifier.classify_job(
            title=title,
            company_name="",
            location=location,
            details_text=details_text,
        )
        return {
            "match_score": res.match_score,
            "match_reason": res.match_reason,
            "evidence": res.evidence_quote,
            "work_mode": res.work_mode,
            "is_relevant": res.is_relevant,
            "eligible": res.eligible,
        }

    def _detect_work_mode(self, title: str, location: str, details_text: str) -> str:
        """Context-aware classification of work arrangements."""
        from src.text_match import normalize_text, is_genuine_hybrid_indicator, is_genuine_remote_indicator
        combined = f"{normalize_text(title)} {normalize_text(location)} {normalize_text(details_text)}"
        if is_genuine_hybrid_indicator(combined):
            return "Hybrid"
        elif is_genuine_remote_indicator(combined):
            return "Remote"
        return "On-site"

    def process_company(
        self,
        company: Dict[str, Any],
        min_score: Optional[int] = None,
        max_checks: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Examines open jobs for a company, filters matches, and records to DB.
        Zero fallback to company country.
        """
        threshold = min_score or config.MIN_RELEVANCE_SCORE
        company_id = company["id"]
        company_name = company["name"]
        careers_url = company.get("careers_url") or f"https://{company.get('domain', '')}"

        print(f"[CareerChecker] Checking company '{company_name}' ({careers_url})...")
        raw_jobs = list_jobs(careers_url)
        valid_jobs = [j for j in raw_jobs if "title" in j]
        print(f"[CareerChecker] Found {len(valid_jobs)} total listings at '{company_name}'.")

        matches_found = []
        checks_performed = 0

        for j in valid_jobs:
            if checks_performed >= max_checks:
                print(f"[CareerChecker] Capped at {max_checks} job evaluations for '{company_name}'.")
                break

            title = j["title"]
            job_url = j["job_url"]
            location = j.get("location", "Unspecified")

            # 1. Geographic resolution from JOB location (never company HQ)
            resolved_country, _, _ = resolve_country_from_location(location)

            # 2. Fast pre-filter on title using word boundaries before fetching description
            if is_non_engineering_role(title):
                continue

            # Check if title has any role or skill keyword
            has_role_hint = contains_any_word(self.target_keywords, title)
            has_skill_hint = contains_any_word(self.skill_keywords, title)
            has_eng_term = contains_any_word([
                "engineer", "developer", "architect", "hardware", "rf", "pcb", "embedded",
                "firmware", "fpga", "antenna", "analog", "electronics", "technician", "scientist"
            ], title)

            if not (has_role_hint or has_skill_hint or has_eng_term):
                continue

            checks_performed += 1

            # 3. Fetch details
            details_resp = get_job_details(job_url)
            details_text = details_resp.get("clean_text") or details_resp.get("safe_content", "")

            # 4. AI Classifier Evaluation
            cls_result = self.classifier.classify_job(
                title=title,
                company_name=company_name,
                location=location,
                details_text=details_text,
                ats_work_mode_hint=j.get("work_mode_hint"),
                structured_workplace_type=j.get("workplace_type"),
            )
            score = cls_result.match_score
            work_mode = cls_result.work_mode

            if cls_result.is_relevant and score >= threshold and cls_result.eligible:
                print(f"    * AI MATCH ({score}/100) [{resolved_country} | {work_mode}]: {title} ({location})")
                match_id = self.db.record_job_match(
                    company_id=company_id,
                    company_name=company_name,
                    country=resolved_country,
                    title=title,
                    job_url=job_url,
                    location=location,
                    work_mode=work_mode,
                    match_score=score,
                    match_reason=cls_result.match_reason,
                    evidence_quote=cls_result.evidence_quote,
                    source_url=careers_url,
                    seniority=cls_result.seniority,
                    visa_sponsorship=cls_result.visa_sponsorship,
                    clearance_or_citizenship_required=cls_result.clearance_or_citizenship_required,
                    visa_evidence_quote=cls_result.visa_evidence_quote,
                    eligible=cls_result.eligible,
                    eligibility_reason=cls_result.eligibility_reason,
                    description_text=details_text,
                    classifier_engine=self.classifier.provider_name,
                    classifier_model=config.GEMINI_MODEL,
                )
                if match_id:
                    matches_found.append({
                        "id": match_id,
                        "title": title,
                        "score": score,
                        "job_url": job_url,
                    })

        return matches_found
