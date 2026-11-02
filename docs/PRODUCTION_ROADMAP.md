# Production Roadmap (Scaling from 1,000 to 100,000+ Companies)

This roadmap outlines the architectural evolution required to scale the Job_Seek multi-agent system from a high-efficiency single-node engine into an enterprise distributed SaaS platform capable of indexing 100,000+ global employers and serving thousands of concurrent candidates.

---

### 1. Multi-Tenancy & Candidate Data Isolation
* **Current Architecture:** Local SQLite database (`job_hunter.db`) with WAL mode, busy timeouts, and serialized `UserProfile` state.
* **Production Architecture:**
  - Transition to managed PostgreSQL (e.g., Supabase / AWS Aurora) with Row-Level Security (RLS) enforcing strict multi-tenant boundaries.
  - Candidate CV vectors and profile embeddings stored in `pgvector` with HNSW indexing.
  - End-to-end envelope encryption for candidate PII (names, contact info, uploaded CVs) with GDPR/CCPA compliance and automated right-to-be-forgotten deletion workflows.

### 2. Distributed Work Orchestration & Scale (100,000+ Companies)
* **Current Architecture:** Async task queues managed inside SQLite with atomic lease claiming (`UPDATE ... RETURNING`), lease timeouts, and exponential backoff.
* **Production Architecture:**
  - Distributed durable execution engine powered by **Temporal.io** or **Celery + Redis**.
  - Worker pools partitioned by ATS type (Workday worker cluster, Greenhouse worker cluster, Job board stream consumers).
  - Rate limiting enforced via distributed Redis Token Bucket algorithms across IP blocks and host domains, eliminating HTTP 429 penalties.

### 3. Delta Harvesting & Change-Detection Architecture
* **Current Architecture:** Periodic batch scans across company career portals.
* **Production Architecture:**
  - Store content hashes (`description_hash`, `title_hash`) and HTTP `ETag` / `Last-Modified` headers to enable instant HTTP 304 skipping.
  - Webhook ingestion listeners for ATS partners and RSS/Atom feed subscriptions for real-time delta ingestion.
  - S3 / GCS raw page snapshot archival with zstandard compression for deterministic legal audit trails.

### 4. Advanced Cost Funnel & Multi-Model Routing
* **Current Architecture:** Strict 7-step cost funnel: Free ATS list -> Word-boundary Title Regex -> Geographic Hard Filter -> Detail Fetch -> Visa/ITAR Hard Filter -> Shortlisted LLM Scoring (capped at $0.00015/posting).
* **Production Architecture:**
  - **Tier 0:** Ultra-fast Rust/Wasm title classification module compiled to native binaries running on serverless edge nodes.
  - **Tier 1:** Small local or open-weights model (e.g., Qwen 2.5 7B / Gemma 2 9B) for initial relevance filtering at zero API marginal cost.
  - **Tier 2:** Frontier reasoning LLMs (Google Gemini 2.0 Flash / OpenAI GPT-4o) reserved exclusively for deep domain alignment and adversarial verification audits on borderline cases.

### 5. Proxy Pools & Resilient Scraping Infrastructure
* **Current Architecture:** Direct HTTP client with polite user-agent strings, custom headers, and jittered retries.
* **Production Architecture:**
  - Enterprise rotating residential proxy mesh (Bright Data / Oxylabs) with automatic TLS fingerprint impersonation (curl_cffi / Playwright-stealth).
  - Headless browser rendering pool (Playwright / Puppeteer via Browserbase) triggered strictly on JS-rendered portals that lack structured REST APIs (e.g. Workday complex legacy portals or BambooHR custom career sites).

### 6. Interactive Candidate Portal & Single-Click Exports
* **Current Architecture:** Interactive terminal CLI and single-owner multi-sheet styled Excel workbook exports (`data/exports/job_hunt_results.xlsx`).
* **Production Architecture:**
  - Next.js 15 App Router web application with real-time WebSocket telemetry tracking job discovery and verification.
  - One-click bi-directional integrations: Sync to Notion databases, Airtable boards, Google Sheets via OAuth, or direct ATS application prep.
  - Human-in-the-loop personalized outreach editor: auto-populates authentic project highlights cited verbatim from the candidate's verified background, requiring candidate approval before emailing hiring teams.
