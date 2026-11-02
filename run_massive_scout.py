"""
Standalone CLI Runner for the Massive AI Job Directory & Company Scout Agent.
Allows searching an expansive catalog of 1,000 to 100,000+ companies and job websites,
and harvesting verified hardware, RF, and embedded engineering jobs worldwide.

Usage:
  python run_massive_scout.py
  python run_massive_scout.py --companies 100 --jobs-per-company 20
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.agents.intake import IntakeAgent
from src.agents.massive_scout import AIMassiveJobDirectoryAgent
from src.agents.parallel_manager import ParallelManagerAgent
from src.db import StateDatabase
from src.schemas import UserProfile


async def main():
    parser = argparse.ArgumentParser(description="Massive AI Job Directory & Company Scout Agent")
    parser.add_argument("--companies", type=int, default=100, help="Target company directory count (default: 100)")
    parser.add_argument("--jobs-per-company", type=int, default=25, help="Max jobs to scan per company (default: 25)")
    parser.add_argument("--concurrency", type=int, default=8, help="Parallel worker threads (default: 8)")
    parser.add_argument("--no-ai-expansion", action="store_true", help="Disable dynamic Gemini AI sector expansion")
    parser.add_argument("--gather-all", action="store_true", help="Gather ALL 40,000+ companies from global ATS directories")
    args = parser.parse_args()

    # Load candidate profile
    profile_file = Path("data/profile.json")
    if not profile_file.exists():
        print(f"Error: Profile not found at {profile_file.resolve()}. Run main.py first to parse CV.")
        sys.exit(1)

    with open(profile_file, "r", encoding="utf-8") as f:
        profile_data = json.load(f)
    profile = UserProfile(**profile_data)

    print("\n" + "#" * 78)
    print("MASSIVE AI JOB DIRECTORY & COMPANY SCOUT AGENT (1,000+ SCALE)")
    print(f"Candidate: {profile.name} ({profile.primary_domain})")
    print(f"Preferred Work Modes: {', '.join(profile.work_modes)}")
    print(f"Target Regions: {', '.join(profile.target_countries)}")
    print("#" * 78)

    db = StateDatabase("data/job_hunter.db")
    agent = AIMassiveJobDirectoryAgent(db=db, profile=profile)

    # Execute complete massive hunt
    summary = await agent.run_massive_hunt(
        target_company_count=args.companies,
        enable_ai_expansion=not args.no_ai_expansion,
        gather_all_mode=args.gather_all,
        max_jobs_per_company=args.jobs_per_company,
        concurrency=args.concurrency,
    )

    # Export verified results to styled Excel workbook
    print("\n[Export] Generating updated Multi-Sheet Excel Workbook...")
    manager = ParallelManagerAgent(db=db, profile=profile)
    manager.verify_all()
    export_summary = manager.export_results()

    if "EXCEL_WORKBOOK" in export_summary:
        print(f"\n👉 OPEN YOUR EXCEL WORKBOOK HERE: {export_summary['EXCEL_WORKBOOK']}")

    print("\nDONE!")


if __name__ == "__main__":
    asyncio.run(main())
