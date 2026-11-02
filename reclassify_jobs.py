"""
Versioned AI Job Reclassification Script.
Re-evaluates existing job postings in the database using the updated classifier.
Strict Ground Rules:
- Never destructively overwrites original match_score or evidence_quote in job_matches.
- Records all rescore evaluations into the versioned 'job_scores' history table.
- Re-fetches the real job description from source if not stored locally.
- Supports --only-verified and --dry-run flags.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Safe stdout for Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.config import config
from src.agents.classifier import AIJobClassifierAgent
from src.db import StateDatabase
from src.schemas import UserProfile
from mcp_servers.career_page_reader.server import get_job_details

logger = logging.getLogger("ReclassifyJobs")


def reclassify_jobs(
    db_path: str = "data/job_hunter.db",
    profile_path: str = "data/profile.json",
    only_verified: bool = False,
    dry_run: bool = False,
    limit: Optional[int] = None,
):
    print("=" * 78)
    print("AI JOB CLASSIFIER: VERSIONED BATCH RE-EVALUATION")
    print(f"Mode: {'DRY RUN (No DB Writes)' if dry_run else 'LIVE VERSIONED PERSISTENCE'}")
    print(f"Filter: {'ONLY VERIFIED ROWS' if only_verified else 'ALL JOB ROWS'}")
    print("=" * 78)

    p_path = Path(profile_path)
    if not p_path.exists():
        print(f"Error: Candidate profile '{profile_path}' not found.")
        return

    with open(p_path, "r", encoding="utf-8") as f:
        profile_data = json.load(f)
    profile = UserProfile(**profile_data)

    db = StateDatabase(db_path)
    classifier = AIJobClassifierAgent(profile=profile)
    print(f"[AI Agent] Active Engine: {classifier.provider_name}")
    print(f"[Candidate] Evaluating for: {profile.name} ({profile.primary_domain})")

    with db.get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM job_matches"
        if only_verified:
            query += " WHERE verified = 1"
        query += " ORDER BY id ASC"
        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query)
        rows = [dict(r) for r in cursor.fetchall()]

    print(f"\nProcessing {len(rows)} job(s)...")
    rescore_count = 0
    skipped_count = 0

    for idx, r in enumerate(rows, 1):
        job_id = r["id"]
        title = r["title"]
        company = r["company_name"]
        location = r["location"] or ""
        job_url = r["job_url"]
        orig_score = r["match_score"]
        orig_evidence = r["evidence_quote"] or ""

        # Obtain full description: check stored description_text first
        desc_text = r.get("description_text") or ""
        if not desc_text:
            # Re-fetch real description from live URL
            try:
                det = get_job_details(job_url)
                desc_text = det.get("safe_content", "")
            except Exception as e:
                logger.debug(f"Failed to fetch {job_url}: {e}")

        if not desc_text:
            # Skip if no description is available to avoid rescoring on fragments
            skipped_count += 1
            continue

        # Re-classify with updated classifier
        cls_res = classifier.classify_job(
            title=title,
            company_name=company,
            location=location,
            details_text=desc_text,
        )

        rescore_count += 1
        diff = cls_res.match_score - orig_score
        sign = "+" if diff > 0 else ""

        if not dry_run:
            with db.get_connection() as conn:
                cur = conn.cursor()
                # 1. Append versioned score history
                cur.execute("""
                INSERT INTO job_scores (job_match_id, classifier_version, classifier_model, score, work_mode, evidence_quote, reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    job_id,
                    config.PROMPT_VERSION,
                    config.GEMINI_MODEL,
                    cls_res.match_score,
                    cls_res.work_mode,
                    cls_res.evidence_quote,
                    cls_res.match_reason,
                ))
                # 2. Update provenance and metadata in job_matches WITHOUT destructively overwriting original score
                cur.execute("""
                UPDATE job_matches
                SET classifier_engine = ?, prompt_version = ?, last_seen_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """, (classifier.provider_name, config.PROMPT_VERSION, job_id))
                conn.commit()

        if idx <= 15 or idx % 25 == 0 or idx == len(rows):
            print(
                f"[{idx:>3}/{len(rows)}] ({orig_score:>2} -> {cls_res.match_score:>2} [{sign}{diff:>2}]) "
                f"[{cls_res.work_mode:<7}] {title[:35]:<35} @ {company[:20]}"
            )

    print("\n" + "=" * 78)
    print("RECLASSIFICATION SUMMARY:")
    print(f"  * Total Processed : {len(rows)}")
    print(f"  * Re-scored       : {rescore_count}")
    print(f"  * Skipped (No text): {skipped_count}")
    print(f"  * Version Key     : {config.PROMPT_VERSION}")
    print("=" * 78)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Versioned AI Job Reclassification")
    parser.add_argument("--only-verified", action="store_true", help="Only rescore verified rows")
    parser.add_argument("--dry-run", action="store_true", help="Preview rescores without modifying database")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of rows to evaluate")
    parser.add_argument("--db", type=str, default="data/job_hunter.db", help="Path to database")
    parser.add_argument("--profile", type=str, default="data/profile.json", help="Path to profile JSON")
    args = parser.parse_args()

    reclassify_jobs(
        db_path=args.db,
        profile_path=args.profile,
        only_verified=args.only_verified,
        dry_run=args.dry_run,
        limit=args.limit,
    )
