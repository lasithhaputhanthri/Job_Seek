"""
Expanded Multi-Country Job Hunter Pipeline.
Scales across USA, UK, Australia, UAE, and Europe concurrently using asyncio workers.
Produces individual per-country CSVs + global summary.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.discovery import CompanyDiscoveryAgent
from src.agents.parallel_manager import ParallelManagerAgent
from src.db import StateDatabase
from src.schemas import UserProfile


async def main():
    start_time = time.time()
    print("=" * 75)
    print("EXPANDED MULTI-COUNTRY AGENT PIPELINE: USA | UK | EUROPE | UAE | AUSTRALIA")
    print("=" * 75)

    # 1. Load Profile
    with open("data/profile.json", "r", encoding="utf-8") as f:
        profile_data = json.load(f)
    profile = UserProfile(**profile_data)
    print(f"\n[1. Intake Profile] Candidate: {profile.name}")
    print(f"    Domain: {profile.primary_domain}")
    print(f"    Target Countries: {', '.join(profile.target_countries)}")

    # 2. Database & Parallel Manager
    db = StateDatabase("data/job_hunter.db")
    manager = ParallelManagerAgent(db=db, profile=profile, max_concurrency=5)

    # 3. Discovery (Phase 7 Expanded)
    print("\n[2. Discovery Stage] Registering tier-1 companies across all target regions...")
    discovery = CompanyDiscoveryAgent(db=db, profile=profile)
    companies = discovery.discover_and_register(max_companies=45)

    # 4. Bootstrap tasks for all discovered companies
    manager.bootstrap_all_companies(companies)

    # 5. Execute parallel workers (Phase 6)
    print("\n[3. Parallel Worker Execution] Querying boards concurrently with semaphore=5...")
    await manager.run_parallel_workers(batch_size=40)

    # 6. Verification (Phase 5)
    manager.verify_all()

    # 7. Per-Country CSV Export (Phase 4 & 5)
    print("\n[4. Per-Country Output Generation]")
    summary = manager.export_results()

    elapsed = round(time.time() - start_time, 2)
    print("\n" + "=" * 75)
    print(f"EXPANDED PIPELINE FINISHED IN {elapsed} SECONDS!")
    print("PER-COUNTRY VERIFIED JOB BREAKDOWN:")
    for country, count in summary.items():
        if country not in ["TOTAL_ALL_COUNTRIES", "EXCEL_WORKBOOK"]:
            print(f"   * {country:<18}: {count} verified job(s)")
    print(f"   -------------------------------------------")
    print(f"   * TOTAL ALL REGIONS : {summary.get('TOTAL_ALL_COUNTRIES', 0)} verified jobs")
    if "EXCEL_WORKBOOK" in summary:
        print(f"   * EXCEL WORKBOOK    : {summary['EXCEL_WORKBOOK']}")
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(main())
