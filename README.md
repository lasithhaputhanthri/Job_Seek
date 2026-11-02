# Multi-Agent Job Hunting System (Job_Seek)

An autonomous, multi-agent AI pipeline designed to discover, evaluate, verify, and export engineering job postings across global markets (Europe, USA, UK, Australia, Switzerland, UAE, and Remote).

Driven by Google Gemini models (`gemini-3.1-flash-lite`), modern ATS API integrations (Greenhouse, Lever, Ashby, Workday CXS REST, SmartRecruiters), and independent adversarial verification agents.

---

## Key Features & Architecture
- **Candidate-Agnostic Design:** Completely decoupled candidate profile and matching logic. Adapts dynamically to any engineering discipline, seniority level, or geographic preference.
- **Direct ATS Integration:** Direct REST API connectors for Workday, Greenhouse, Lever, Ashby, and SmartRecruiters, bypassing JavaScript frontends.
- **32,000+ Company Directory:** Pre-indexed catalog of global tech, deep tech, semiconductor, and hardware employers.
- **Adversarial Verification:** Multi-point independent verification checking HTTP status, ATS listing presence, verbatim description quote matching, role alignment, and multilingual closed/expired detection (EN, DE, FR, NL, ES, IT).
- **Hard Eligibility & Visa Filters:** Explicit filtering for visa sponsorship, security clearances, ITAR citizenship constraints, and seniority tiers.
- **Multi-Sheet Excel Reporting:** Single-owner workbook output (`job_hunt_results.xlsx`) containing verified roles, country breakdowns, and ineligible audits.

---

## Quickstart Guide

### 1. Clone the Repository
```bash
git clone https://github.com/lasithhaputhanthri/Job_Seek.git
cd Job_Seek
```

### 2. Set Up Virtual Environment & Dependencies
```bash
# Windows
python -m venv .venv
.\.venv\Scripts\activate

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Your Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Open `.env` and replace `"Gemini API goes here"` with your free Google Gemini API key from [Google AI Studio](https://aistudio.google.com/):

```env
GEMINI_API_KEY="your-gemini-api-key-here"
```

### 4. Run the Pipeline
```bash
python main.py
```
1. Point to your CV (`.pdf` or `.docx`).
2. Answer a few intake preference questions (Target Countries, Roles, Relocation/Visa needs, Work Arrangement).
3. Select your desired search volume (e.g., Option 3 for the Massive 32,000+ Company Directory Scout).
4. Inspect verified matches in `data/exports/job_hunt_results.xlsx`.

---

## Running Automated Tests

Run the full offline test suite with mocked HTTP/LLM:
```bash
pytest tests/ -q
```

Run the golden dataset precision benchmark:
```bash
python -m src.eval
```

---

## Architectural Documentation
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): Multi-agent design, cost funnel, and data contracts.
- [`docs/GLOSSARY.md`](docs/GLOSSARY.md): MCP definitions, sampling, adversarial audits, and untrusted framing.
- [`docs/PRODUCTION_ROADMAP.md`](docs/PRODUCTION_ROADMAP.md): Scalability milestones, adapter roadmaps, and enterprise readiness.
- [`CHANGELOG.md`](CHANGELOG.md): Audit and bugfix changelog.
