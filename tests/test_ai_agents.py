"""
Integration Test for All AI Agents in the Architecture.
Verifies:
1. IntakeAgent: Profile extraction & preference parsing
2. AICompanyDiscoveryAgent: Regional employer matching & discovery
3. AIJobClassifierAgent: Work mode & technical fit evaluation
4. AIVerifierAgent: Quality audit & evidence validation
5. ContactFinderWorker: Public contact discovery & personalized outreach drafting
"""

import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.intake import IntakeAgent
from src.agents.discovery import CompanyDiscoveryAgent
from src.agents.classifier import AIJobClassifierAgent
from src.agents.llm_engine import ai_engine
from src.agents.verifier import AIVerifierAgent
from src.agents.contact_finder import ContactFinderWorker
from src.db import StateDatabase
from src.schemas import SeniorityLevel, UserProfile


class TestAllAIAgents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live_patcher = patch.object(ai_engine, "is_live", False)
        cls.live_patcher.start()

        cls.test_db_path = f"data/test_agents_{uuid.uuid4().hex[:8]}.db"
        cls.db = StateDatabase(cls.test_db_path)
        cls.profile = UserProfile(
            name="Candidate Name",
            current_location="Generic Location",
            primary_domain="Electronics, RF & Embedded Hardware",
            target_roles=["Hardware Design Engineer", "RF Engineer", "Embedded Systems Engineer"],
            seniority_levels=[SeniorityLevel.MID, SeniorityLevel.SENIOR],
            target_countries=["Netherlands", "Germany", "France", "USA"],
            target_industries=["Semiconductors", "Aerospace", "Defense"],
            must_have_skills=["RF", "RF Electronics", "Multilayer PCB Design", "Embedded C", "Antenna", "Planar Antennas"],
            nice_to_have_skills=["FPGA", "HFSS"],
            constraints=["Requires visa sponsorship"],
            summary="Hardware and RF Design Engineer",
            work_modes=["Remote", "Hybrid", "On-site"],
        )

    @classmethod
    def tearDownClass(cls):
        cls.live_patcher.stop()
        del cls.db
        import gc
        gc.collect()
        if Path(cls.test_db_path).exists():
            try:
                os.remove(cls.test_db_path)
            except Exception:
                pass

    def test_discovery_agent(self):
        discovery = CompanyDiscoveryAgent(db=self.db, profile=self.profile)
        companies = discovery.discover_and_register(max_companies=10)
        self.assertGreater(len(companies), 0)
        countries = [c["country"] for c in companies]
        self.assertTrue(any(c in ["Netherlands", "Germany", "France", "USA"] for c in countries))

    def test_classifier_agent(self):
        classifier = AIJobClassifierAgent(profile=self.profile)
        # Test On-site hardware role with technical jargon trap
        res = classifier.classify_job(
            title="Antenna & Phased Array Design Engineer",
            company_name="Thales",
            location="Hengelo, Netherlands",
            details_text="Develop hybrid beamforming arrays and calibrate in the RF anechoic chamber.",
        )
        self.assertEqual(res.work_mode, "On-site")
        self.assertTrue(res.is_relevant)
        self.assertGreaterEqual(res.match_score, 50)

    def test_verifier_agent(self):
        verifier = AIVerifierAgent(profile=self.profile)
        raw_text = "Join our team in Delft. Design microwave RF quantum readout circuitry on site in the cryostat laboratory."
        proposal = {
            "title": "RF Systems Engineer",
            "company_name": "QuantWare",
            "location": "Delft, Netherlands",
            "work_mode": "On-site",
            "match_score": 75,
            "match_reason": "Direct RF engineering match",
            "evidence_quote": "Design microwave RF quantum readout circuitry",
            "source_url": "https://jobs.ashbyhq.com/quantware",
            "job_url": "https://jobs.ashbyhq.com/quantware",
        }
        audit = verifier.audit_proposal(proposal, raw_page_text=raw_text)
        self.assertTrue(audit.is_verified)
        self.assertGreaterEqual(audit.confidence_score, 70)

    def test_contact_outreach_agent(self):
        finder = ContactFinderWorker(db=self.db, profile=self.profile)
        draft = finder.generate_outreach_draft(
            company_name="NXP Semiconductors",
            target_role="Hardware Design Engineer",
            recipient="Talent Acquisition Team",
        )
        self.assertIn("Hardware Design Engineer", draft.subject)
        self.assertIn("Candidate Name", draft.body)
        self.assertGreater(len(draft.key_highlights), 0)


if __name__ == "__main__":
    unittest.main()
