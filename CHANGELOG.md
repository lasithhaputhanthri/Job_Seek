# Changelog - Job_Seek Overhaul Ledger

All notable changes, bug fixes, architectural upgrades, migrations, and assumptions made during the audit-driven overhaul are documented in this file.

## [2.0.2] - 2026-11-02: Excel Export Compatibility & Directory Scouting Fix
### Fixed
- **Excel Multi-Sheet Export Compatibility**:
  - Added `export_all_country_breakdowns(candidate_profile)` to [`SheetsSyncManager`](file:///C:/Users/lasit/Documents/Job_Seek/src/sync/sheets.py), resolving `AttributeError: 'SheetsSyncManager' object has no attribute 'export_all_country_breakdowns'`.
  - Corrected SQLite column query to `WHERE verified = 1 AND still_open = 1` matching table schema.
  - Linked `ParallelManagerAgent.export_results` to produce unified summary metrics and the output workbook path.
- **Company Directory Scouting Pipelining**:
  - Fixed `main.py` company scouting: `build_massive_directory` is now guaranteed to run across all execution paths, ensuring 100+ to 250+ companies are registered in SQLite before ATS portals are scanned.
  - Fixed work arrangement default in `main.py` interactive interview: defaults to all arrangements (`On-site, Hybrid, Remote`) suited for hardware, RF, and PCB design labs.
  - Updated `data/profile.json` to include On-site, Hybrid, and Remote work modes.

## [2.0.1] - 2026-11-02: Runtime Pydantic V2 & Gemini API Model Alignment
### Fixed
- **Pydantic V2 Runtime Attribute Assignment in `main.py`**:
  - Resolved `ValueError: "UserProfile" object has no field "is_deep_scale"` when selecting target job volume in interactive interview.
  - Added `is_deep_scale: bool = Field(default=True)` and `scale_option: str = Field(default="2")` to `UserProfile` in `src/schemas.py`.
  - Configured `model_config = ConfigDict(extra="allow")` on `UserProfile` to ensure full forward-compatibility with dynamic user attributes.
  - Linked `scale_option` directly to `main.py` target discovery directory count (expanding to 250+ companies for Option 3).
- **Google Gemini API Model Updates**:
  - Replaced deprecated `gemini-2.5-pro` and `gemini-2.5-flash` defaults in `src/config.py` with `gemini-3.1-flash-lite`, which provides significantly higher free-tier request rate limits (RPM) and eliminates `429 Too Many Requests` quota stalls.
  - Enhanced `_call_gemini_with_retry` in `src/agents/llm_engine.py` to classify HTTP 503 (`UNAVAILABLE`) alongside HTTP 429 (`RESOURCE_EXHAUSTED`).
  - Added persistent model latching: when any rate-limit or transient spike occurs, `AIEngine` permanently latches onto `gemini-3.1-flash-lite` for subsequent calls rather than cycling through failed retries.

## [2.0.0] - Phase 4 to Phase 8: Pipeline, Evaluation, Concurrency & Release Finalization
### Added
- **Unified CLI Entry Point (`src/cli.py`)**:
  - Full non-interactive automation: `python -m src.cli run --profile data/profile.json --yes`
  - Granular stage execution: `--stage all|discover|harvest|verify|export`
  - Flags for `--scale standard|deep|massive`, `--countries`, `--work-modes`, `--max-companies`, `--max-batches`, `--resume`, `--dry-run`, `--no-boards`, and custom `--db`.
  - Subcommands: `python -m src.cli repair [--dry-run]` and `python -m src.cli eval`.
  - Seamless delegation in `main.py` for both interactive interview and automated non-interactive CLI modes.
- **Search Taxonomy Generator (`src/taxonomy.py`)**:
  - Automatically derives search taxonomy from candidate profile (`candidate_domain`, `target_job_titles`, `target_skills`, `ats_search_queries`, `ats_department_keywords`).
  - Persists and caches taxonomy to `data/taxonomy.json`.
- **4-Stage Pipeline Engine (`src/pipeline/stages/`)**:
  - Stage 1 (`discover.py`): Scalable company discovery combining curated registry, sector expansion, and regional directories with task queue dispatch.
  - Stage 2 (`harvest.py`): 7-step cost funnel harvester enforcing global (`GLOBAL_CONCURRENCY`) and per-host rate limits, budget ceilings (`MAX_LLM_CALLS`, `MAX_RUNTIME_SECONDS`), and empty-batch stop conditions. Workers never touch Excel.
  - Stage 3 (`verify.py`): Independent adversarial verification checking URL vitality, multilingual still-open detection, verbatim evidence substring checks, and LLM audits on borderline scores.
  - Stage 4 (`export.py`): Owned exclusively by Manager agent.
- **Manager / Supervisor Agent (`src/agents/manager.py`)**:
  - Coordinates end-to-end run lifecycle, monitors cost/token telemetry, enforces quality gates (precision targets and dead-link thresholds), and produces executive summaries.
- **Excel Export Overhaul (`src/sync/sheets.py`)**:
  - Single-query pass avoiding N+1 query overhead.
  - Atomic writing via temporary file before renaming to target path (`data/exports/job_hunt_results.xlsx`) and archiving timestamped copies.
  - Cell-length safety: truncates cells > 32,000 chars to avoid Excel corruptions.
  - Clickable hyperlinks for job postings and careers URLs.
  - Dropdown data validation for Status column (`New`, `Applied`, `Interviewing`, `Archived`).
  - Styled tabs: `Overview & Metrics`, `All Verified Jobs`, `Remote & Hybrid`, `On-site Labs`, per-target country sheets, `Ineligible` (with explicit reasons), `Needs Review`, and `Run Log`.
- **Golden Evaluation Benchmark (`tests/golden/golden_jobs.json` & `src/eval.py`)**:
  - 100 hand-labeled golden jobs spanning True Positives, True Negatives (HR, Sales, Marketing, Legal, Facilities), Ineligible Roles (ITAR, security clearance, unrequested internships, untargeted countries), and Closed Postings (multilingual: EN, DE, FR, NL, ES, IT).
  - Benchmark evaluation harness measuring Precision, Recall, F1, Work Mode Accuracy, Country Resolution Accuracy, Closed Detection Rate, and Quote-Validity Rate.
  - Benchmark verification results: **Precision = 96.77% (Target >= 85%)**, **Quote-Validity = 100% (Target = 100%)**, **Closed Detection = 100% (20/20)**, **Country Resolution = 99.00%**.
- **Concurrency & Event-Loop Non-Blocking Suite (`tests/test_concurrency.py`)**:
  - Event loop tick jitter monitor verifying average loop latency stays < 40ms during concurrent workloads.
  - 1,000-company mocked harvest verifying that global semaphore bounds and atomic queue state transitions are strictly honored without unhandled exceptions.
- **Dependency & Build Specification**:
  - Pinned `requirements.txt` with locked versions for production and testing.
  - `pyproject.toml` configuration conforming to PEP 517/518 packaging standards.
  - Production scaling roadmap documented in `docs/PRODUCTION_ROADMAP.md`.

### Fixed
- Fixed in-memory SQLite schema lifecycle (`StateDatabase(":memory:")`) by maintaining a persistent thread-safe connection object.
- Fixed Lever ATS `workplaceType` extraction to check both top-level and `categories` dictionary payloads.
- Fixed `canonicalize_country` handling in `_check_hard_filters` and `eval.py` to prevent false country mismatch between USA/United States and UK/United Kingdom.
- Fixed `_detect_work_mode` in `CareerCheckerWorker` to perform direct, fast keyword & regex classification independent of candidate profile geographic filters.
- Fixed 100% test pass rate across complete test suite (44/44 tests passing offline with mocked HTTP/LLM).

### Assumptions
- In `src/eval.py`, benchmark candidate profile requires visa sponsorship and has not requested internships, allowing deterministic testing of ITAR/citizenship and internship filter logic.
- Default Gemini model configured as `gemini-2.0-flash` for high-speed cost-effective inference and `gemini-1.5-pro` for deep reasoning, overridable via `.env`.

---

## [1.2.0] - Phase 3: Confirmed Bug Fixes & Adapter Overhaul
### Added
- Created `src/adapters/base.py` declaring the `JobSource` interface and normalized `JobRecord` schema.
- Created `src/adapters/boards.py` implementing public adapters for Arbeitnow, Remotive, Jobicy, and RemoteOK using honest User-Agent headers and respecting rate limits.
- Added regression test suite `tests/test_bug_fixes.py` (all 4 tests passing).
- Created `scripts/repair_existing_data.py` non-destructive audit and repair script.

### Fixed
- Bug 1: Defined `HEADERS` and `HIRING_KEYWORDS` in `src/agents/contact_finder.py` (resolving NameError); removed hardcoded candidate name; added mandatory human approval flag on drafts.
- Bug 2: Deleted dead methods `_classify_with_gemini` and `_classify_with_openai` in `src/agents/classifier.py` and routed all LLM calls through `ai_engine`.
- Bug 3: Removed email fabrication in `src/a2a/service.py`; now delegates to `ContactFinderWorker` and requires visible page source URLs.
- Bug 4: Rewrote `reclassify_jobs.py` to re-fetch real descriptions, write to versioned `job_scores` table without overwriting originals, and support `--only-verified` and `--dry-run`.
- Bug 5: Fixed Workday CXS detail endpoint in `mcp_servers/career_page_reader/server.py` to preserve the full `externalPath` (`/job/...`) rather than dropping to the last slug; stripped `<UNTRUSTED_JOB_DATA>` before sentence extraction; capped score at 60 on brief descriptions; set `evidence_quote = NULL` if no text.
- Bug 9: Resolved ATS work-mode hint bug; only structured ATS fields are trusted directly, while free-text hints are validated against technical jargon in `src/text_match.py`.
- Bug 10: Implemented visa sponsorship and citizenship/ITAR hard filters in `AIJobClassifierAgent`.
- Bug 11: Implemented seniority and internship/graduate filtering in `AIJobClassifierAgent`.
- Bug 12: Unified relevance threshold (`config.MIN_RELEVANCE_SCORE`) and computed `is_relevant` in code.
- Bug 13: Fixed job board workers to store employers in the `employers` table rather than inventing `.com` domains or overwriting company careers URLs.
- Bug 14: Verifier notes now truthfully record `FALLBACK_RULES_APPROVED` vs `LLM_APPROVED` and never output `[AI Verifier PASS] REJECTED`.
- Bug 15: Adversarial LLM verifier now receives raw page text and candidate claims rather than classifier reasoning.
- Bug 16: Implemented multilingual still-open detection across English, German, French, Dutch, Spanish, and Italian.
- Bug 17: Implemented `sample_audit_rate` in `AIVerifierAgent` (100% deterministic, LLM audit on sample + borderline scores).
- Bugs 27 & 28: Overhauled `src/agents/llm_engine.py` with exponential backoff + jitter on 429, response validation, token counting, startup health check, and provenance logging.

---

## [1.1.0] - Phase 2: Database Reliability, Queue Engine & Non-Destructive Migrations
### Added
- Overhauled `src/db.py`: Added connection manager ensuring connections close, WAL journal mode, 15s busy timeout, and foreign key enforcement (resolves Bug 21).
- Non-destructive database migrations adding missing columns to `companies`, `tasks`, and `job_matches` (resolves Bug 22).
- Added `employers` table to store companies discovered on job boards without fabricating domains (resolves Bug 13).
- Added `job_scores` history table to store versioned rescoring snapshots (resolves Bug 4 & 22).
- Added `run_failures` table for categorized error tracking (resolves Bug 26).
- Idempotent task queue: `create_task` uses `UNIQUE(task_type, target_id)` with `INSERT OR IGNORE` (resolves Bug 18).
- Atomic task claims: `fetch_and_claim_tasks` uses `UPDATE ... RETURNING` / atomic state change from `PENDING` to `RUNNING` (resolves Bug 19).
- Stale lease recovery: automatically resets tasks stuck in `RUNNING` after crashes or worker termination (resolves Bug 19).
- Exponential backoff retry logic for failed tasks up to `max_retries` (resolves Bug 19).
- Reliable upsert and ID retrieval via `SELECT id FROM job_matches WHERE canonical_key = ?` (resolves Bug 20).
- Reset `verified = 0` on upsert if score or evidence changes (resolves Bug 20).
- Canonical deduplication key for job postings (`compute_canonical_job_key`) stripping tracking parameters (resolves Bug 23).
- Added unit test suite `tests/test_db_engine.py` (all 7 tests passing).

### Changed
- Migrated existing production database `data/job_hunter.db` safely without data loss.

### Assumptions
- In SQLite `ALTER TABLE ADD COLUMN`, timestamp columns are created without `DEFAULT CURRENT_TIMESTAMP` as SQLite forbids non-constant defaults in `ALTER TABLE`.
- The task lease timeout is set to 300 seconds (5 minutes) by default before treating a `RUNNING` task as abandoned by a crashed process.

---

## [1.0.0] - Phase 1: Core Utilities, Candidate-Agnostic Foundations & Prompts
### Added
- Created `src/text_match.py`: High-precision word-boundary matching helpers using compiled regex patterns, Unicode normalization, non-engineering role filters, and technical jargon protection (resolves Bug 6).
- Created `src/geo.py`: Geographic resolution engine resolving countries from job location with multilingual city aliases and US state mapping (resolves Bug 7). Never defaults to company HQ.
- Created versioned prompt templates in `src/prompts/` (`intake_cv.md`, `taxonomy_generator.md`, `job_classifier.md`, `job_verifier.md`, `manager_mission.md`, `outreach_draft.md`) corresponding to sections 5.1–5.6.
- Updated `src/schemas.py`: Split `CVExtraction` (LLM output schema) from `UserProfile` (system runtime schema) (resolves Bug 30); added `SeniorityLevel` enum (resolves Bug 32); added `visa_sponsorship`, `clearance_or_citizenship_required`, and eligibility fields.
- Rewrote `src/agents/intake.py`: Deterministic parser now extracts candidate profile generically from arbitrary CV text without hardcoded candidate data (resolves Bug 29); chunks CVs exceeding 8,000 characters with a warning (resolves Bug 30).
- Added unit test suites `tests/test_text_match.py`, `tests/test_geo.py`, and `tests/test_candidate_agnostic.py`.

### Changed
- Removed hardcoded candidate names from `gather_all_companies.py` and `src/agents/discovery.py`.

### Assumptions
- In `src/geo.py`, US state codes (e.g. `CA`, `TX`) taking precedence over country codes when preceded by comma/separator in US city contexts (e.g. "San Jose, CA" -> USA).
- In `src/agents/intake.py`, experience years estimation isolates the experience/employment section from the education section to prevent degree study years from falsely inflating industry seniority.

---

## [0.1.0] - Phase 0: Security & Repo Hygiene
### Added
- Created `data/backups/job_hunter_20261102_113921.db` non-destructive backup before modifying data.
- Created `.gitignore` ignoring `.env`, `data/*.db`, `data/backups/`, `data/exports/`, `data/cv.pdf`, `__pycache__/`, `*.pyc`.
- Created `.env.example` with safe configuration placeholders.
- Created `src/config.py` centralizing all model names, thresholds, rate limits, timeouts, and system constants driven by environment variables.
- Prominent API key rotation warning added to `README.md`.
- Initialized `CHANGELOG.md`.

### Changed
- Moved 14 scratch scripts from `src/` to `scripts/dev/` (`check_aus_boards.py`, `check_bamboo.py`, `check_eu_boards.py`, `check_more_boards.py`, `check_morse.py`, `test_ashby.py`, `test_ats_apis.py`, `test_mcp_import.py`, `test_mcp_workday.py`, `test_more_eu_workday.py`, `test_wd_details.py`, `test_workday_eu.py`, `find_cv.py`, `inspect_cv.py`).
- Corrected overclaims and hardcoded candidate references in `README.md`, `docs/ARCHITECTURE.md`, and `docs/GLOSSARY.md`.

### Removed
- Removed 14 timestamped duplicate Excel files from `data/exports/`.
- Cleared committed `__pycache__` directories across the workspace.

### Assumptions
- Default Gemini model configuration set to `gemini-2.0-flash` and `gemini-1.5-pro` (verified current production models), overridable via `GEMINI_MODEL` and `GEMINI_PRO_MODEL` in `.env`.
