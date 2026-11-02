"""
Complete End-to-End Job Hunter Pipeline.
Orchestrates Discovery -> Career Check -> Contact Finder -> Verification -> CSV/Sheets Sync.
"""

import json
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.career_checker import CareerCheckerWorker
from src.agents.contact_finder import ContactFinderWorker
from src.agents.discovery import CompanyDiscoveryAgent
from src.agents.manager import ManagerAgent
from src.db import StateDatabase
from src.schemas import UserProfile


def run_full_pipeline():
    start_time = time.time()
    print("=" * 70)
    print("STARTING FULL END-TO-END MULTI-AGENT JOB HUNTING PIPELINE")
    print("=" * 70)

    # 1. Load Candidate Profile
    profile_path = Path("data/profile.json")
    if not profile_path.exists():
        raise FileNotFoundError("Candidate profile not found. Run 'python -m src.agents.intake' first.")

    with open(profile_path, "r", encoding="utf-8") as f:
        profile_data = json.load(f)
    profile = UserProfile(**profile_data)
    print(f"\n[Stage 1: Intake] Candidate: {profile.name} | Domain: {profile.primary_domain}")

    # 2. Initialize Database & Manager
    db = StateDatabase("data/job_hunter.db")
    manager = ManagerAgent(db=db, profile=profile, sample_audit_rate=0.25)

    # 3. Company Discovery (Phase 7)
    print("\n[Stage 2: Discovery] Discovering target companies across candidate countries...")
    discovery = CompanyDiscoveryAgent(db=db, profile=profile)
    discovered_companies = discovery.discover_and_register(max_companies=32)
    print(f"Total Companies in State Database: {len(discovered_companies)}")

    # 4. Bootstrap Tasks
    all_companies = db.get_companies()
    manager.bootstrap_companies(all_companies[:8])  # Dispatch first 8 active target companies for this run

    # 5. Career Check (Worker execution)
    print("\n[Stage 3: Career Check] Workers querying career pages via MCP...")
    manager.run_pending_tasks()

    # 6. Contact Finder (Phase 8)
    print("\n[Stage 4: Contact Discovery] Finding verified public hiring emails...")
    contact_finder = ContactFinderWorker(db=db)
    for comp in all_companies[:5]:
        contact_finder.find_contacts_for_company(comp)

    # 7. Manager Verification (Phase 5)
    print("\n[Stage 5: Manager Verification & Audit]")
    audit_stats = manager.verify_all_proposals()

    # 8. Output Sync (Phase 4 & 5)
    print("\n[Stage 6: Output Synchronization]")
    csv_file = manager.sync_verified_to_output(country=None)

    elapsed = round(time.time() - start_time, 2)
    print("\n" + "=" * 70)
    print(f"PIPELINE COMPLETE IN {elapsed}s!")
    print(f"  Verified Job Matches Saved: {audit_stats['verified']}")
    print(f"  Exported File: {csv_file}")
    print("=" * 70)


if __name__ == "__main__":
    run_full_pipeline()
