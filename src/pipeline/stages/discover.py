"""
Pipeline Stage 1: Company Discovery & Registry Population.
Populates the durable companies registry from verified ATS slugs, curated directories,
and taxonomy-derived sectors.
Data Contract: Reads UserProfile + SearchTaxonomy -> Writes to `companies` and `tasks` tables.
Resumable & Idempotent.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config import config
from src.db import StateDatabase
from src.schemas import UserProfile
from src.taxonomy import SearchTaxonomy, TaxonomyGenerator
from src.agents.discovery import CURATED_SEED_COMPANIES

logger = logging.getLogger("StageDiscover")


def run_discover_stage(
    db: StateDatabase,
    profile: UserProfile,
    taxonomy: Optional[SearchTaxonomy] = None,
    max_companies: Optional[int] = None,
    include_massive_directory: bool = True,
) -> Dict[str, Any]:
    print("\n" + "=" * 78)
    print("PIPELINE STAGE 1: COMPANY REGISTRY POPULATION (DISCOVERY)")
    print("=" * 78)

    tax = taxonomy or TaxonomyGenerator(profile).generate_or_load()
    initial_count = db.get_company_count()
    print(f"[StageDiscover] Starting company count: {initial_count:,}")

    registered_count = 0
    tasks_created = 0

    # 1. Register Curated Seed Employers
    target_countries_l = [c.lower() for c in profile.target_countries]
    is_global = any(w in " ".join(target_countries_l) for w in ["worldwide", "global", "all", "anywhere"])

    for comp in CURATED_SEED_COMPANIES:
        c_country = comp.get("country", "Global")
        if is_global or any(tc in c_country.lower() or c_country.lower() in tc for tc in target_countries_l):
            comp_id = db.add_company(
                name=comp["name"],
                domain=comp["domain"],
                country=comp["country"],
                industry=comp.get("industry", "Engineering"),
                careers_url=comp.get("careers_url", ""),
            )
            registered_count += 1
            # Create durable queue task idempotently
            task_id = db.create_task("CAREER_CHECK", comp_id, {
                "company_id": comp_id,
                "name": comp["name"],
                "careers_url": comp.get("careers_url", ""),
                "domain": comp["domain"],
            })
            if task_id:
                tasks_created += 1

    # 2. Ingest from Massive Company Directory if available (up to max_companies)
    catalog_path = config.BASE_DIR / "data" / "massive_company_directory.json"
    if include_massive_directory and catalog_path.exists():
        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                massive_data = json.load(f)

            limit_to_add = (max_companies - registered_count) if max_companies else len(massive_data)
            added_from_file = 0

            for c in massive_data:
                if max_companies and (initial_count + registered_count >= max_companies):
                    break
                domain = c.get("domain", "").lower().strip()
                if not domain:
                    continue

                comp_id = db.add_company(
                    name=c.get("name", "Unknown Company"),
                    domain=domain,
                    country=c.get("country", "Global"),
                    industry=c.get("industry", "Technology"),
                    careers_url=c.get("careers_url", ""),
                    ats_detected=c.get("ats_detected") or c.get("ats"),
                )
                db.create_task("CAREER_CHECK", comp_id, {
                    "company_id": comp_id,
                    "name": c.get("name", "Unknown Company"),
                    "careers_url": c.get("careers_url", ""),
                    "domain": domain,
                })
                registered_count += 1
                added_from_file += 1

            print(f"[StageDiscover] Ingested {added_from_file:,} companies from massive catalog.")
        except Exception as e:
            logger.warning(f"[StageDiscover] Notice loading massive catalog: {e}")

    final_count = db.get_company_count()
    print(f"[StageDiscover] Discovery complete. Total companies in registry: {final_count:,}")

    return {
        "initial_count": initial_count,
        "final_count": final_count,
        "registered_in_run": registered_count,
        "tasks_queued": tasks_created,
    }
