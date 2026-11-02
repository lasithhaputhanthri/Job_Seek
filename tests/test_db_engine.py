"""
Unit Tests for Database Engine & Reliability (src/db.py).
Tests:
1. create_task idempotency
2. Atomic task claims & stale lease recovery
3. Exponential backoff retries & failure tracking
4. Canonical key deduplication
5. Reliable SELECT id on upsert & verified reset on score change
6. Board employers recording without fake domains
"""

import os
import time
import unittest
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from src.db import StateDatabase, compute_canonical_job_key


class TestDatabaseEngine(unittest.TestCase):
    def setUp(self):
        self.test_db_path = f"data/test_db_{uuid.uuid4().hex[:8]}.db"
        self.db = StateDatabase(self.test_db_path)

    def tearDown(self):
        del self.db
        import gc
        gc.collect()
        if Path(self.test_db_path).exists():
            try:
                os.remove(self.test_db_path)
            except Exception:
                pass

    def test_canonical_job_key_stripping(self):
        """Verify tracking parameters and URL variants resolve to the same canonical key."""
        url1 = "https://boards.greenhouse.io/anduril/jobs/12345?gh_src=linkedin&utm_campaign=q1"
        url2 = "https://boards.greenhouse.io/anduril/jobs/12345/?utm_source=indeed"
        url3 = "https://boards.greenhouse.io/anduril/jobs/12345#apply"

        key1 = compute_canonical_job_key(url1)
        key2 = compute_canonical_job_key(url2)
        key3 = compute_canonical_job_key(url3)

        self.assertEqual(key1, key2)
        self.assertEqual(key1, key3)
        self.assertEqual(key1, "url:https://boards.greenhouse.io/anduril/jobs/12345")

    def test_create_task_idempotency(self):
        """Verify tasks cannot be duplicated for the same (task_type, target_id)."""
        t1 = self.db.create_task("CAREER_CHECK", 42, {"company": "NXP"})
        t2 = self.db.create_task("CAREER_CHECK", 42, {"company": "NXP"})
        self.assertEqual(t1, t2)

        # Different target_id creates a new task
        t3 = self.db.create_task("CAREER_CHECK", 43, {"company": "ASML"})
        self.assertNotEqual(t1, t3)

    def test_atomic_claim_and_completion(self):
        """Verify tasks are atomically claimed and complete successfully."""
        self.db.create_task("CAREER_CHECK", 101, {"company": "A"})
        self.db.create_task("CAREER_CHECK", 102, {"company": "B"})

        claimed = self.db.fetch_and_claim_tasks(task_type="CAREER_CHECK", limit=1)
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0]["status"], "RUNNING")
        claimed_id = claimed[0]["id"]

        # Second claim should get the second task, NOT the first
        claimed_second = self.db.fetch_and_claim_tasks(task_type="CAREER_CHECK", limit=1)
        self.assertEqual(len(claimed_second), 1)
        self.assertNotEqual(claimed_second[0]["id"], claimed_id)

        # Complete first task
        self.db.complete_task(claimed_id)
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM tasks WHERE id = ?", (claimed_id,))
            self.assertEqual(cursor.fetchone()["status"], "COMPLETED")

    def test_stale_lease_recovery(self):
        """Verify stale RUNNING tasks are recovered and reset to PENDING."""
        task_id = self.db.create_task("CAREER_CHECK", 201, {"company": "CrashedWorker"})
        # Manually claim and backdate updated_at
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            past = (datetime.utcnow() - timedelta(seconds=600)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("UPDATE tasks SET status = 'RUNNING', updated_at = ? WHERE id = ?", (past, task_id))
            conn.commit()

        # Calling fetch_and_claim_tasks should recover the stale task and claim it
        claimed = self.db.fetch_and_claim_tasks(task_type="CAREER_CHECK", limit=1, lease_seconds=300)
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0]["id"], task_id)
        self.assertEqual(claimed[0]["status"], "RUNNING")

    def test_retry_backoff_and_failure(self):
        """Verify task retries increment and transition to FAILED after max_retries."""
        task_id = self.db.create_task("CAREER_CHECK", 301, {"company": "FlakyAPI"})
        # Fail 3 times (max_retries default is 3)
        self.db.fail_task(task_id, "Network timeout 1", error_category="network")
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, retry_count FROM tasks WHERE id = ?", (task_id,))
            r = cursor.fetchone()
            self.assertEqual(r["status"], "PENDING")
            self.assertEqual(r["retry_count"], 1)

        self.db.fail_task(task_id, "Network timeout 2", error_category="network")
        self.db.fail_task(task_id, "Network timeout 3", error_category="network")

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, retry_count FROM tasks WHERE id = ?", (task_id,))
            r = cursor.fetchone()
            self.assertEqual(r["status"], "FAILED")
            self.assertEqual(r["retry_count"], 3)

    def test_job_match_upsert_and_verification_reset(self):
        """Verify job match upsert retrieves row ID reliably and resets verified on score change."""
        comp_id = self.db.add_company("TestCorp", "testcorp.com", "Germany", "Hardware")
        job_url = "https://testcorp.com/careers/rf-engineer-101"

        # 1. Insert initial job match
        j_id1 = self.db.record_job_match(
            company_id=comp_id,
            company_name="TestCorp",
            country="Germany",
            title="RF Engineer",
            job_url=job_url,
            location="Munich, Germany",
            match_score=75,
            match_reason="Initial technical match",
            evidence_quote="Design RF front-ends.",
            source_url="https://testcorp.com/careers",
        )
        self.assertIsNotNone(j_id1)

        # 2. Mark as verified
        self.db.verify_job_match(j_id1, verified=True, notes="Verified by test")
        verified_jobs = self.db.get_verified_jobs()
        self.assertEqual(len(verified_jobs), 1)

        # 3. Upsert with CHANGED score (85) -> verified must reset to 0
        j_id2 = self.db.record_job_match(
            company_id=comp_id,
            company_name="TestCorp",
            country="Germany",
            title="RF Engineer",
            job_url=job_url,
            location="Munich, Germany",
            match_score=85,
            match_reason="Higher technical match",
            evidence_quote="Design RF front-ends and antennas.",
            source_url="https://testcorp.com/careers",
        )
        self.assertEqual(j_id1, j_id2)

        # Check that verified was reset to 0
        verified_jobs_after = self.db.get_verified_jobs()
        self.assertEqual(len(verified_jobs_after), 0)

        # Check job_scores history has 2 records
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM job_scores WHERE job_match_id = ?", (j_id1,))
            self.assertEqual(cursor.fetchone()[0], 2)

    def test_add_board_employer(self):
        """Verify board employers are saved without faking domains."""
        emp_id = self.db.add_board_employer("Awesome Robotics", domain=None, source="Arbeitnow")
        self.assertGreater(emp_id, 0)

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, domain, source FROM employers WHERE id = ?", (emp_id,))
            row = cursor.fetchone()
            self.assertEqual(row["name"], "Awesome Robotics")
            self.assertIsNone(row["domain"])
            self.assertEqual(row["source"], "Arbeitnow")


if __name__ == "__main__":
    unittest.main()
