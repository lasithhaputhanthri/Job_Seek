"""
Phase 6: High-Concurrency Parallel Orchestrator.
Dispatches company career checks across multiple asyncio workers with:
- Concurrency bounding via asyncio.Semaphore (default 5 concurrent workers)
- Polite domain throttling
- Atomic SQLite task checkpoints (resumes crashed runs)
- Multi-country task grouping
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.agents.career_checker import CareerCheckerWorker
from src.agents.verifier import AIVerifierAgent
from src.db import StateDatabase
from src.schemas import UserProfile
from src.sync.sheets import SheetsSyncManager


class ParallelManagerAgent:
    def __init__(
        self,
        db: StateDatabase,
        profile: UserProfile,
        max_concurrency: int = 5,
        sample_audit_rate: float = 0.20,
    ):
        self.db = db
        self.profile = profile
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.sample_audit_rate = sample_audit_rate
        self.sync_manager = SheetsSyncManager(db=self.db)
        self.worker = CareerCheckerWorker(db=self.db, profile=self.profile)
        self.verifier = AIVerifierAgent(profile=self.profile)

    def bootstrap_all_companies(self, companies: List[Dict[str, Any]]) -> List[int]:
        """Creates durable tasks in SQLite for any company not yet processed."""
        task_ids = []
        for c in companies:
            comp_id = self.db.add_company(
                name=c["name"],
                domain=c["domain"],
                country=c.get("country", "USA"),
                industry=c.get("industry", "Hardware & Electronics"),
                careers_url=c.get("careers_url", ""),
            )
            # Create task if not already existing
            task_id = self.db.create_task(
                task_type="CAREER_CHECK",
                target_id=comp_id,
                payload={"company_id": comp_id, "name": c["name"], "country": c.get("country", "USA"), "careers_url": c.get("careers_url", "")},
            )
            task_ids.append(task_id)
        print(f"[ParallelManager] Registered {len(task_ids)} companies in durable task queue.")
        return task_ids

    async def _process_single_task(self, task: Dict[str, Any]):
        """Worker task execution wrapped inside a concurrency semaphore."""
        async with self.semaphore:
            task_id = task["id"]
            payload = task["payload"]
            comp_id = payload["company_id"]
            comp_name = payload["name"]
            country = payload.get("country", "Global")

            self.db.update_task_status(task_id, "RUNNING")
            print(f"  [WORKER] Checking [{country.upper()}] '{comp_name}'...")

            try:
                # Fetch full company record from DB
                with self.db._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM companies WHERE id = ?", (comp_id,))
                    comp = dict(cursor.fetchone())

                # Run worker (in thread pool to keep asyncio event loop responsive)
                loop = asyncio.get_running_loop()
                matches = await loop.run_in_executor(None, self.worker.process_company, comp)

                self.db.update_task_status(task_id, "COMPLETED")
                self.db.log_trace(
                    task_id=task_id,
                    agent_name="CareerCheckerWorker",
                    step=1,
                    action="PROCESS_COMPANY_PARALLEL",
                    details=f"Found {len(matches)} match(es) for '{comp_name}' ({country})",
                )
                print(f"  [DONE] '{comp_name}': {len(matches)} relevant match(es) recorded.")

            except Exception as e:
                print(f"  [TASK ERROR] '{comp_name}' failed: {e}")
                self.db.update_task_status(task_id, "FAILED", error_message=str(e))

            # Small polite pause to prevent IP rate spikes
            await asyncio.sleep(0.5)

    async def run_parallel_workers(self, batch_size: int = 40):
        """Dispatches all pending tasks concurrently."""
        tasks = self.db.fetch_pending_tasks(task_type="CAREER_CHECK", limit=batch_size)
        if not tasks:
            print("[ParallelManager] No pending tasks in queue.")
            return

        print(f"\n[ParallelManager] Launching {len(tasks)} concurrent tasks across workers...")
        await asyncio.gather(*(self._process_single_task(t) for t in tasks))
        print("[ParallelManager] All concurrent worker tasks finished.")

    def verify_all(self):
        """AI Verifier Agent audit on all unverified job proposals."""
        print("\n" + "=" * 70)
        print("[ParallelManager] RUNNING AI QUALITY AUDIT ON ALL FOUND MATCHES")
        print("=" * 70)

        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM job_matches WHERE verified = 0")
            unverified_rows = [dict(r) for r in cursor.fetchall()]

        print(f"[AI Verifier Agent] Auditing {len(unverified_rows)} proposed rows...")
        verified_count = 0

        for row in unverified_rows:
            job_id = row["id"]
            title = row["title"]
            company = row["company_name"]

            audit = self.verifier.audit_proposal(row)

            if audit.is_verified:
                self.db.verify_job_match(job_id, verified=True, notes=audit.audit_notes)
                verified_count += 1
                print(f"  [AI AUDIT PASS] ({audit.confidence_score}%) '{title}' @ {company} -> {audit.audit_notes}")
            else:
                self.db.verify_job_match(job_id, verified=False, notes=audit.audit_notes)
                print(f"  [AI AUDIT REJECT] '{title}' @ {company} -> {audit.audit_notes}")

        print(f"[AI Verifier Agent] Audit complete. {verified_count} row(s) approved.")

    def export_results(self) -> Dict[str, Any]:
        """Exports per-country and unified Excel workbook."""
        print("\n[ParallelManager] Exporting multi-sheet Excel workbook and country breakdowns...")
        return self.sync_manager.export_all_country_breakdowns(candidate_profile=self.profile)
