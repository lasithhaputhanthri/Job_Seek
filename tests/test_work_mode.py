"""
Regression tests for Work Mode classification (Remote, Hybrid, On-site).
Verifies that:
1. Genuine Remote postings (100% remote, work from home full-time, etc.) are detected.
2. Genuine Hybrid postings (2-3 days in office, hybrid workplace, etc.) are detected.
3. Hardware/RF engineering jargon does NOT cause false positives:
   - "hybrid beamforming", "hybrid couplers", "hybrid propulsion", "hybrid circuits" -> On-site
   - "remotely piloted aircraft", "remote sensing", "remote procedure calls" -> On-site
   - SpaceX Starlink "remote parts of the globe" -> On-site
4. Physical hardware lab roles default to On-site.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.career_checker import CareerCheckerWorker
from src.agents.llm_engine import ai_engine
from src.db import StateDatabase
from src.schemas import SeniorityLevel, UserProfile


class TestWorkModeClassification(unittest.TestCase):
    def setUp(self):
        self.live_patcher = patch.object(ai_engine, "is_live", False)
        self.live_patcher.start()

        db = StateDatabase(":memory:")
        profile = UserProfile(
            name="Candidate",
            current_location="Generic Location",
            primary_domain="Electronics & Hardware",
            target_roles=["Hardware Engineer", "RF Engineer"],
            seniority_levels=[SeniorityLevel.MID],
            target_countries=["Worldwide"],
            target_industries=["Electronics"],
            must_have_skills=["RF", "PCB"],
            nice_to_have_skills=[],
            constraints=[],
            summary="Engineer",
        )
        self.checker = CareerCheckerWorker(db=db, profile=profile)

    def tearDown(self):
        self.live_patcher.stop()

    def test_genuine_remote_titles(self):
        self.assertEqual(self.checker._detect_work_mode("Senior Embedded Software Engineer (Remote)", "Berlin, Germany", ""), "Remote")
        self.assertEqual(self.checker._detect_work_mode("Firmware Engineer - Remote", "Munich", ""), "Remote")
        self.assertEqual(self.checker._detect_work_mode("RF Simulation Specialist", "Remote, United Kingdom", ""), "Remote")
        self.assertEqual(self.checker._detect_work_mode("Embedded Linux Developer", "Work from home, France", ""), "Remote")

    def test_genuine_remote_body(self):
        text = "Join our distributed team. This is a 100% remote opportunity for European candidates with flexible hours."
        self.assertEqual(self.checker._detect_work_mode("Embedded Software Engineer", "Germany", text), "Remote")

        text2 = "We are hiring for a fully remote position with occasional meetups in Amsterdam."
        self.assertEqual(self.checker._detect_work_mode("Hardware Simulation Engineer", "Netherlands", text2), "Remote")

    def test_genuine_hybrid(self):
        self.assertEqual(self.checker._detect_work_mode("Hardware Engineer (Hybrid)", "Paris, France", ""), "Hybrid")
        self.assertEqual(self.checker._detect_work_mode("Embedded Software Engineer", "Hybrid - London", ""), "Hybrid")

        text = "We operate a hybrid workplace model with 2 days per week in the Dublin lab and 3 days from home."
        self.assertEqual(self.checker._detect_work_mode("FPGA Verification Engineer", "Dublin, Ireland", text), "Hybrid")

    def test_engineering_jargon_not_falsely_classified(self):
        # SpaceX Starlink mission false positive trap
        tx_spacex = "Connecting users in the most remote parts of the globe using phased arrays and hybrid beamforming."
        self.assertEqual(self.checker._detect_work_mode("Antenna Engineer (Starlink)", "Bastrop, TX", tx_spacex), "On-site")

        # Anduril defense false positive trap
        tx_anduril = "Develop avionics for remotely piloted aircraft and autonomous hybrid propulsion systems."
        self.assertEqual(self.checker._detect_work_mode("Flight Software Engineer", "Costa Mesa, CA", tx_anduril), "On-site")

        # Formlabs RPC false positive trap
        tx_formlabs = "Implement remote procedure calls (RPC) and board bring-up. Onsite lab testing in Somerville."
        self.assertEqual(self.checker._detect_work_mode("Embedded Firmware Engineer", "Somerville, MA", tx_formlabs), "On-site")

        # RF Microwave hybrid IC trap
        tx_rf = "Design hybrid microwave integrated circuits (HMIC) and 3dB hybrid couplers in the cleanroom."
        self.assertEqual(self.checker._detect_work_mode("MMIC Design Engineer", "Chelmsford, MA", tx_rf), "On-site")

        # Radar anechoic chamber
        tx_radar = "Bring up radar processor boards and perform antenna measurements in the RF anechoic chamber."
        self.assertEqual(self.checker._detect_work_mode("Digital Hardware Engineer", "Hengelo, Netherlands", tx_radar), "On-site")


if __name__ == "__main__":
    unittest.main()
