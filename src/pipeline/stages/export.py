"""
Pipeline Stage 4: Master Excel Export Stage.
Single owner of final workbook generation.
Data Contract: Reads SQLite database -> Generates multi-sheet Excel file atomically.
"""

from typing import Any, Dict, Optional
from src.db import StateDatabase
from src.schemas import UserProfile
from src.sync.sheets import SheetsSyncManager


def run_export_stage(db: StateDatabase, profile: Optional[UserProfile] = None) -> str:
    print("\n" + "=" * 78)
    print("PIPELINE STAGE 4: MASTER EXCEL EXPORT (SINGLE-OWNER)")
    print("=" * 78)

    exporter = SheetsSyncManager(db=db)
    export_file = exporter.export_to_excel(candidate_profile=profile)
    return export_file
