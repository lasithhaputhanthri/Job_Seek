"""
Job Board Aggregator Worker.
Coordinates harvesting from public job boards (Arbeitnow, Remotive, Jobicy, RemoteOK).
Strict Ground Rule: Never invents fake domains, never overwrites careers_url with job URL.
Employers are recorded into the dedicated employers table.
"""

import logging
from typing import Any, Dict, List, Optional

from src.adapters.boards import ArbeitnowSource, JobicySource, RemotiveSource, RemoteOKSource
from src.agents.classifier import AIJobClassifierAgent
from src.config import config
from src.db import StateDatabase
from src.geo import resolve_country_from_location
from src.schemas import UserProfile
from src.text_match import contains_any_word, is_non_engineering_role

logger = logging.getLogger("JobBoardWorker")


class JobBoardWorker:
    def __init__(self, db: StateDatabase, profile: UserProfile):
        self.db = db
        self.profile = profile
        self.classifier = AIJobClassifierAgent(profile=self.profile)
        self.sources = [
            ArbeitnowSource(),
            RemotiveSource(),
            JobicySource(),
            RemoteOKSource(),
        ]

    def run_all_job_boards(self, limit_per_source: int = 50) -> int:
        """Runs all configured job board adapters through the matching and recording pipeline."""
        total_matches = 0
        for source in self.sources:
            try:
                print(f"[JobBoardWorker] Harvesting from '{source.name}' (limit: {limit_per_source})...")
                records = source.list_jobs(limit=limit_per_source)
                print(f"[JobBoardWorker] Retrieved {len(records)} raw jobs from '{source.name}'.")

                for rec in records:
                    # 1. Word-boundary filter on title
                    if is_non_engineering_role(rec.title):
                        continue

                    # 2. Geographic resolution from job location
                    country, _, _ = resolve_country_from_location(rec.location)

                    # 3. Store employer in employers table (Strict: Zero fake domains)
                    self.db.add_board_employer(
                        name=rec.company_name,
                        domain=rec.company_domain,
                        source=source.name,
                    )

                    # Register or lookup company in companies table
                    norm_domain = rec.company_domain or f"board:{rec.company_name.lower().replace(' ', '-')}"
                    comp_id = self.db.add_company(
                        name=rec.company_name,
                        domain=norm_domain,
                        country=country,
                        industry=f"Engineering & Technology (via {source.name})",
                        careers_url="",  # Never overwrite with job URL!
                    )

                    # 4. Classify job
                    cls_res = self.classifier.classify_job(
                        title=rec.title,
                        company_name=rec.company_name,
                        location=rec.location,
                        details_text=rec.description,
                        ats_work_mode_hint=rec.work_mode_hint,
                    )

                    if cls_res.is_relevant and cls_res.match_score >= config.MIN_RELEVANCE_SCORE and cls_res.eligible:
                        match_id = self.db.record_job_match(
                            company_id=comp_id,
                            company_name=rec.company_name,
                            country=country,
                            title=rec.title,
                            job_url=rec.job_url,
                            location=rec.location,
                            work_mode=cls_res.work_mode,
                            match_score=cls_res.match_score,
                            match_reason=cls_res.match_reason,
                            evidence_quote=cls_res.evidence_quote,
                            source_url=rec.source_url,
                            seniority=cls_res.seniority,
                            visa_sponsorship=cls_res.visa_sponsorship,
                            clearance_or_citizenship_required=cls_res.clearance_or_citizenship_required,
                            visa_evidence_quote=cls_res.visa_evidence_quote,
                            eligible=cls_res.eligible,
                            eligibility_reason=cls_res.eligibility_reason,
                            description_text=rec.description,
                            classifier_engine=self.classifier.provider_name,
                            classifier_model=config.GEMINI_MODEL,
                        )
                        if match_id:
                            total_matches += 1
                            print(f"  * [{source.name} MATCH ({cls_res.match_score}/100)] [{country} | {cls_res.work_mode}] {rec.title} @ {rec.company_name}")

            except Exception as e:
                logger.error(f"[JobBoardWorker] Source '{source.name}' failure: {e}")

        return total_matches

    def fetch_arbeitnow_jobs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Legacy helper running Arbeitnow source."""
        source = ArbeitnowSource()
        return [{"title": r.title, "company": r.company_name, "job_url": r.job_url} for r in source.list_jobs(limit=limit)]

    def fetch_remotive_jobs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Legacy helper running Remotive source."""
        source = RemotiveSource()
        return [{"title": r.title, "company": r.company_name, "job_url": r.job_url} for r in source.list_jobs(limit=limit)]
