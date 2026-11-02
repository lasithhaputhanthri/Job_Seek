"""
Non-Destructive Data Repair Script.
Scans existing job_matches rows in data/job_hunter.db and audits:
1. Garbage URL/HTML evidence quotes (e.g. 'com/en-US/Dyson_Careers/job/...">')
2. Country mismatches (e.g. Dyson Shenzhen labeled 'UK', ADI Istanbul labeled 'Ireland')
3. Verified rows below the canonical MIN_RELEVANCE_SCORE
4. Internships or graduate program postings
5. Rows approved by legacy fallback verifier

Flags (does not delete) problematic rows, records audit findings, and reports counts before/after.
Supports --dry-run.
"""

import argparse
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import config
from src.db import StateDatabase
from src.geo import resolve_country_from_location
from src.text_match import is_internship_or_graduate


def repair_existing_data(db_path: str = "data/job_hunter.db", dry_run: bool = False):
    print("=" * 78)
    print("DATA AUDIT & REPAIR UTILITY (NON-DESTRUCTIVE)")
    print(f"Database : {db_path}")
    print(f"Mode     : {'DRY RUN (Read-Only Preview)' if dry_run else 'APPLY AUDIT FLAGS & RE-QUEUE'}")
    print("=" * 78)

    db = StateDatabase(db_path)

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM job_matches ORDER BY id ASC")
        rows = [dict(r) for r in cursor.fetchall()]

    total_rows = len(rows)
    print(f"\nAuditing {total_rows} existing job posting rows...")

    bad_evidence_ids = []
    country_mismatch_ids = []
    low_score_verified_ids = []
    internship_ids = []
    fallback_verifier_ids = []

    for r in rows:
        job_id = r["id"]
        title = r["title"]
        company = r["company_name"]
        location = r["location"] or ""
        country = r["country"]
        score = r["match_score"]
        verified = r["verified"]
        evidence = r["evidence_quote"] or ""
        notes = r["verification_notes"] or ""

        # 1. Audit Bad Evidence Quotes (URL fragments, HTML wrappers, etc.)
        ev_lower = evidence.lower()
        if (
            not evidence
            or "http" in ev_lower
            or "com/" in ev_lower
            or ".com" in ev_lower
            or "url=" in ev_lower
            or "<untrusted" in ev_lower
            or "</" in ev_lower
            or "<div" in ev_lower
            or evidence.startswith("com/")
            or len(evidence.strip()) < 15
        ):
            bad_evidence_ids.append(job_id)

        # 2. Audit Country Mismatches
        if location:
            resolved_c, conf, is_remote = resolve_country_from_location(location)
            if conf >= 0.85 and resolved_c != "Unknown":
                if resolved_c.lower() != country.lower() and country not in ["Global / Tech", "Europe / International"]:
                    country_mismatch_ids.append((job_id, country, resolved_c, location))

        # 3. Audit Verified rows below canonical MIN_RELEVANCE_SCORE
        if verified == 1 and score < config.MIN_RELEVANCE_SCORE:
            low_score_verified_ids.append((job_id, score, title, company))

        # 4. Audit Internships & Graduate Schemes
        if is_internship_or_graduate(title):
            internship_ids.append((job_id, title, company))

        # 5. Audit Fallback Verifier Approvals
        if "[AI Verifier PASS]" in notes or "FALLBACK_RULES_APPROVED" in notes:
            fallback_verifier_ids.append(job_id)

    print("\n" + "-" * 78)
    print("AUDIT FINDINGS:")
    print(f"  * Rows with Garbage/URL Evidence Quotes : {len(bad_evidence_ids):>4} ({len(bad_evidence_ids)/total_rows*100:.1f}%)")
    print(f"  * Rows with Country vs Location Mismatch: {len(country_mismatch_ids):>4} ({len(country_mismatch_ids)/total_rows*100:.1f}%)")
    print(f"  * Verified Rows Below Min Score (<{config.MIN_RELEVANCE_SCORE}): {len(low_score_verified_ids):>4}")
    print(f"  * Unrequested Internship / Graduate Rows : {len(internship_ids):>4}")
    print(f"  * Rows Verified by Legacy Fallback Verifier: {len(fallback_verifier_ids):>4}")
    print("-" * 78)

    # Sample country mismatches
    if country_mismatch_ids:
        print("\nSample Country Mismatches:")
        for j_id, orig_c, new_c, loc in country_mismatch_ids[:5]:
            print(f"  [ID {j_id}] '{loc}' was labeled '{orig_c}' -> resolved to '{new_c}'")

    if not dry_run:
        print("\nApplying Non-Destructive Data Repairs...")
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Flag bad evidence rows: set evidence_quote = NULL and cap score at 60
            for j_id in bad_evidence_ids:
                cursor.execute("""
                UPDATE job_matches
                SET evidence_quote = NULL,
                    match_score = MIN(match_score, 60),
                    verified = 0,
                    verification_notes = 'Flagged by repair script: invalid URL/HTML evidence quote.'
                WHERE id = ?
                """, (j_id,))

            # 2. Correct country attribution from location
            for j_id, orig_c, new_c, loc in country_mismatch_ids:
                cursor.execute("""
                UPDATE job_matches
                SET country = ?
                WHERE id = ?
                """, (new_c, j_id))

            # 3. Un-verify low score rows
            for j_id, score, title, comp in low_score_verified_ids:
                cursor.execute("""
                UPDATE job_matches
                SET verified = 0,
                    verification_notes = 'Un-verified: score below MIN_RELEVANCE_SCORE threshold.'
                WHERE id = ?
                """, (j_id,))

            # 4. Mark internships ineligible
            for j_id, title, comp in internship_ids:
                cursor.execute("""
                UPDATE job_matches
                SET eligible = 0,
                    eligibility_reason = 'Excluded: internship or graduate program',
                    verified = 0
                WHERE id = ?
                """, (j_id,))

            # 5. Create repair tasks to re-fetch and re-verify
            recheck_ids = set(bad_evidence_ids + [item[0] for item in country_mismatch_ids])
            for j_id in recheck_ids:
                cursor.execute("""
                INSERT OR IGNORE INTO tasks (task_type, target_id, payload, status)
                VALUES ('JOB_REPAIR', ?, ?, 'PENDING')
                """, (j_id, f'{{"job_id": {j_id}, "action": "RE_FETCH_AND_VERIFY"}}'))

            conn.commit()

        print("Repairs committed successfully! Re-checking counts...")
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM job_matches WHERE verified = 1")
            new_verified = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM job_matches WHERE eligible = 0")
            new_ineligible = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM tasks WHERE task_type = 'JOB_REPAIR'")
            repair_tasks = cursor.fetchone()[0]

        print(f"  * Still-Verified Eligible Jobs: {new_verified}")
        print(f"  * Jobs Flagged Ineligible     : {new_ineligible}")
        print(f"  * Queued Repair Tasks         : {repair_tasks}")

    print("=" * 78)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit and Repair Legacy Database Rows")
    parser.add_argument("--dry-run", action="store_true", help="Preview audit findings without updating database")
    parser.add_argument("--db", type=str, default="data/job_hunter.db", help="Path to database")
    args = parser.parse_args()

    repair_existing_data(db_path=args.db, dry_run=args.dry_run)
