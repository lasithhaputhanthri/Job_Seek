"""
Integration Tests for AIMassiveJobDirectoryAgent.
Verifies:
1. Massive Company Directory initialization and curated registry loading.
2. Dynamic AI sector expansion capability.
3. Job websites registry discovery and API accessibility.
4. Autonomous job scouting across company ATS portals with AI classification and verification.
"""

import asyncio
import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.llm_engine import ai_engine
from src.agents.massive_scout import AIMassiveJobDirectoryAgent, CURATED_HARDWARE_DIRECTORY, JOB_WEBSITES_REGISTRY
from src.db import StateDatabase
from src.schemas import SeniorityLevel, UserProfile


class TestMassiveJobDirectoryAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live_patcher = patch.object(ai_engine, "is_live", False)
        cls.live_patcher.start()

        cls.test_db_path = f"data/test_massive_{uuid.uuid4().hex[:8]}.db"
        cls.db = StateDatabase(cls.test_db_path)
        cls.profile = UserProfile(
            name="Candidate",
            current_location="Generic Location",
            primary_domain="Electronics, RF & Embedded Hardware",
            target_roles=["Hardware Design Engineer", "RF Engineer", "Embedded Hardware Engineer"],
            seniority_levels=[SeniorityLevel.MID, SeniorityLevel.SENIOR],
            target_countries=["Netherlands", "Germany", "France", "USA", "Australia", "UK"],
            target_industries=["Semiconductors", "Defense", "Aerospace", "Robotics"],
            must_have_skills=["Multilayer PCB Layout", "RF Front-End", "Antenna Design", "Embedded C"],
            nice_to_have_skills=["LTspice", "Altium Designer"],
            constraints=["Requires relocation or visa sponsorship"],
            summary="Hardware, RF & Embedded Systems Engineer",
            work_modes=["Remote", "Hybrid", "On-site"],
        )
        cls.agent = AIMassiveJobDirectoryAgent(db=cls.db, profile=cls.profile)

    @classmethod
    def tearDownClass(cls):
        cls.live_patcher.stop()
        del cls.agent
        del cls.db
        import gc
        gc.collect()
        if Path(cls.test_db_path).exists():
            try:
                os.remove(cls.test_db_path)
            except Exception:
                pass

    def test_curated_directory_contains_key_employers(self):
        """Curated directory must contain tier-1 global hardware and RF employers."""
        names = [c["name"].lower() for c in CURATED_HARDWARE_DIRECTORY]
        self.assertTrue(any("nxp" in n for n in names), "NXP Semiconductors must be in curated directory")
        self.assertTrue(any("rohde" in n for n in names), "Rohde & Schwarz must be in curated directory")
        self.assertTrue(any("thales" in n for n in names), "Thales must be in curated directory")
        self.assertTrue(any("analog devices" in n for n in names), "Analog Devices must be in curated directory")
        self.assertTrue(any("morse micro" in n for n in names), "Morse Micro must be in curated directory")
        self.assertGreaterEqual(len(CURATED_HARDWARE_DIRECTORY), 40)

    def test_build_massive_directory(self):
        """Agent builds directory, registers companies in DB, and creates durable tasks."""
        companies = self.agent.build_massive_directory(
            target_count=30,
            enable_ai_expansion=False,  # test deterministic curated ingestion
            save_to_json=True,
        )
        self.assertGreaterEqual(len(companies), 20)

        # Check DB companies
        db_companies = self.db.get_companies()
        self.assertGreaterEqual(len(db_companies), 20)

        # Check tasks created
        tasks = self.db.fetch_pending_tasks(task_type="CAREER_CHECK", limit=50)
        self.assertGreaterEqual(len(tasks), 20)

    def test_job_websites_registry(self):
        """Agent provides supported job websites with valid API types."""
        sites = self.agent.list_job_websites()
        self.assertGreaterEqual(len(sites), 5)
        names = [s.name.lower() for s in sites]
        self.assertTrue(any("arbeitnow" in n for n in names))
        self.assertTrue(any("remotive" in n for n in names))
        self.assertTrue(any("jobicy" in n for n in names))
        self.assertTrue(any("greenhouse" in n for n in names))
        self.assertTrue(any("workday" in n for n in names))

    def test_scout_sample_company_jobs(self):
        """Agent scouts a test company and executes AI classification and audit with mocked inputs."""
        async def _test():
            test_companies = [
                {
                    "id": 1,
                    "name": "QuantWare",
                    "country": "Netherlands",
                    "careers_url": "https://jobs.ashbyhq.com/quantware",
                }
            ]
            mock_jobs = [
                {
                    "title": "RF Systems Engineer",
                    "location": "Delft, Netherlands",
                    "job_url": "https://jobs.ashbyhq.com/quantware/job/1",
                    "department": "Engineering",
                }
            ]
            mock_details = {
                "status": "success",
                "description": "Design microwave RF quantum readout circuitry on site in Delft.",
                "character_count": 65,
            }
            with patch("mcp_servers.career_page_reader.server.list_jobs", return_value=mock_jobs):
                with patch("mcp_servers.career_page_reader.server.get_job_details", return_value=mock_details):
                    stats = await self.agent.scout_companies_for_jobs(
                        companies=test_companies,
                        max_jobs_per_company=5,
                        concurrency=2,
                    )
            self.assertIn("companies_scanned", stats)
            self.assertEqual(stats["companies_scanned"], 1)

        asyncio.run(_test())


if __name__ == "__main__":
    unittest.main()
