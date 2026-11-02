"""
Evaluation Benchmark Tests for Matching & Verification Precision.
Tests matching logic against the 100-job ground-truth golden dataset and synthetic benchmarks.
Ensures Precision >= 85% and Quote-Validity Rate == 100%.
"""

import unittest
from unittest.mock import patch
from src.agents.career_checker import CareerCheckerWorker
from src.agents.llm_engine import ai_engine
from src.db import StateDatabase
from src.eval import get_benchmark_profile, run_evaluation_benchmark
from src.schemas import SeniorityLevel, UserProfile


class TestEvaluationBenchmark(unittest.TestCase):
    def setUp(self):
        self.live_patcher = patch.object(ai_engine, "is_live", False)
        self.live_patcher.start()

    def tearDown(self):
        self.live_patcher.stop()

    def test_golden_dataset_benchmark_targets(self):
        """Golden evaluation benchmark must achieve >= 85% precision and 100% quote validity."""
        results = run_evaluation_benchmark(
            golden_path="tests/golden/golden_jobs.json",
            min_score=50,
        )
        self.assertTrue(results["passed"], "Benchmark acceptance criteria not met")
        self.assertGreaterEqual(results["precision"], 0.85, f"Precision was {results['precision']:.2%}")
        self.assertAlmostEqual(results["quote_validity_rate"], 1.0, places=2)
        self.assertGreaterEqual(results["closed_detection_rate"], 0.90)

    def test_synthetic_10_role_benchmark(self):
        """Verifies CareerCheckerWorker precision on synthetic engineering vs business roles."""
        db = StateDatabase(":memory:")
        profile = UserProfile(
            name="Candidate",
            current_location="Generic Location",
            primary_domain="Electronics & RF Hardware",
            target_roles=["Hardware Design Engineer", "RF Engineer", "Embedded Systems Engineer", "PCB Design Engineer"],
            seniority_levels=[SeniorityLevel.MID, SeniorityLevel.SENIOR],
            target_countries=["USA", "UK", "Germany"],
            target_industries=["Semiconductors", "Aerospace"],
            must_have_skills=["RF Electronics", "PCB Design", "Embedded C", "FPGA"],
            nice_to_have_skills=["Python", "HFSS"],
            constraints=["Visa sponsorship required"],
            summary="Hardware & RF Engineer",
        )

        worker = CareerCheckerWorker(db=db, profile=profile)

        eval_set = [
            {
                "title": "Senior RF Hardware Engineer",
                "details": "Design RF transceivers, perform PCB layout, and validate matching circuits in the RF laboratory with vector network analyzers.",
                "relevant": True,
            },
            {
                "title": "Electrical Engineer - Satellite Bus",
                "details": "Develop spacecraft power systems, multilayer PCB design, and FPGA hardware controllers for satellite bus telemetry.",
                "relevant": True,
            },
            {
                "title": "Embedded Systems & Firmware Engineer",
                "details": "Write Embedded C firmware for microcontrollers and validate PCB hardware in lab using digital oscilloscopes.",
                "relevant": True,
            },
            {
                "title": "PCB Layout & Hardware Validation Engineer",
                "details": "Layout complex multilayer PCB boards in Altium and perform hardware signal integrity testing on prototypes.",
                "relevant": True,
            },
            {
                "title": "Antenna & RF Front-End Specialist",
                "details": "Design planar antennas, RF front-ends, and test in anechoic chamber across 5G frequency bands.",
                "relevant": True,
            },
            {
                "title": "FPGA / RTL Design Engineer",
                "details": "Implement FPGA logic in Verilog and perform hardware bring-up and verification on Xilinx test boards.",
                "relevant": True,
            },
            {
                "title": "Senior Corporate Legal Counsel",
                "details": "Manage corporate contracts, employment law, corporate acquisitions, and regulatory compliance.",
                "relevant": False,
            },
            {
                "title": "Technical Recruiter - Talent",
                "details": "Source candidates, screen engineering resumes, schedule phone screens, and manage interview pipelines.",
                "relevant": False,
            },
            {
                "title": "Global Account Executive - Financial Sector",
                "details": "Drive enterprise software sales quotas, manage executive relationships, and negotiate commercial deals.",
                "relevant": False,
            },
            {
                "title": "Brand Marketing & Communications Manager",
                "details": "Lead international advertising campaigns, social media branding, market positioning, and corporate PR.",
                "relevant": False,
            },
        ]

        tp, fp, tn, fn = 0, 0, 0, 0
        for item in eval_set:
            res = worker._score_job(title=item["title"], location="USA", details_text=item["details"])
            pred = res["match_score"] >= 50
            if pred and item["relevant"]:
                tp += 1
            elif pred and not item["relevant"]:
                fp += 1
            elif not pred and not item["relevant"]:
                tn += 1
            else:
                fn += 1

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        self.assertEqual(fp, 0, "No business/HR roles may be falsely classified as engineering")
        self.assertGreaterEqual(precision, 0.85)


if __name__ == "__main__":
    unittest.main()
