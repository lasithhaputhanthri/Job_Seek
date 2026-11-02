"""
Gather All Companies Script.
Downloads, merges, and registers ALL available technology companies across:
- 12,884 Workday enterprise portals
- 8,333 Greenhouse company boards
- 4,368 Lever company boards
- 3,161 Ashby deeptech boards
- 11,316 BambooHR portals
- 86+ Curated Tier-1 Hardware Leaders
Total: 40,000+ real tech companies with direct ATS endpoints!

Usage:
  python gather_all_companies.py
"""

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

from src.agents.massive_scout import AIMassiveJobDirectoryAgent
from src.db import StateDatabase
from src.schemas import UserProfile, SeniorityLevel


def main():
    print("\n" + "#" * 78)
    print("GLOBAL TECH COMPANY REPOSITORY HARVESTER (40,000+ DIRECTORY)")
    print("#" * 78)

    profile_file = Path("data/profile.json")
    if profile_file.exists():
        with open(profile_file, "r", encoding="utf-8") as f:
            profile_data = json.load(f)
        profile = UserProfile(**profile_data)
    else:
        profile = UserProfile(
            name="Candidate",
            current_location="Global",
            primary_domain="Hardware & Embedded Systems",
            target_roles=["Hardware Design Engineer", "RF Engineer", "Embedded Engineer"],
            seniority_levels=[SeniorityLevel.MID, SeniorityLevel.SENIOR],
            target_countries=["Worldwide"],
            target_industries=["Semiconductors", "Defense", "Aerospace"],
            must_have_skills=["RF", "PCB", "Embedded C"],
            nice_to_have_skills=["FPGA", "Altium"],
            constraints=["Open to relocation or remote opportunities"],
            summary="Hardware, RF & Embedded Systems Engineer",
            work_modes=["Remote", "Hybrid", "On-site"],
        )

    db = StateDatabase("data/job_hunter.db")
    initial_count = db.get_company_count()
    print(f"\n[Database Status] Initial company records in database: {initial_count:,}")

    agent = AIMassiveJobDirectoryAgent(db=db, profile=profile)
    stats = agent.gather_all_companies(save_to_json=True)

    final_count = db.get_company_count()
    print("\n" + "=" * 78)
    print("HARVEST SUMMARY:")
    print(f"  * Total Companies Downloaded & Processed : {stats['total_companies_gathered']:,}")
    print(f"  * Total Companies Now In SQLite Database : {final_count:,}")
    print(f"  * New Companies Added in this Run        : {final_count - initial_count:,}")
    print(f"  * Saved JSON Catalog File                : {Path('data/massive_company_directory.json').resolve()}")
    print(f"  * Elapsed Time                           : {stats['elapsed_seconds']}s")
    print("=" * 78)


if __name__ == "__main__":
    main()
