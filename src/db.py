"""
Durable SQLite State Machine & Checkpoint Manager.
Ensures crash resilience, idempotency, atomic task claiming, stale lease recovery,
exponential backoff retries, and non-destructive schema migrations.
"""

import contextlib
import hashlib
import json
import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from src.config import config

logger = logging.getLogger("StateDatabase")


def compute_canonical_job_key(job_url: str, company_name: str = "", title: str = "", location: str = "") -> str:
    """
    Computes a canonical deduplication key for a job posting.
    Strips tracking queries (utm_*, gh_src, ref, session_id, etc.).
    Falls back to company + title + location hash if URL is generic.
    """
    if job_url and job_url.startswith("http"):
        parsed = urlparse(job_url.strip())
        # Filter tracking and session parameters
        tracking_keys = {
            "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
            "gh_src", "lever-source", "lever-origin", "ref", "source", "source_id",
            "tracker", "session", "session_id", "mode", "jid", "code"
        }
        filtered_q = [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() not in tracking_keys]
        clean_query = urlencode(filtered_q)
        clean_path = parsed.path.rstrip("/")
        normalized_url = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            clean_path,
            parsed.params,
            clean_query,
            "",  # Strip fragment
        ))
        return f"url:{normalized_url}"

    # Secondary canonical hash
    raw_sig = f"{company_name.lower().strip()}:{title.lower().strip()}:{location.lower().strip()}"
    return f"sig:{hashlib.sha256(raw_sig.encode('utf-8')).hexdigest()[:24]}"


class StateDatabase:
    def __init__(self, db_path: Optional[str] = None):
        self._mem_lock = threading.Lock()
        if db_path == ":memory:":
            self.db_path = Path(":memory:")
            self.is_memory = True
            self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._mem_conn.row_factory = sqlite3.Row
            self._mem_conn.execute("PRAGMA foreign_keys = ON;")
        else:
            self.is_memory = False
            self._mem_conn = None
            self.db_path = Path(db_path) if db_path else config.DEFAULT_DB_PATH
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def __del__(self):
        if getattr(self, "is_memory", False) and getattr(self, "_mem_conn", None):
            try:
                self._mem_conn.close()
            except Exception:
                pass

    @contextlib.contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Connection manager ensuring connections are closed and pragmas are enforced.
        Enables WAL mode, busy timeouts, and foreign key constraints.
        """
        if self.is_memory:
            with self._mem_lock:
                yield self._mem_conn
                try:
                    self._mem_conn.commit()
                except sqlite3.OperationalError:
                    pass
            return

        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 15000;")
            conn.execute("PRAGMA foreign_keys = ON;")
            yield conn
        finally:
            conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """Compatibility wrapper for legacy code."""
        if self.is_memory:
            return self._mem_conn
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 15000;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_database(self):
        """Initializes tables, executes non-destructive migrations, and builds indexes."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Companies Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                domain TEXT NOT NULL UNIQUE,
                country TEXT NOT NULL,
                industry TEXT NOT NULL,
                careers_url TEXT,
                ats_detected TEXT,
                slug TEXT,
                relevance_score INTEGER DEFAULT 0,
                jobs_seen INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                real_domain TEXT,
                hq_country TEXT,
                last_checked_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # 2. Employers Table (For job boards: never invents domains or overwrites careers URLs)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS employers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL UNIQUE,
                domain TEXT,
                source TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # 3. Tasks Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT NOT NULL,
                target_id INTEGER,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                error_message TEXT,
                error_category TEXT,
                next_retry_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # 4. Job Matches Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                company_name TEXT NOT NULL,
                country TEXT NOT NULL,
                title TEXT NOT NULL,
                job_url TEXT NOT NULL UNIQUE,
                canonical_key TEXT,
                location TEXT,
                work_mode TEXT DEFAULT 'On-site',
                match_score INTEGER NOT NULL,
                match_reason TEXT NOT NULL,
                evidence_quote TEXT,
                source_url TEXT NOT NULL,
                seniority TEXT,
                visa_sponsorship TEXT DEFAULT 'unknown',
                clearance_or_citizenship_required INTEGER DEFAULT 0,
                visa_evidence_quote TEXT,
                eligible INTEGER DEFAULT 1,
                eligibility_reason TEXT,
                description_hash TEXT,
                description_text TEXT,
                classifier_engine TEXT,
                classifier_model TEXT,
                prompt_version TEXT,
                verifier_engine TEXT,
                still_open INTEGER DEFAULT 1,
                still_open_checked_at TIMESTAMP,
                first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                verified INTEGER DEFAULT 0,
                verification_notes TEXT,
                synced_to_sheet INTEGER DEFAULT 0,
                FOREIGN KEY (company_id) REFERENCES companies(id)
            )
            """)

            # 5. Contacts Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                company_name TEXT NOT NULL,
                email TEXT NOT NULL,
                role_department TEXT,
                source_url TEXT NOT NULL,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                verified INTEGER DEFAULT 0,
                synced_to_sheet INTEGER DEFAULT 0,
                FOREIGN KEY (company_id) REFERENCES companies(id),
                UNIQUE(company_id, email)
            )
            """)

            # 6. Job Scores History Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_match_id INTEGER NOT NULL,
                classifier_version TEXT NOT NULL,
                classifier_model TEXT,
                score INTEGER NOT NULL,
                work_mode TEXT,
                evidence_quote TEXT,
                reasons TEXT,
                scored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (job_match_id) REFERENCES job_matches(id)
            )
            """)

            # 7. Observability Traces
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                agent_name TEXT NOT NULL,
                step INTEGER NOT NULL,
                action TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                estimated_cost_usd REAL DEFAULT 0.0,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # 8. Run Failures & Diagnostic Errors
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS run_failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stage TEXT NOT NULL,
                error_category TEXT NOT NULL,
                message TEXT NOT NULL,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            conn.commit()
            self._run_migrations(conn)

    def _run_migrations(self, conn: sqlite3.Connection):
        """Non-destructive migrations adding missing columns and indexes."""
        cursor = conn.cursor()

        # Check existing columns in companies
        cursor.execute("PRAGMA table_info(companies)")
        comp_cols = {row["name"] for row in cursor.fetchall()}
        missing_comp_cols = {
            "slug": "TEXT",
            "relevance_score": "INTEGER DEFAULT 0",
            "jobs_seen": "INTEGER DEFAULT 0",
            "status": "TEXT DEFAULT 'active'",
            "real_domain": "TEXT",
            "hq_country": "TEXT",
            "last_checked_at": "TIMESTAMP",
        }
        for col, col_type in missing_comp_cols.items():
            if col not in comp_cols:
                cursor.execute(f"ALTER TABLE companies ADD COLUMN {col} {col_type}")

        # Check existing columns in tasks
        cursor.execute("PRAGMA table_info(tasks)")
        task_cols = {row["name"] for row in cursor.fetchall()}
        missing_task_cols = {
            "error_category": "TEXT",
            "next_retry_at": "TIMESTAMP",
        }
        for col, col_type in missing_task_cols.items():
            if col not in task_cols:
                cursor.execute(f"ALTER TABLE tasks ADD COLUMN {col} {col_type}")

        # Check existing columns in job_matches
        cursor.execute("PRAGMA table_info(job_matches)")
        jm_cols = {row["name"] for row in cursor.fetchall()}
        missing_jm_cols = {
            "canonical_key": "TEXT",
            "seniority": "TEXT",
            "visa_sponsorship": "TEXT DEFAULT 'unknown'",
            "clearance_or_citizenship_required": "INTEGER DEFAULT 0",
            "visa_evidence_quote": "TEXT",
            "eligible": "INTEGER DEFAULT 1",
            "eligibility_reason": "TEXT",
            "description_hash": "TEXT",
            "description_text": "TEXT",
            "classifier_engine": "TEXT",
            "classifier_model": "TEXT",
            "prompt_version": "TEXT",
            "verifier_engine": "TEXT",
            "still_open": "INTEGER DEFAULT 1",
            "still_open_checked_at": "TIMESTAMP",
            "first_seen_at": "TIMESTAMP",
            "last_seen_at": "TIMESTAMP",
        }
        for col, col_type in missing_jm_cols.items():
            if col not in jm_cols:
                cursor.execute(f"ALTER TABLE job_matches ADD COLUMN {col} {col_type}")

        # Relax NOT NULL on evidence_quote if legacy schema enforces it
        cursor.execute("PRAGMA table_info(job_matches)")
        jm_info = {row["name"]: row for row in cursor.fetchall()}
        if "evidence_quote" in jm_info and jm_info["evidence_quote"]["notnull"] == 1:
            cursor.execute("PRAGMA foreign_keys = OFF;")
            cols = [row["name"] for row in jm_info.values()]
            col_list = ", ".join(cols)
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='job_matches'")
            create_sql = cursor.fetchone()[0]
            new_sql = create_sql.replace("evidence_quote TEXT NOT NULL", "evidence_quote TEXT").replace("CREATE TABLE job_matches", "CREATE TABLE job_matches_v2", 1)
            cursor.execute(new_sql)
            cursor.execute(f"INSERT INTO job_matches_v2 ({col_list}) SELECT {col_list} FROM job_matches")
            cursor.execute("DROP TABLE job_matches")
            cursor.execute("ALTER TABLE job_matches_v2 RENAME TO job_matches")
            cursor.execute("PRAGMA foreign_keys = ON;")

        # Populate canonical_key for existing rows if null
        cursor.execute("SELECT id, job_url, company_name, title, location FROM job_matches WHERE canonical_key IS NULL")
        unkeyed = cursor.fetchall()
        for r in unkeyed:
            ck = compute_canonical_job_key(r["job_url"], r["company_name"], r["title"], r["location"] or "")
            cursor.execute("UPDATE job_matches SET canonical_key = ? WHERE id = ?", (ck, r["id"]))

        # Deduplicate tasks before creating unique index
        cursor.execute("""
        DELETE FROM tasks
        WHERE id NOT IN (
            SELECT MIN(id) FROM tasks
            GROUP BY task_type, target_id
        )
        """)

        # Deduplicate job_matches on canonical_key if duplicates exist
        cursor.execute("""
        DELETE FROM job_matches
        WHERE id NOT IN (
            SELECT MIN(id) FROM job_matches
            GROUP BY canonical_key
        )
        """)

        # Create Indexes
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_type_target ON tasks(task_type, target_id);")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_job_matches_canonical ON job_matches(canonical_key);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_matches_verified ON job_matches(verified);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_matches_country ON job_matches(country);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_matches_company_id ON job_matches(company_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status_type ON tasks(status, task_type);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_ats ON companies(ats_detected);")

        conn.commit()

    # =========================================================================
    # Task Queue Operations (Atomic Claims, Stale Lease Recovery, Exponential Backoff)
    # =========================================================================

    def create_task(self, task_type: str, target_id: int, payload: Dict[str, Any]) -> int:
        """
        Idempotent task insertion. If a task with (task_type, target_id) already exists,
        ignores insertion and returns the existing task ID.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR IGNORE INTO tasks (task_type, target_id, payload, status)
            VALUES (?, ?, ?, 'PENDING')
            """, (task_type, target_id, json.dumps(payload)))
            conn.commit()

            cursor.execute("SELECT id FROM tasks WHERE task_type = ? AND target_id = ?", (task_type, target_id))
            row = cursor.fetchone()
            return row["id"] if row else 0

    def fetch_and_claim_tasks(
        self,
        task_type: Optional[str] = None,
        limit: int = 10,
        lease_seconds: int = 300,
    ) -> List[Dict[str, Any]]:
        """
        Atomically claims up to `limit` pending tasks.
        Recovers stale RUNNING tasks whose lease has expired before claiming.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Recover stale RUNNING tasks
            stale_threshold = datetime.utcnow() - timedelta(seconds=lease_seconds)
            cursor.execute("""
            UPDATE tasks
            SET status = CASE WHEN retry_count < max_retries THEN 'PENDING' ELSE 'FAILED' END,
                error_message = 'Task lease expired / worker crashed',
                updated_at = CURRENT_TIMESTAMP
            WHERE status = 'RUNNING' AND updated_at < ?
            """, (stale_threshold.strftime("%Y-%m-%d %H:%M:%S"),))

            # 2. Atomic Claim with RETURNING
            query_cond = "status = 'PENDING'"
            params: List[Any] = []
            if task_type:
                query_cond += " AND task_type = ?"
                params.append(task_type)

            cursor.execute(f"""
            WITH claimed AS (
                SELECT id FROM tasks
                WHERE {query_cond}
                ORDER BY id ASC
                LIMIT ?
            )
            UPDATE tasks
            SET status = 'RUNNING', updated_at = CURRENT_TIMESTAMP
            WHERE id IN (SELECT id FROM claimed)
            RETURNING *
            """, (*params, limit))

            rows = cursor.fetchall()
            conn.commit()

            tasks = []
            for r in rows:
                d = dict(r)
                d["payload"] = json.loads(d["payload"]) if isinstance(d["payload"], str) else d["payload"]
                tasks.append(d)
            return tasks

    def fetch_pending_tasks(self, task_type: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Legacy compatibility wrapper calling atomic claim."""
        return self.fetch_and_claim_tasks(task_type=task_type, limit=limit)

    def complete_task(self, task_id: int):
        """Marks a claimed task as COMPLETED."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE tasks SET status = 'COMPLETED', updated_at = CURRENT_TIMESTAMP WHERE id = ?
            """, (task_id,))
            conn.commit()

    def fail_task(self, task_id: int, error_message: str, error_category: str = "general"):
        """
        Records failure with exponential backoff.
        If retry_count < max_retries, sets back to PENDING; otherwise FAILED.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT retry_count, max_retries FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if not row:
                return

            retries = row["retry_count"] + 1
            max_r = row["max_retries"]

            if retries >= max_r:
                status = "FAILED"
                next_retry = None
            else:
                status = "PENDING"
                # Exponential backoff (e.g. 10s, 30s, 90s)
                delay = 10 * (3 ** (retries - 1))
                next_retry = (datetime.utcnow() + timedelta(seconds=delay)).strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("""
            UPDATE tasks
            SET status = ?, retry_count = ?, error_message = ?, error_category = ?,
                next_retry_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """, (status, retries, error_message, error_category, next_retry, task_id))

            # Record failure diagnostic
            cursor.execute("""
            INSERT INTO run_failures (stage, error_category, message, details)
            VALUES ('TASK_EXECUTION', ?, ?, ?)
            """, (error_category, f"Task {task_id} failed: {error_message}", json.dumps({"retries": retries})))

            conn.commit()

    def update_task_status(self, task_id: int, status: str, error_message: Optional[str] = None):
        """Generic task status update for backward compatibility."""
        if status == "COMPLETED":
            self.complete_task(task_id)
        elif status == "FAILED":
            self.fail_task(task_id, error_message or "Unknown failure")
        else:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                UPDATE tasks SET status = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?
                """, (status, error_message, task_id))
                conn.commit()

    # =========================================================================
    # Job Match Operations (Canonical Upsert, Score History, Reset on Change)
    # =========================================================================

    def record_job_match(
        self,
        company_id: int,
        company_name: str,
        country: str,
        title: str,
        job_url: str,
        location: str,
        match_score: int,
        match_reason: str,
        evidence_quote: Optional[str],
        source_url: str,
        work_mode: str = "On-site",
        seniority: Optional[str] = None,
        visa_sponsorship: str = "unknown",
        clearance_or_citizenship_required: bool = False,
        visa_evidence_quote: Optional[str] = None,
        eligible: bool = True,
        eligibility_reason: Optional[str] = None,
        description_text: Optional[str] = None,
        classifier_engine: Optional[str] = None,
        classifier_model: Optional[str] = None,
        prompt_version: Optional[str] = None,
    ) -> Optional[int]:
        """
        Idempotent job recording keyed on canonical_key.
        Retrieves ID reliably via SELECT.
        Resets verified=0 if score or evidence changed.
        Appends entry into job_scores history.
        """
        canonical_key = compute_canonical_job_key(job_url, company_name, title, location)
        desc_hash = hashlib.sha256(description_text.encode("utf-8")).hexdigest() if description_text else None

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Check existing match
            cursor.execute("SELECT id, match_score, evidence_quote, verified FROM job_matches WHERE canonical_key = ?", (canonical_key,))
            existing = cursor.fetchone()

            reset_verified = 0
            if existing:
                job_id = existing["id"]
                # If score or evidence changed, reset verified to 0
                if existing["match_score"] != match_score or existing["evidence_quote"] != evidence_quote:
                    reset_verified = 0
                else:
                    reset_verified = existing["verified"]

                cursor.execute("""
                UPDATE job_matches SET
                    country = ?, location = ?, work_mode = ?, match_score = ?,
                    match_reason = ?, evidence_quote = ?, source_url = ?,
                    seniority = ?, visa_sponsorship = ?, clearance_or_citizenship_required = ?,
                    visa_evidence_quote = ?, eligible = ?, eligibility_reason = ?,
                    description_hash = COALESCE(?, description_hash),
                    description_text = COALESCE(?, description_text),
                    classifier_engine = ?, classifier_model = ?, prompt_version = ?,
                    last_seen_at = CURRENT_TIMESTAMP, verified = ?
                WHERE id = ?
                """, (
                    country, location, work_mode, match_score,
                    match_reason, evidence_quote, source_url,
                    seniority, visa_sponsorship, 1 if clearance_or_citizenship_required else 0,
                    visa_evidence_quote, 1 if eligible else 0, eligibility_reason,
                    desc_hash, description_text,
                    classifier_engine, classifier_model, prompt_version or config.PROMPT_VERSION,
                    reset_verified, job_id
                ))
            else:
                cursor.execute("""
                INSERT INTO job_matches (
                    company_id, company_name, country, title, job_url, canonical_key,
                    location, work_mode, match_score, match_reason, evidence_quote,
                    source_url, seniority, visa_sponsorship, clearance_or_citizenship_required,
                    visa_evidence_quote, eligible, eligibility_reason, description_hash,
                    description_text, classifier_engine, classifier_model, prompt_version,
                    verified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """, (
                    company_id, company_name, country, title, job_url, canonical_key,
                    location, work_mode, match_score, match_reason, evidence_quote,
                    source_url, seniority, visa_sponsorship, 1 if clearance_or_citizenship_required else 0,
                    visa_evidence_quote, 1 if eligible else 0, eligibility_reason,
                    desc_hash, description_text, classifier_engine, classifier_model,
                    prompt_version or config.PROMPT_VERSION
                ))
                cursor.execute("SELECT id FROM job_matches WHERE canonical_key = ?", (canonical_key,))
                row = cursor.fetchone()
                job_id = row["id"] if row else None

            if job_id:
                # Append to job_scores history table
                cursor.execute("""
                INSERT INTO job_scores (job_match_id, classifier_version, classifier_model, score, work_mode, evidence_quote, reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    job_id,
                    prompt_version or config.PROMPT_VERSION,
                    classifier_model,
                    match_score,
                    work_mode,
                    evidence_quote,
                    match_reason
                ))

            conn.commit()
            return job_id

    def verify_job_match(
        self,
        job_id: int,
        verified: bool,
        notes: str,
        verifier_engine: str = "RULE_BASED",
        still_open: bool = True
    ):
        """Updates verification outcome and verifier engine provenance."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE job_matches
            SET verified = ?, verification_notes = ?, verifier_engine = ?,
                still_open = ?, still_open_checked_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """, (1 if verified else 0, notes, verifier_engine, 1 if still_open else 0, job_id))
            conn.commit()

    def get_verified_jobs(self, country: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns all verified, eligible jobs (optionally filtered by country)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if country:
                cursor.execute("""
                SELECT * FROM job_matches
                WHERE verified = 1 AND eligible = 1 AND still_open = 1 AND country = ?
                ORDER BY match_score DESC
                """, (country,))
            else:
                cursor.execute("""
                SELECT * FROM job_matches
                WHERE verified = 1 AND eligible = 1 AND still_open = 1
                ORDER BY match_score DESC
                """)
            return [dict(row) for row in cursor.fetchall()]

    def get_ineligible_jobs(self) -> List[Dict[str, Any]]:
        """Returns jobs rejected due to hard filters (visa/ITAR, seniority, outside target countries)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM job_matches
            WHERE eligible = 0
            ORDER BY checked_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]

    # =========================================================================
    # Company Operations & Employer Registry
    # =========================================================================

    def add_company(
        self,
        name: str,
        domain: str,
        country: str,
        industry: str,
        careers_url: str = "",
        ats_detected: Optional[str] = None,
        slug: Optional[str] = None,
    ) -> int:
        """Registers or updates a company domain in the registry."""
        norm_domain = domain.lower().strip()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO companies (name, domain, country, industry, careers_url, ats_detected, slug)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(domain) DO UPDATE SET
                careers_url = COALESCE(NULLIF(excluded.careers_url, ''), companies.careers_url),
                ats_detected = COALESCE(NULLIF(excluded.ats_detected, ''), companies.ats_detected),
                slug = COALESCE(NULLIF(excluded.slug, ''), companies.slug)
            """, (name, norm_domain, country, industry, careers_url, ats_detected, slug))
            conn.commit()

            cursor.execute("SELECT id FROM companies WHERE domain = ?", (norm_domain,))
            row = cursor.fetchone()
            return row["id"] if row else 0

    def bulk_add_companies(self, companies: List[Dict[str, Any]]) -> int:
        """Registers multiple companies efficiently in a single database transaction."""
        if not companies:
            return 0
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for comp in companies:
                norm_domain = comp.get("domain", "").lower().strip()
                if not norm_domain:
                    continue
                name = comp.get("name", "")
                country = comp.get("country", "")
                industry = comp.get("industry", "")
                careers_url = comp.get("careers_url", "")
                ats = comp.get("ats_detected") or comp.get("ats") or comp.get("ats_hint")
                slug = comp.get("slug")
                cursor.execute("""
                INSERT INTO companies (name, domain, country, industry, careers_url, ats_detected, slug)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(domain) DO UPDATE SET
                    careers_url = COALESCE(NULLIF(excluded.careers_url, ''), companies.careers_url),
                    ats_detected = COALESCE(NULLIF(excluded.ats_detected, ''), companies.ats_detected),
                    slug = COALESCE(NULLIF(excluded.slug, ''), companies.slug)
                """, (name, norm_domain, country, industry, careers_url, ats, slug))
            conn.commit()
            cursor.execute("SELECT COUNT(*) AS cnt FROM companies")
            row = cursor.fetchone()
            return row["cnt"] if row else len(companies)

    def add_board_employer(self, name: str, domain: Optional[str], source: str) -> int:
        """
        Stores an employer found on a job board in the employers table.
        Never fabricates fake domains or overwrites careers URLs.
        """
        norm_name = name.lower().strip()
        norm_domain = domain.lower().strip() if domain else None
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO employers (name, normalized_name, domain, source)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(normalized_name) DO UPDATE SET
                domain = COALESCE(excluded.domain, employers.domain)
            """, (name, norm_name, norm_domain, source))
            conn.commit()

            cursor.execute("SELECT id FROM employers WHERE normalized_name = ?", (norm_name,))
            row = cursor.fetchone()
            return row["id"] if row else 0

    def get_company_count(self) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM companies")
            return cursor.fetchone()[0]

    def get_companies(self, country: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if country:
                cursor.execute("SELECT * FROM companies WHERE country = ?", (country,))
            else:
                cursor.execute("SELECT * FROM companies")
            return [dict(row) for row in cursor.fetchall()]

    def get_prioritized_companies(
        self,
        keywords: Optional[List[str]] = None,
        limit: int = 150,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if keywords:
                clauses = []
                params = []
                for kw in keywords:
                    clauses.append("(name LIKE ? OR industry LIKE ? OR domain LIKE ?)")
                    params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])
                where_sql = " OR ".join(clauses)
                query = f"""
                SELECT * FROM companies
                WHERE {where_sql}
                ORDER BY
                    CASE WHEN industry LIKE '%RF%' OR industry LIKE '%Hardware%' OR industry LIKE '%Semiconductor%' THEN 1 ELSE 2 END,
                    id ASC
                LIMIT ? OFFSET ?
                """
                params.extend([limit, offset])
                cursor.execute(query, params)
            else:
                cursor.execute("SELECT * FROM companies ORDER BY id ASC LIMIT ? OFFSET ?", (limit, offset))
            return [dict(row) for row in cursor.fetchall()]

    # =========================================================================
    # Contact Operations & Observability Traces
    # =========================================================================

    def record_contact(
        self, company_id: int, company_name: str, email: str, role_dept: str, source_url: str
    ) -> Optional[int]:
        norm_email = email.lower().strip()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                INSERT INTO contacts (company_id, company_name, email, role_department, source_url, verified)
                VALUES (?, ?, ?, ?, ?, 0)
                ON CONFLICT(company_id, email) DO UPDATE SET
                    source_url = excluded.source_url
                """, (company_id, company_name, norm_email, role_dept, source_url))
                conn.commit()
                cursor.execute("SELECT id FROM contacts WHERE company_id = ? AND email = ?", (company_id, norm_email))
                row = cursor.fetchone()
                return row["id"] if row else None
            except Exception:
                return None

    def log_trace(
        self,
        task_id: Optional[int],
        agent_name: str,
        step: int,
        action: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        details: Optional[str] = None,
    ):
        """Populates the traces table with real token usage and cost accounting."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO traces (task_id, agent_name, step, action, input_tokens, output_tokens, estimated_cost_usd, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (task_id, agent_name, step, action, input_tokens, output_tokens, cost_usd, details))
            conn.commit()

    def get_run_metrics(self) -> Dict[str, Any]:
        """Calculates comprehensive run telemetry for the manager."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM companies")
            total_companies = cursor.fetchone()[0]

            cursor.execute("SELECT count(*) FROM job_matches")
            total_jobs = cursor.fetchone()[0]

            cursor.execute("SELECT count(*) FROM job_matches WHERE verified = 1 AND eligible = 1")
            verified_jobs = cursor.fetchone()[0]

            cursor.execute("SELECT count(*) FROM job_matches WHERE eligible = 0")
            ineligible_jobs = cursor.fetchone()[0]

            cursor.execute("SELECT count(*) FROM job_matches WHERE still_open = 0")
            dead_jobs = cursor.fetchone()[0]

            cursor.execute("SELECT SUM(input_tokens), SUM(output_tokens), SUM(estimated_cost_usd) FROM traces")
            t_row = cursor.fetchone()
            in_tokens = t_row[0] or 0
            out_tokens = t_row[1] or 0
            total_cost = t_row[2] or 0.0

            cursor.execute("SELECT classifier_engine, count(*) FROM job_matches GROUP BY classifier_engine")
            engines = {row[0] or "Unknown": row[1] for row in cursor.fetchall()}

            return {
                "total_companies": total_companies,
                "total_jobs_seen": total_jobs,
                "verified_jobs": verified_jobs,
                "ineligible_jobs": ineligible_jobs,
                "dead_jobs": dead_jobs,
                "input_tokens": in_tokens,
                "output_tokens": out_tokens,
                "estimated_cost_usd": total_cost,
                "engines_used": engines,
            }
