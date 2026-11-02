"""
Pipeline Stage 3: Independent Adversarial Verification.
Executes the adversarial quality auditor on all unverified job matches.
Data Contract: Reads unverified rows from `job_matches` -> Writes verified/rejected verdicts to DB.
Resumable & Idempotent.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from src.agents.verifier import AIVerifierAgent
from src.config import config
from src.db import StateDatabase
from src.schemas import UserProfile

logger = logging.getLogger("StageVerify")


async def run_verify_stage(
    db: StateDatabase,
    profile: UserProfile,
    batch_size: int = 50,
) -> Dict[str, Any]:
    print("\n" + "=" * 78)
    print("PIPELINE STAGE 3: INDEPENDENT ADVERSARIAL VERIFICATION")
    print("=" * 78)

    verifier = AIVerifierAgent(profile=profile)

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM job_matches WHERE verified = 0 AND eligible = 1 ORDER BY id ASC")
        unverified = [dict(r) for r in cursor.fetchall()]

    print(f"[StageVerify] Found {len(unverified)} proposed job match(es) awaiting verification audit...")
    stats = {"verified": 0, "rejected": 0, "total": len(unverified)}

    semaphore = asyncio.Semaphore(config.GLOBAL_CONCURRENCY)

    async def _audit_job(row: Dict[str, Any]):
        async with semaphore:
            job_id = row["id"]
            title = row["title"]
            company = row["company_name"]

            # Independent audit
            audit = await asyncio.to_thread(verifier.audit_proposal, row)

            if audit.is_verified:
                await asyncio.to_thread(
                    db.verify_job_match,
                    job_id=job_id,
                    verified=True,
                    notes=audit.audit_notes,
                    verifier_engine=audit.verifier_engine,
                    still_open=audit.still_open,
                )
                stats["verified"] += 1
                print(f"  [APPROVED] ({audit.verifier_engine}) '{title}' @ {company} -> {audit.audit_notes[:70]}")
            else:
                await asyncio.to_thread(
                    db.verify_job_match,
                    job_id=job_id,
                    verified=False,
                    notes=audit.audit_notes,
                    verifier_engine=audit.verifier_engine,
                    still_open=audit.still_open,
                )
                stats["rejected"] += 1
                print(f"  [REJECTED] ({audit.verifier_engine}) '{title}' @ {company} -> {audit.audit_notes[:70]}")

    await asyncio.gather(*[_audit_job(r) for r in unverified])

    print("\n" + "=" * 78)
    print("STAGE 3 VERIFICATION COMPLETE:")
    print(f"  * Total Audited : {stats['total']}")
    print(f"  * Approved      : {stats['verified']}")
    print(f"  * Rejected      : {stats['rejected']}")
    print("=" * 78)

    return stats
