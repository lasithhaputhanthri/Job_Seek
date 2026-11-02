"""
Multi-Agent Job Hunting System - Main Entry Point.
Coordinates:
1. Interactive Intake (CV parsing & preference interview)
2. Target Company Discovery (Europe, UK, USA, etc.)
3. Parallel Career Checks (Workday REST, Greenhouse, Lever, Ashby)
4. Manager Evidence Verification & URL Audit
5. Multi-Sheet Styled Excel Export (job_hunt_results.xlsx)
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv, set_key

# Load environment variables from .env
load_dotenv()

# Windows console encoding fix
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.agents.discovery import CompanyDiscoveryAgent
from src.agents.intake import IntakeAgent
from src.agents.job_board_worker import JobBoardWorker
from src.agents.massive_scout import AIMassiveJobDirectoryAgent
from src.agents.parallel_manager import ParallelManagerAgent
from src.db import StateDatabase
from src.schemas import UserProfile
from src.sync.sheets import SheetsSyncManager


def interactive_intake() -> UserProfile:
    """Interactively ingests candidate CV, asks preference questions, and persists profile."""
    print("\n" + "=" * 75)
    print("STAGE 1: CANDIDATE INTAKE & PREFERENCE INTERVIEW")
    print("=" * 75)

    profile_file = Path("data/profile.json")

    # If profile already exists, offer fast resume
    if profile_file.exists():
        try:
            with open(profile_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            existing = UserProfile(**data)
            ans = input(f"Existing profile found for '{existing.name}'. Use existing profile? (Y/n): ").strip().lower()
            if ans not in ["n", "no"]:
                print(f"[Intake] Loaded existing profile for {existing.name}.")
                return existing
        except Exception:
            pass

    # 1. Ask for CV location
    default_cv = "data/cv.pdf"
    cv_input = input(f"\n[1/4] Enter path to your CV (PDF or DOCX) [default: {default_cv}]: ").strip()
    cv_path = cv_input if cv_input else default_cv

    if not Path(cv_path).exists():
        print(f"Error: Could not find CV at '{cv_path}'. Please ensure the file exists.")
        sys.exit(1)

    print(f"\n[Intake] Parsing CV document: {cv_path}...")
    intake_agent = IntakeAgent()
    cv_text = intake_agent.read_cv(cv_path)
    profile = intake_agent.extract_profile(cv_text)

    print("\n" + "-" * 60)
    print(f"IDENTIFIED CANDIDATE: {profile.name} (Current: {profile.current_location})")
    print(f"PRIMARY DOMAIN:       {profile.primary_domain}")
    print(f"CORE SKILLS DETECTED: {', '.join(profile.must_have_skills[:5])}")
    print("-" * 60)

    # 2. Interactive Questions on Preferences
    print("\n[2/4] PREFERENCES & CONSTRAINTS INTERVIEW:")
    print("      (Tip: You can type in completely normal, conversational English. The parser extracts entities automatically.)")

    # Q1: Target Countries
    default_countries = (
        "Netherlands, Germany, France, Ireland, UK, USA, Switzerland, Austria, Belgium, Spain, Australia, UAE"
    )
    user_countries = input(
        f"\n1. Target Countries / Regions (natural language or comma-separated)\n   [Press Enter for: {default_countries}]:\n   > "
    ).strip()
    if user_countries:
        parsed_c = intake_agent.parse_natural_language_countries(user_countries)
        profile.target_countries = parsed_c if parsed_c else [c.strip() for c in user_countries.split(",") if c.strip()]
    else:
        profile.target_countries = [c.strip() for c in default_countries.split(",") if c.strip()]
    print(f"   -> Parsed Target Countries: {', '.join(profile.target_countries)}")

    # Q2: Target Job Titles
    default_roles = ", ".join(profile.target_roles[:5])
    user_roles = input(
        f"\n2. Preferred Roles / Disciplines (natural language or comma-separated)\n   [Press Enter to accept: {default_roles}]:\n   > "
    ).strip()
    if user_roles:
        parsed_r = intake_agent.parse_natural_language_roles(user_roles, existing_roles=profile.target_roles)
        profile.target_roles = parsed_r if parsed_r else [r.strip() for r in user_roles.split(",") if r.strip()]
    print(f"   -> Parsed Target Roles: {', '.join(profile.target_roles)}")

    # Q3: Relocation / Visa Constraints
    default_constraint = (
        f"Based in {profile.current_location}: requires work visa sponsorship or relocation support"
    )
    user_constraint = input(
        f"\n3. Visa & Relocation Constraints (natural language)\n   [Press Enter for: '{default_constraint}']:\n   > "
    ).strip()
    if user_constraint:
        profile.constraints = [user_constraint]
    else:
        profile.constraints = [default_constraint]
    print(f"   -> Recorded Constraints: {profile.constraints[0]}")

    # Q4: Preferred Work Arrangement (Remote / Hybrid / On-site)
    saved_wm = ", ".join(profile.work_modes) if profile.work_modes else "On-site, Hybrid, Remote"
    user_wm = input(
        f"\n4. Work Arrangement Preference (Remote, Hybrid, On-site, or All)\n   [Press Enter for: {saved_wm}]:\n   > "
    ).strip().lower()
    if user_wm:
        selected_wm = []
        if "all" in user_wm or "any" in user_wm:
            selected_wm = ["On-site", "Hybrid", "Remote"]
        else:
            if "remote" in user_wm:
                selected_wm.append("Remote")
            if "hybrid" in user_wm:
                selected_wm.append("Hybrid")
            if "onsite" in user_wm or "on-site" in user_wm or "office" in user_wm:
                selected_wm.append("On-site")
        profile.work_modes = selected_wm if selected_wm else ["On-site", "Hybrid", "Remote"]
    elif profile.work_modes:
        pass  # Keep saved preference
    else:
        profile.work_modes = ["On-site", "Hybrid", "Remote"]
    print(f"   -> Recorded Work Arrangement: {', '.join(profile.work_modes)}")

    # Q5: Target Search Scale
    print("\n5. Target Job Volume & Scale:")
    print("   [1] Standard Search (~50-150 jobs)")
    print("   [2] Deep Global Scale (100 - 1,000 jobs around the world)")
    print("   [3] Massive AI Directory Scout (1,000 - 100,000+ companies & job websites)")
    user_scale = input("   Select option [Press Enter for option 2]: ").strip()
    is_deep_scale = user_scale != "1"
    profile.is_deep_scale = is_deep_scale
    profile.scale_option = user_scale if user_scale in ["1", "2", "3"] else "2"
    if user_scale == "3":
        scale_label = "Massive AI Directory Scout (1,000 - 100,000+ companies & websites)"
    elif is_deep_scale:
        scale_label = "Deep Global Scale (100 - 1,000 jobs around the world)"
    else:
        scale_label = "Standard Search (50 - 150 jobs)"
    print(f"   -> Configured Target Volume: {scale_label}")

    # Gemini API Key Setup (if not already set)
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not gemini_key:
        print("\n[Gemini Pro Configuration]")
        print("  You can activate live Gemini Pro for dynamic worldwide employer discovery & reasoning.")
        key_input = input("  Paste your GEMINI_API_KEY [or press Enter to use built-in AI engine]: ").strip()
        if key_input:
            os.environ["GEMINI_API_KEY"] = key_input
            try:
                set_key(".env", "GEMINI_API_KEY", key_input)
                print("  -> GEMINI_API_KEY saved to .env!")
            except Exception:
                pass

    # Save finalized profile to disk
    intake_agent.save_profile(profile, str(profile_file))
    print(f"\n[Intake] Profile successfully validated and saved to {profile_file.resolve()}")
    return profile


async def run_pipeline():
    start_time = time.time()
    print("\n" + "#" * 75)
    print("MULTI-AGENT JOB HUNTING SYSTEM: END-TO-END PIPELINE")
    print("#" * 75)

    # Step 1: Intake & Preferences
    profile = interactive_intake()

    is_deep_scale = getattr(profile, "is_deep_scale", True)
    scale_option = getattr(profile, "scale_option", "2")

    # AI Agent Classification Engine Status
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    if gemini_key:
        print("\n[AI Agent Engine] Using Google Gemini Pro & Flash for deep LLM job evaluation.")
    elif openai_key:
        print("\n[AI Agent Engine] Using OpenAI GPT-4o for deep LLM job evaluation.")
    else:
        print("\n[AI Agent Engine] Running with Built-in Semantic Reasoning Engine.")
        print("                  (Tip: Set GEMINI_API_KEY in .env to activate Google Gemini Pro.)")

    # Step 2: Database Initialization
    db_path = "data/job_hunter.db"
    db = StateDatabase(db_path)
    concurrency = 12 if is_deep_scale else 5
    manager = ParallelManagerAgent(db=db, profile=profile, max_concurrency=concurrency)

    # Step 3 & 4: Massive Company Directory & AI Job Scouting
    if is_deep_scale:
        massive_agent = AIMassiveJobDirectoryAgent(db=db, profile=profile)
        is_remote_strictly = profile.work_modes == ["Remote"]

        # 1. Build and expand directory with curated and emerging targets
        if scale_option == "3":
            target_dir_count = 1000
        elif scale_option == "2":
            target_dir_count = 250
        else:
            target_dir_count = 80

        print("\n" + "=" * 75)
        print("STAGE 2: GLOBAL TECH COMPANY DIRECTORY GENERATION")
        if is_remote_strictly:
            print("Populating 32,000+ Company Database & Curated Targets (Remote-Friendly Mode)...")
        else:
            print(f"Populating {target_dir_count}+ Curated and Verified Engineering Employers (from 32,000+ Catalog)...")
        print("=" * 75)

        companies = massive_agent.build_massive_directory(
            target_count=target_dir_count,
            enable_ai_expansion=True,
            save_to_json=True,
        )

        # 2. Scout open engineering jobs across direct company ATS portals
        print("\n" + "=" * 75)
        print(f"STAGE 3A: SCOUTING OPEN JOBS ACROSS DIRECT COMPANY ATS PORTALS {'(REMOTE ONLY)' if is_remote_strictly else ''}")
        print("=" * 75)
        await massive_agent.scout_companies_for_jobs(
            companies=companies,
            max_jobs_per_company=25,
            concurrency=concurrency,
            remote_only=is_remote_strictly,
        )

        # 3. Harvest engineering job boards & websites (Arbeitnow, Remotive, Jobicy, RemoteOK)
        print("\n" + "=" * 75)
        print("STAGE 3B: LIVE JOB WEBSITES & AGGREGATORS HARVEST")
        print("=" * 75)
        massive_agent.harvest_from_job_websites(max_per_source=100)
    else:
        # Standard Search
        print("\n" + "=" * 75)
        print("STAGE 2: DYNAMIC AI COMPANY DISCOVERY (WORLDWIDE & REGIONAL)")
        print("=" * 75)
        discovery = CompanyDiscoveryAgent(db=db, profile=profile)
        companies = discovery.discover_and_register(max_companies=25)
        print(f"[Discovery] Discovered & registered {len(companies)} global engineering employers.")

        manager.bootstrap_all_companies(companies)

        print("\n" + "=" * 75)
        print("STAGE 3A: DIRECT COMPANY PORTALS (Workday REST, Greenhouse, Lever & Ashby)")
        print("=" * 75)
        print(f"Launching async workers across tier-1 hardware employers (Concurrency: {concurrency})...")
        await manager.run_parallel_workers(batch_size=len(companies))

        print("\n" + "=" * 75)
        print("STAGE 3B: GLOBAL JOB BOARDS & AGGREGATORS (Arbeitnow & Remotive Live Feeds)")
        print("=" * 75)
        job_board_worker = JobBoardWorker(db=db, profile=profile)
        jb_count = job_board_worker.run_all_job_boards(limit_per_source=50)
        print(f"[JobBoards] Scanned live job sites: {jb_count} matches recorded.")

    # Step 6: Manager Verification Audit (Phase 5)
    print("\n" + "=" * 75)
    print("STAGE 4: AI VERIFICATION & LIVE URL AUDIT")
    print("=" * 75)
    manager.verify_all()

    # Step 7: Multi-Sheet Excel & Per-Country Output
    print("\n" + "=" * 75)
    print("STAGE 5: MULTI-SHEET EXCEL WORKBOOK EXPORT")
    print("=" * 75)
    summary = manager.export_results()

    elapsed = round(time.time() - start_time, 2)
    print("\n" + "#" * 75)
    print(f"PIPELINE COMPLETED SUCCESSFULLY IN {elapsed} SECONDS!")
    print("#" * 75)
    print("\nVERIFIED JOBS SUMMARY BY COUNTRY:")
    for country, count in summary.items():
        if country not in ["TOTAL_ALL_COUNTRIES", "EXCEL_WORKBOOK"]:
            print(f"   * {country:<18}: {count} verified job(s)")
    print("   " + "-" * 42)
    print(f"   * TOTAL ALL REGIONS : {summary.get('TOTAL_ALL_COUNTRIES', 0)} verified jobs")
    if "EXCEL_WORKBOOK" in summary:
        print(f"\n👉 OPEN YOUR EXCEL WORKBOOK HERE: {summary['EXCEL_WORKBOOK']}")
    print("#" * 75)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # If run flags are passed directly without 'run' subcommand, inject 'run'
        if sys.argv[1] not in ["run", "repair", "eval", "-h", "--help"]:
            sys.argv.insert(1, "run")
        from src.cli import main as cli_main
        cli_main()
    else:
        asyncio.run(run_pipeline())
