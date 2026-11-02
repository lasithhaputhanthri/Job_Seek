"""
AI Company Discovery Agent.
Intelligently discovers and registers target employers across Europe, UK, USA, and candidate target regions.
Combines:
1. Curated high-yield verified ATS seed companies (Workday, Greenhouse, Lever, Ashby).
2. Dynamic AI LLM discovery tailored to candidate's exact engineering domains (RF, Radar, Antennas, High-Speed PCB, Embedded Systems, Semiconductors).
3. Deduplication and registration into durable SQLite database.
"""

import json
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.agents.llm_engine import ai_engine
from src.db import StateDatabase
from src.schemas import UserProfile


class DiscoveredCompanyItem(BaseModel):
    name: str = Field(..., description="Company name")
    domain: str = Field(..., description="Primary domain, e.g. nxp.com")
    country: str = Field(..., description="Country headquarters or primary lab")
    industry: str = Field(..., description="Engineering domain, e.g. RF & Microwave Defense Electronics")
    careers_url: str = Field(..., description="Careers URL or ATS link (Workday, Greenhouse, Lever, Ashby, or company careers)")
    fit_rationale: str = Field(..., description="Why this company fits candidate's RF/Hardware/Embedded profile")


class DiscoveredCompanyBatch(BaseModel):
    companies: List[DiscoveredCompanyItem] = Field(..., description="List of discovered engineering employers")


# Curated seed database of tier-1 employers with verified direct ATS APIs
CURATED_SEED_COMPANIES: List[Dict[str, Any]] = [
    # NETHERLANDS
    {
        "name": "NXP Semiconductors (Europe)",
        "domain": "nxp.com",
        "country": "Netherlands",
        "industry": "Automotive Radar, RF Front-Ends & Secure Embedded Hardware",
        "careers_url": "https://nxp.wd3.myworkdayjobs.com/careers",
    },
    {
        "name": "QuantWare (Netherlands)",
        "domain": "quantware.com",
        "country": "Netherlands",
        "industry": "Superconducting Quantum Processors & Microwave RF Design",
        "careers_url": "https://jobs.ashbyhq.com/quantware",
    },
    # FRANCE
    {
        "name": "Thales Group (Europe)",
        "domain": "thalesgroup.com",
        "country": "France",
        "industry": "Radar, RF Antennas, Defense Electronics & Avionics",
        "careers_url": "https://thales.wd3.myworkdayjobs.com/Careers",
    },
    {
        "name": "Alta Ares (France)",
        "domain": "alta-ares.com",
        "country": "France",
        "industry": "Radar Systems, FPGA Electronic Warfare & Interceptors",
        "careers_url": "https://jobs.ashbyhq.com/alta-ares",
    },
    {
        "name": "Alice & Bob (France)",
        "domain": "alice-bob.com",
        "country": "France",
        "industry": "Fault-Tolerant Quantum Hardware, Microwave Electronics & FPGA",
        "careers_url": "https://jobs.lever.co/alice-bob",
    },
    # GERMANY
    {
        "name": "Helsing (Germany & Europe)",
        "domain": "helsing.ai",
        "country": "Germany",
        "industry": "Defense AI, Real-Time Sensor Processing & Rugged Embedded Hardware",
        "careers_url": "https://boards.greenhouse.io/helsing",
    },
    {
        "name": "Isar Aerospace (Germany)",
        "domain": "isaraerospace.com",
        "country": "Germany",
        "industry": "Launch Vehicle Avionics, Embedded Controls & Power Distribution",
        "careers_url": "https://boards.greenhouse.io/isaraerospace",
    },
    {
        "name": "The Exploration Company (Germany/France)",
        "domain": "exploration.space",
        "country": "Germany",
        "industry": "Orbital Spacecraft Avionics, Telemetry & Space Electronics",
        "careers_url": "https://jobs.ashbyhq.com/the-exploration-company",
    },
    {
        "name": "Rocket Factory Augsburg (Germany)",
        "domain": "rfa.space",
        "country": "Germany",
        "industry": "Rocket Avionics, Electronic Actuators & Embedded Flight Computers",
        "careers_url": "https://boards.greenhouse.io/rocketfactoryaugsburgag",
    },
    {
        "name": "Sensmore (Germany)",
        "domain": "sensmore.ai",
        "country": "Germany",
        "industry": "Radar Sensor Electronics, Embedded Robotics & Microcontroller Hardware",
        "careers_url": "https://jobs.ashbyhq.com/sensmore",
    },
    # IRELAND
    {
        "name": "Analog Devices (Europe)",
        "domain": "analog.com",
        "country": "Ireland",
        "industry": "Mixed-Signal, RF Transceivers, Sensor Interfaces & Power ICs",
        "careers_url": "https://analogdevices.wd1.myworkdayjobs.com/External",
    },
    # UNITED KINGDOM
    {
        "name": "Graphcore (UK)",
        "domain": "graphcore.ai",
        "country": "UK",
        "industry": "AI Silicon, Multilayer PCB Design & Hardware Validation",
        "careers_url": "https://boards.greenhouse.io/graphcore",
    },
    {
        "name": "Spire Global (UK/Luxembourg)",
        "domain": "spire.com",
        "country": "UK",
        "industry": "Earth Observation RF Payloads, Satellite Avionics & Ground Stations",
        "careers_url": "https://boards.greenhouse.io/spire",
    },
    {
        "name": "Foundational (UK)",
        "domain": "foundational.space",
        "country": "UK",
        "industry": "Satellite Laser Ranging, Ground Hardware & Space Electronics",
        "careers_url": "https://jobs.ashbyhq.com/foundational",
    },
    # USA
    {
        "name": "SpaceX / Starlink",
        "domain": "spacex.com",
        "country": "USA",
        "industry": "Starlink Phased-Array Antennas, RFIC & Satellite Avionics",
        "careers_url": "https://boards.greenhouse.io/spacex",
    },
    {
        "name": "Astranis Space Technologies",
        "domain": "astranis.com",
        "country": "USA",
        "industry": "Geostationary Telecommunications & RF Payloads",
        "careers_url": "https://boards.greenhouse.io/astranis",
    },
    {
        "name": "Anduril Industries",
        "domain": "anduril.com",
        "country": "USA",
        "industry": "Autonomous Systems, RF Data Links & Edge Robotics",
        "careers_url": "https://boards.greenhouse.io/andurilindustries",
    },
    {
        "name": "Formlabs",
        "domain": "formlabs.com",
        "country": "USA",
        "industry": "Precision Embedded Systems, Actuation & Sensor Electronics",
        "careers_url": "https://boards.greenhouse.io/formlabs",
    },
    {
        "name": "Palantir Technologies",
        "domain": "palantir.com",
        "country": "USA",
        "industry": "Mission Edge Hardware, Embedded Linux & Defense Deployments",
        "careers_url": "https://jobs.lever.co/palantir",
    },
]


class CompanyDiscoveryAgent:
    """
    AI Company Discovery Agent:
    Dynamically identifies top engineering employers matching candidate preferences
    and registers them into the durable SQLite queue.
    """

    def __init__(self, db: StateDatabase, profile: UserProfile):
        self.db = db
        self.profile = profile

    def discover_and_register(self, max_companies: int = 50) -> List[Dict[str, Any]]:
        """
        Executes discovery using curated seed companies plus AI dynamic expansion.
        """
        registered = []
        seen_names = set()

        # 1. Register Curated Seed Companies matching target countries
        target_countries_lower = [c.lower() for c in self.profile.target_countries]
        is_global = any(w in " ".join(target_countries_lower) for w in ["worldwide", "global", "all", "any", "around the world", "all around the world"])
        print(f"[AI Discovery Agent] Matching against target countries: {', '.join(self.profile.target_countries)} (Global scope: {is_global})...")

        for comp in CURATED_SEED_COMPANIES:
            # Check country match
            c_country = comp["country"].lower()
            if is_global or not target_countries_lower or any(tc in c_country or c_country in tc for tc in target_countries_lower):
                comp_id = self.db.add_company(
                    name=comp["name"],
                    domain=comp["domain"],
                    country=comp["country"],
                    industry=comp["industry"],
                    careers_url=comp.get("careers_url", ""),
                )
                registered.append({
                    "id": comp_id,
                    "name": comp["name"],
                    "country": comp["country"],
                    "domain": comp["domain"],
                    "careers_url": comp.get("careers_url", ""),
                })
                seen_names.add(comp["name"].lower())

        print(f"[AI Discovery Agent] Registered {len(registered)} curated tier-1 hardware employers.")

        # 2. Dynamic AI Discovery if LLM is available
        if ai_engine.is_live and len(registered) < max_companies:
            print("[AI Discovery Agent] Activating LLM Discovery for target region expansion...")
            ai_discovered = self._discover_with_ai(target_count=max_companies - len(registered))
            for comp in ai_discovered:
                if comp.name.lower() not in seen_names:
                    comp_id = self.db.add_company(
                        name=comp.name,
                        domain=comp.domain,
                        country=comp.country,
                        industry=comp.industry,
                        careers_url=comp.careers_url,
                    )
                    registered.append({
                        "id": comp_id,
                        "name": comp.name,
                        "country": comp.country,
                        "domain": comp.domain,
                        "careers_url": comp.careers_url,
                    })
                    seen_names.add(comp.name.lower())
                    print(f"  * [AI Discovered] {comp.name} ({comp.country}) - {comp.industry}")

        return registered[:max_companies]

    def _discover_with_ai(self, target_count: int = 15) -> List[DiscoveredCompanyItem]:
        """Uses LLM to discover innovative tech firms with physical hardware/RF labs."""
        prompt = f"""You are a specialized AI Engineering Recruiter and Tech Market Researcher.
Find {target_count} innovative engineering employers with active {self.profile.primary_domain} development.

CANDIDATE TARGET CRITERIA:
- Target Countries: {', '.join(self.profile.target_countries)}
- Primary Domain: {self.profile.primary_domain}
- Core Skills: {', '.join(self.profile.must_have_skills)}
- Target Disciplines: {', '.join(self.profile.target_roles)}

REQUIREMENTS:
1. Focus on employers in the specified target countries (e.g. Netherlands, Germany, France, Ireland, UK, Switzerland, Austria, USA).
2. Prioritize companies using standard ATS platforms (Workday, Greenhouse, Lever, Ashby, SmartRecruiters) or public career portals.
3. Include real, valid company domains and career URLs.
4. Provide a 1-sentence fit rationale for each company.
"""
        batch = ai_engine.generate_structured(
            prompt=prompt,
            response_schema=DiscoveredCompanyBatch,
            system_instruction="You are an expert AI Tech Discovery Agent. Return only valid DiscoveredCompanyBatch JSON.",
        )
        return batch.companies if batch else []
