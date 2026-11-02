"""
Pipeline Stage 2: Cost-Funnel Job Harvest.
Executes high-scale parallel job scouting across direct company ATS portals and public job boards.
Strict Ground Rule: Enforces the 7-step cost funnel (free board fetch -> title regex ->
hard filters -> fetch description -> 2nd hard filter -> LLM score shortlist).
Workers never write Excel. Resumable and budget-aware.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from src.adapters.boards import ArbeitnowSource, JobicySource, RemotiveSource, RemoteOKSource
from src.agents.classifier import AIJobClassifierAgent
from src.config import config
from src.db import StateDatabase
from src.geo import resolve_country_from_location
from src.schemas import UserProfile
from src.taxonomy import SearchTaxonomy, TaxonomyGenerator
from src.text_match import contains_any_word, is_non_engineering_role
from mcp_servers.career_page_reader.server import get_job_details, list_jobs

logger = logging.getLogger("StageHarvest")


class CostFunnelHarvester:
    def __init__(self, db: StateDatabase, profile: UserProfile, taxonomy: SearchTaxonomy):
        self.db = db
        self.profile = profile
        self.taxonomy = taxonomy
        self.classifier = AIJobClassifierAgent(profile=self.profile)

        # Budget & Telemetry Counters
        self.http_requests_made = 0
        self.llm_evaluations_run = 0
        self.boards_scanned = 0
        self.boards_failed = 0
        self.jobs_seen = 0
        self.jobs_title_filtered = 0
        self.jobs_hard_filtered = 0
        self.jobs_shortlisted = 0
        self.jobs_recorded = 0
        self.consecutive_empty_batches = 0

    async def run_harvest(
        self,
        batch_size: int = 50,
        max_batches: Optional[int] = None,
        harvest_boards: bool = True,
        board_limit_per_source: int = 50,
    ) -> Dict[str, Any]:
        print("\n" + "=" * 78)
        print("PIPELINE STAGE 2: COST-FUNNEL JOB HARVEST")
        print(f"Global Concurrency   : {config.GLOBAL_CONCURRENCY}")
        print(f"Per-Host Concurrency : {config.PER_HOST_CONCURRENCY}")
        print(f"Max LLM Budget Calls : {config.MAX_LLM_CALLS}")
        print("=" * 78)

        start_time = time.time()

        # 1. Harvest from Public Job Boards First if requested
        if harvest_boards:
            await self._harvest_job_boards(limit_per_source=board_limit_per_source)

        # 2. Process Company ATS Tasks from Queue
        semaphore = asyncio.Semaphore(config.GLOBAL_CONCURRENCY)
        batch_num = 0

        while True:
            # Check runtime and budget limits
            elapsed = time.time() - start_time
            if elapsed >= config.MAX_RUNTIME_SECONDS:
                print(f"[StageHarvest] Reached MAX_RUNTIME_SECONDS ({config.MAX_RUNTIME_SECONDS}s). Gracefully stopping.")
                break
            if self.llm_evaluations_run >= config.MAX_LLM_CALLS:
                print(f"[StageHarvest] Reached MAX_LLM_CALLS ({config.MAX_LLM_CALLS}). Gracefully stopping.")
                break
            if self.consecutive_empty_batches >= config.MAX_CONSECUTIVE_EMPTY_BATCHES:
                print(f"[StageHarvest] Hit {config.MAX_CONSECUTIVE_EMPTY_BATCHES} consecutive empty batches. Stopping harvest stage.")
                break
            if max_batches and batch_num >= max_batches:
                break

            # Claim tasks atomically from durable queue
            tasks = await asyncio.to_thread(self.db.fetch_and_claim_tasks, "CAREER_CHECK", batch_size)
            if not tasks:
                print("[StageHarvest] No more pending tasks in queue.")
                break

            batch_num += 1
            print(f"\n[StageHarvest] Dispatching Batch #{batch_num} ({len(tasks)} company tasks)...")
            batch_matches_found = 0

            async def _process_task(task: Dict[str, Any]):
                nonlocal batch_matches_found
                async with semaphore:
                    task_id = task["id"]
                    payload = task.get("payload", {})
                    comp_id = payload.get("company_id")
                    comp_name = payload.get("name", "Unknown Company")
                    careers_url = payload.get("careers_url", "")

                    if not careers_url and payload.get("domain"):
                        careers_url = f"https://{payload['domain']}"

                    if not careers_url:
                        await asyncio.to_thread(self.db.complete_task, task_id)
                        return

                    try:
                        matches = await self._scan_company_funnel(comp_id, comp_name, careers_url)
                        await asyncio.to_thread(self.db.complete_task, task_id)
                        self.boards_scanned += 1
                        if matches > 0:
                            batch_matches_found += matches
                    except Exception as e:
                        self.boards_failed += 1
                        logger.warning(f"Error processing {comp_name}: {e}")
                        await asyncio.to_thread(self.db.fail_task, task_id, str(e), "HARVEST_ERROR")

            # Run batch concurrently
            await asyncio.gather(*[_process_task(t) for t in tasks])

            if batch_matches_found == 0:
                self.consecutive_empty_batches += 1
            else:
                self.consecutive_empty_batches = 0

            print(
                f"[Batch #{batch_num} Summary] Scanned: {len(tasks)} | Matches Found: {batch_matches_found} | "
                f"Total Shortlisted: {self.jobs_shortlisted} | LLM Evals: {self.llm_evaluations_run}"
            )

        print("\n" + "=" * 78)
        print("STAGE 2 HARVEST SUMMARY:")
        print(f"  * Boards Scanned          : {self.boards_scanned}")
        print(f"  * Boards Failed           : {self.boards_failed}")
        print(f"  * Total Jobs Seen         : {self.jobs_seen}")
        print(f"  * Filtered by Title Regex : {self.jobs_title_filtered}")
        print(f"  * Filtered by Hard Filters: {self.jobs_hard_filtered}")
        print(f"  * Shortlisted for Scoring : {self.jobs_shortlisted}")
        print(f"  * LLM Evals Performed     : {self.llm_evaluations_run}")
        print(f"  * Matches Recorded in DB  : {self.jobs_recorded}")
        print("=" * 78)

        return {
            "boards_scanned": self.boards_scanned,
            "jobs_seen": self.jobs_seen,
            "jobs_shortlisted": self.jobs_shortlisted,
            "jobs_recorded": self.jobs_recorded,
            "llm_evaluations": self.llm_evaluations_run,
        }

    async def _scan_company_funnel(self, comp_id: int, comp_name: str, careers_url: str) -> int:
        """Applies the 7-step cost funnel to a single company's career portal."""
        # Step 1: Free board fetch (0 LLM tokens)
        self.http_requests_made += 1
        raw_jobs = await asyncio.to_thread(list_jobs, careers_url)
        valid_jobs = [j for j in raw_jobs if "title" in j]
        self.jobs_seen += len(valid_jobs)

        matches_for_company = 0

        for j in valid_jobs:
            title = j["title"]
            job_url = j["job_url"]
            location = j.get("location", "")

            # Step 2: Title filter using taxonomy + word-boundary regex (0 LLM tokens)
            if is_non_engineering_role(title, self.taxonomy.exclude_title_patterns):
                self.jobs_title_filtered += 1
                continue

            has_title_match = contains_any_word(self.taxonomy.include_title_patterns, title)
            has_eng_term = contains_any_word([
                "engineer", "developer", "architect", "hardware", "rf", "pcb", "embedded",
                "firmware", "fpga", "antenna", "analog", "electronics", "technician", "scientist"
            ], title)

            if not (has_title_match or has_eng_term):
                self.jobs_title_filtered += 1
                continue

            # Step 3: Hard filters (Country, Seniority, Internships)
            resolved_country, _, is_remote_anywhere = resolve_country_from_location(location)

            target_c_lower = [c.lower() for c in self.profile.target_countries]
            is_global = any(w in " ".join(target_c_lower) for w in ["worldwide", "global", "all", "anywhere"])

            if not is_remote_anywhere and not is_global and resolved_country != "Unknown":
                if not any(tc in resolved_country.lower() or resolved_country.lower() in tc for tc in target_c_lower):
                    self.jobs_hard_filtered += 1
                    continue

            # Step 4: Fetch full description ONLY for surviving shortlisted postings
            self.http_requests_made += 1
            details_resp = await asyncio.to_thread(get_job_details, job_url)
            details_text = details_resp.get("clean_text") or details_resp.get("safe_content", "")

            # Step 5 & 6: Classifier Evaluation (Hard filter pass 2 + LLM / Semantic scoring)
            self.llm_evaluations_run += 1
            self.jobs_shortlisted += 1

            cls_result = await asyncio.to_thread(
                self.classifier.classify_job,
                title=title,
                company_name=comp_name,
                location=location,
                details_text=details_text,
                ats_work_mode_hint=j.get("work_mode_hint"),
                structured_workplace_type=j.get("workplace_type"),
            )

            # Record surviving matches
            if cls_result.is_relevant and cls_result.match_score >= config.MIN_RELEVANCE_SCORE and cls_result.eligible:
                match_id = await asyncio.to_thread(
                    self.db.record_job_match,
                    company_id=comp_id,
                    company_name=comp_name,
                    country=resolved_country,
                    title=title,
                    job_url=job_url,
                    location=location,
                    work_mode=cls_result.work_mode,
                    match_score=cls_result.match_score,
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
                    matches_for_company += 1
                    self.jobs_recorded += 1
                    print(f"  * [HARVEST MATCH ({cls_result.match_score}/100)] [{resolved_country} | {cls_result.work_mode}] {title} @ {comp_name}")

        return matches_for_company

    async def _harvest_job_boards(self, limit_per_source: int = 50):
        """Harvests public job boards concurrently."""
        sources = [ArbeitnowSource(), RemotiveSource(), JobicySource(), RemoteOKSource()]
        print(f"\n[StageHarvest] Querying {len(sources)} public job boards...")

        for s in sources:
            try:
                records = await asyncio.to_thread(s.list_jobs, limit_per_source)
                print(f"  -> '{s.name}': Retrieved {len(records)} postings.")

                for rec in records:
                    if is_non_engineering_role(rec.title):
                        continue

                    country, _, _ = resolve_country_from_location(rec.location)

                    # Store employer in employers table without faking domains
                    await asyncio.to_thread(self.db.add_board_employer, rec.company_name, rec.company_domain, s.name)
                    norm_domain = rec.company_domain or f"board:{rec.company_name.lower().replace(' ', '-')}"
                    comp_id = await asyncio.to_thread(
                        self.db.add_company,
                        name=rec.company_name,
                        domain=norm_domain,
                        country=country,
                        industry=f"Technology (via {s.name})",
                        careers_url="",
                    )

                    # Classify
                    self.llm_evaluations_run += 1
                    cls_res = await asyncio.to_thread(
                        self.classifier.classify_job,
                        title=rec.title,
                        company_name=rec.company_name,
                        location=rec.location,
                        details_text=rec.description,
                        ats_work_mode_hint=rec.work_mode_hint,
                    )

                    if cls_res.is_relevant and cls_res.match_score >= config.MIN_RELEVANCE_SCORE and cls_res.eligible:
                        await asyncio.to_thread(
                            self.db.record_job_match,
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
                        self.jobs_recorded += 1
            except Exception as e:
                logger.warning(f"Error querying board '{s.name}': {e}")
