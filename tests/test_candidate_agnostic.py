"""
Unit Tests for Candidate-Agnostic Ingestion.
Verifies that the IntakeAgent and schemas function correctly on arbitrary CVs
without leaking or assuming any hardcoded personal data.
"""

import unittest
from src.agents.intake import IntakeAgent
from src.schemas import SeniorityLevel, UserProfile


class TestCandidateAgnosticIntake(unittest.TestCase):
    def test_deterministic_extraction_on_synthetic_cv(self):
        """Verify deterministic parser extracts correct profile for a completely new person."""
        synthetic_cv = """
        Elena Rostova
        Berlin, Germany | elena.rostova@example.com | +49 170 1234567

        PROFESSIONAL SUMMARY
        Embedded Software and Firmware Engineer with 5 years of experience in RTOS and ARM Cortex.

        EXPERIENCE
        Firmware Engineer (2020 - 2025)
        Bosch Mobility - Stuttgart, Germany
        - Developed bare-metal and FreeRTOS firmware for STM32 microcontrollers in C/C++.
        - Implemented CAN bus and SPI device drivers for automotive radar units.
        - Performed board bring-up and hardware debugging using oscilloscopes and logic analyzers.

        Junior Embedded Developer (2018 - 2020)
        Embedded Systems GmbH - Munich, Germany
        - Designed multilayer PCB layout in KiCad for sensor interface boards.

        EDUCATION
        B.Sc. in Electrical Engineering (2014 - 2018)
        Technical University of Munich
        """

        agent = IntakeAgent(target_countries=["Germany", "Netherlands", "France"])
        profile = agent._extract_deterministic(synthetic_cv)

        # Name must be Elena Rostova, NOT hardcoded Lasith
        self.assertEqual(profile.name, "Elena Rostova")
        self.assertIn("Germany", profile.current_location)
        self.assertTrue(any("Embedded" in r or "Hardware" in r for r in profile.target_roles))
        self.assertTrue(any("Firmware" in s or "Pcb" in s or "Embedded" in s for s in profile.must_have_skills))
        self.assertIn(SeniorityLevel.MID, profile.seniority_levels)

    def test_large_cv_chunking_warning(self):
        """Verify CVs larger than 8000 characters trigger graceful section chunking."""
        large_cv = "Header Information\n" + ("Long descriptive project details\n" * 500)
        self.assertGreater(len(large_cv), 8000)

        agent = IntakeAgent()
        chunked = agent._chunk_cv_text(large_cv, max_chars=8000)
        self.assertLessEqual(len(chunked), 8000)


if __name__ == "__main__":
    unittest.main()
