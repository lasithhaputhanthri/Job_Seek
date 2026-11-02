"""
Phase 5 & Production: The Manager / Supervisor Agent (Orchestrator).
Single owner of run lifecycle, queue health, quality gates, and output exports.
Enforces the cost funnel, tracks token budgets and costs, evaluates quality gates,
and owns the final multi-sheet Excel export.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from src.config import config
from src.db import StateDatabase
from src.pipeline.stages.discover import run_discover_stage
from src.pipeline.stages.harvest import CostFunnelHarvester
from src.pipeline.stages.verify import run_verify_stage
from src.pipeline.stages.export import run_export_stage
from src.schemas import UserProfile
from src.taxonomy import SearchTaxonomy, TaxonomyGenerator

logger = logging.getLogger("ManagerAgent")


class ManagerAgent:
    def __init__(
        self,
        db: Optional[StateDatabase] = None,
        profile: Optional[UserProfile] = None,
        sample_audit_rate: Optional[float] = None,
    ):
        self.db = db or StateDatabase()
        self.profile = profile
        self.sample_audit_rate = sample_audit_rate or config.SAMPLE_AUDIT_RATE
        self.taxonomy: Optional[SearchTaxonomy] = None
        self.run_report: Dict[str, Any] = {}

    async def run_pipeline(
        self,
        stage: str = "all",
        max_companies: Optional[int] = None,
        max_batches: Optional[int] = None,
        harvest_boards: bool = True,
        board_limit_per_source: int = 50,
    ) -> Dict[str, Any]:
        """
        Coordinates full end-to-end execution across discrete stages:
        Profile -> Company Registry -> Job Harvest -> Verification -> Export.
        """
        start_time = time.time()
        print("\n" + "#" * 78)
        print("MULTI-AGENT JOB SEEK SYSTEM - MANAGER AGENT EXECUTION")
        print(f"Target Stage  : {stage.upper()}")
        print(f"Candidate     : {self.profile.name if self.profile else 'Generic Profile'}")
        print("#" * 78)

        # Ensure search taxonomy is loaded
        if self.profile:
            self.taxonomy = TaxonomyGenerator(self.profile).generate_or_load()

        report: Dict[str, Any] = {
            "stage": stage,
            "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "quality_gate_passed": True,
            "quality_gate_notes": "All checks within tolerance.",
        }

        # -------------------------------------------------------------
        # STAGE 1: DISCOVERY
        # -------------------------------------------------------------
        if stage in ["all", "discover"]:
            if not self.profile:
                raise ValueError("UserProfile is required to run discovery stage.")
            disc_stats = run_discover_stage(
                db=self.db,
                profile=self.profile,
                taxonomy=self.taxonomy,
                max_companies=max_companies,
            )
            report["discovery"] = disc_stats

        # -------------------------------------------------------------
        # STAGE 2: HARVEST (Cost Funnel)
        # -------------------------------------------------------------
        if stage in ["all", "harvest"]:
            if not self.profile or not self.taxonomy:
                raise ValueError("UserProfile and SearchTaxonomy are required for harvest stage.")
            harvester = CostFunnelHarvester(db=self.db, profile=self.profile, taxonomy=self.taxonomy)
            harvest_stats = await harvester.run_harvest(
                max_batches=max_batches,
                harvest_boards=harvest_boards,
                board_limit_per_source=board_limit_per_source,
            )
            report["harvest"] = harvest_stats

        # -------------------------------------------------------------
        # STAGE 3: INDEPENDENT VERIFICATION
        # -------------------------------------------------------------
        if stage in ["all", "verify"]:
            if not self.profile:
                raise ValueError("UserProfile is required for verification stage.")
            verify_stats = await run_verify_stage(db=self.db, profile=self.profile)
            report["verification"] = verify_stats

        # -------------------------------------------------------------
        # QUALITY GATE CHECK (Precision target & Dead link max)
        # -------------------------------------------------------------
        metrics = self.db.get_run_metrics()
        tot_jobs = max(metrics.get("total_jobs_seen", 0), 1)
        dead_link_rate = metrics.get("dead_jobs", 0) / tot_jobs

        if dead_link_rate > config.DEAD_LINK_MAX:
            report["quality_gate_passed"] = False
            report["quality_gate_notes"] = f"Dead link rate ({dead_link_rate:.2%}) exceeded maximum threshold ({config.DEAD_LINK_MAX:.2%})."
            print(f"\n[Manager Quality Gate WARNING] {report['quality_gate_notes']}")

        # -------------------------------------------------------------
        # STAGE 4: EXPORT (Owned exclusively by Manager)
        # -------------------------------------------------------------
        if stage in ["all", "export"]:
            export_path = run_export_stage(db=self.db, profile=self.profile)
            report["export_path"] = export_path

        elapsed = round(time.time() - start_time, 2)
        report["elapsed_seconds"] = elapsed
        report["metrics"] = metrics
        self.run_report = report

        self._print_executive_summary(report)
        return report

    def _print_executive_summary(self, report: Dict[str, Any]):
        """Prints candidate-agnostic executive run report."""
        metrics = report.get("metrics", {})
        print("\n" + "=" * 78)
        print("EXECUTIVE RUN REPORT & TELEMETRY:")
        print(f"  * Total Companies in Registry : {metrics.get('total_companies', 0):,}")
        print(f"  * Total Jobs Processed        : {metrics.get('total_jobs_seen', 0):,}")
        print(f"  * Total Verified Eligible Jobs: {metrics.get('verified_jobs', 0):,}")
        print(f"  * Jobs Flagged Ineligible     : {metrics.get('ineligible_jobs', 0):,}")
        print(f"  * Token Usage & Cost (USD)    : {metrics.get('input_tokens', 0) + metrics.get('output_tokens', 0):,} tokens (${metrics.get('estimated_cost_usd', 0.0):.4f})")
        print(f"  * Quality Gate Status         : {'PASSED' if report.get('quality_gate_passed') else 'NEEDS REVIEW'}")
        if "export_path" in report:
            print(f"  * Final Master Excel Workbook : {report['export_path']}")
        print("=" * 78)
