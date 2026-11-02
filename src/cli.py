"""
Unified CLI Entry Point for Job_Seek Multi-Agent System.

Usage:
    python -m src.cli run --profile data/profile.json --yes
    python -m src.cli run --stage discover --max-companies 50
    python -m src.cli run --stage harvest --scale deep
    python -m src.cli run --stage verify
    python -m src.cli run --stage export
    python -m src.cli repair [--dry-run]
    python -m src.cli eval
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

from src.agents.manager import ManagerAgent
from src.config import config
from src.db import StateDatabase
from src.schemas import SeniorityLevel, UserProfile

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("JobSeekCLI")


def load_or_create_profile(
    profile_path: str,
    countries: Optional[List[str]] = None,
    work_modes: Optional[List[str]] = None,
    non_interactive: bool = False,
) -> UserProfile:
    """Loads existing profile from disk, optionally overrides filters, or creates minimal valid profile."""
    path = Path(profile_path)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        profile = UserProfile(**data)
        logger.info("Loaded profile for candidate '%s' from %s", profile.name, profile_path)
    else:
        if non_interactive:
            logger.warning("Profile '%s' not found. Creating default generic profile.", profile_path)
            profile = UserProfile(
                name="Candidate",
                current_location="Unknown",
                primary_domain="Engineering",
                target_roles=["Software Engineer", "Systems Engineer"],
                seniority_levels=[SeniorityLevel.MID, SeniorityLevel.SENIOR],
                target_countries=["Germany", "Netherlands", "United Kingdom", "United States"],
                target_industries=["Technology"],
                must_have_skills=["Python", "System Design"],
                nice_to_have_skills=[],
                constraints=[],
                work_modes=["Remote", "Hybrid", "On-site"],
            )
        else:
            raise FileNotFoundError(f"Profile file '{profile_path}' does not exist. Run interactive intake or specify a valid profile.")

    if countries:
        profile.target_countries = countries
        logger.info("Overriding target countries: %s", countries)

    if work_modes:
        profile.work_modes = work_modes
        logger.info("Overriding work modes: %s", work_modes)

    return profile


async def cmd_run(args: argparse.Namespace) -> int:
    """Executes a pipeline run across selected stages."""
    countries = [c.strip() for c in args.countries.split(",") if c.strip()] if args.countries else None
    work_modes = [w.strip() for w in args.work_modes.split(",") if w.strip()] if args.work_modes else None

    profile = load_or_create_profile(
        profile_path=args.profile,
        countries=countries,
        work_modes=work_modes,
        non_interactive=args.yes,
    )

    db = StateDatabase(args.db)

    # Scale configuration adjustments
    max_companies = args.max_companies
    if args.scale == "massive":
        max_companies = max_companies or 500
    elif args.scale == "deep":
        max_companies = max_companies or 100
    else:
        max_companies = max_companies or 25

    manager = ManagerAgent(db=db, profile=profile)

    if args.dry_run:
        print("\n[DRY RUN] Running in dry-run mode. Pipeline parameters validated:")
        print(f"  Stage: {args.stage}")
        print(f"  Scale: {args.scale} (Max companies: {max_companies})")
        print(f"  Profile: {profile.name} ({profile.primary_domain})")
        print(f"  Target Countries: {profile.target_countries}")
        print(f"  Work Modes: {profile.work_modes}")
        print(f"  Database: {args.db}")
        return 0

    report = await manager.run_pipeline(
        stage=args.stage,
        max_companies=max_companies,
        max_batches=args.max_batches,
        harvest_boards=not args.no_boards,
    )

    if report.get("quality_gate_passed", True):
        return 0
    return 1


def cmd_repair(args: argparse.Namespace) -> int:
    """Runs data repair on existing database."""
    from scripts.repair_existing_data import repair_database
    res = repair_database(db_path=args.db, dry_run=args.dry_run)
    return 0 if res else 1


def cmd_eval(args: argparse.Namespace) -> int:
    """Runs golden dataset benchmark evaluation."""
    from src.eval import run_evaluation_benchmark
    res = run_evaluation_benchmark(golden_path=args.golden_file, min_score=args.min_score)
    return 0 if res.get("passed", False) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli",
        description="Candidate-Agnostic Multi-Agent Job Hunting System CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: run
    run_parser = subparsers.add_parser("run", help="Run the multi-agent pipeline")
    run_parser.add_argument("--profile", default="data/profile.json", help="Path to profile JSON")
    run_parser.add_argument("-y", "--yes", action="store_true", help="Non-interactive mode (no prompt)")
    run_parser.add_argument(
        "--stage",
        choices=["all", "discover", "harvest", "verify", "export"],
        default="all",
        help="Pipeline stage to execute",
    )
    run_parser.add_argument(
        "--scale",
        choices=["standard", "deep", "massive"],
        default="standard",
        help="Search scale level",
    )
    run_parser.add_argument("--countries", default=None, help="Comma-separated country list override")
    run_parser.add_argument("--work-modes", default=None, help="Comma-separated work modes (Remote, Hybrid, On-site)")
    run_parser.add_argument("--max-companies", type=int, default=None, help="Maximum companies to process")
    run_parser.add_argument("--max-batches", type=int, default=None, help="Maximum harvest batches")
    run_parser.add_argument("--resume", action="store_true", help="Resume from current queue state")
    run_parser.add_argument("--dry-run", action="store_true", help="Validate parameters and test configuration without side effects")
    run_parser.add_argument("--no-boards", action="store_true", help="Skip public job boards")
    run_parser.add_argument("--db", default="data/job_hunter.db", help="Path to database")

    # Command: repair
    repair_parser = subparsers.add_parser("repair", help="Audit and repair existing database rows")
    repair_parser.add_argument("--db", default="data/job_hunter.db", help="Path to database")
    repair_parser.add_argument("--dry-run", action="store_true", help="Audit without modifying rows")

    # Command: eval
    eval_parser = subparsers.add_parser("eval", help="Run evaluation benchmark against golden dataset")
    eval_parser.add_argument("--golden-file", default="tests/golden/golden_jobs.json", help="Path to golden jobs JSON")
    eval_parser.add_argument("--min-score", type=int, default=50, help="Relevance threshold")

    return parser


def main():
    parser = build_parser()
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    if args.command == "run":
        exit_code = asyncio.run(cmd_run(args))
        sys.exit(exit_code)
    elif args.command == "repair":
        exit_code = cmd_repair(args)
        sys.exit(exit_code)
    elif args.command == "eval":
        exit_code = cmd_eval(args)
        sys.exit(exit_code)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
