"""
Unit Tests for src/text_match.py.
Verifies word-boundary precision, Unicode handling, non-engineering role filters,
and technical jargon protection.
"""

import unittest
from src.text_match import (
    matches_word,
    contains_any_word,
    find_matched_keywords,
    is_non_engineering_role,
    is_internship_or_graduate,
    contains_technical_work_mode_jargon,
    is_genuine_remote_indicator,
    is_genuine_hybrid_indicator,
    extract_visa_and_citizenship_signals,
)


class TestTextMatch(unittest.TestCase):
    def test_word_boundary_negative_substrings(self):
        """Verify short keywords do NOT match inside unrelated words."""
        # 'rf' in 'performance', 'transform', 'surface', 'tariff'
        self.assertFalse(matches_word("rf", "High performance computing system"))
        self.assertFalse(matches_word("rf", "Surface acoustic wave filter transform"))
        self.assertFalse(matches_word("rf", "Tariff analysis report"))

        # 'hr' in 'through', 'threat', 'chronic'
        self.assertFalse(matches_word("hr", "Working through complex algorithms"))
        self.assertFalse(matches_word("hr", "Mitigating threat models"))

        # 'sales' in 'salesforce'
        self.assertFalse(matches_word("sales", "Integration with Salesforce CRM"))

        # 'uk' in 'ukraine'
        self.assertFalse(matches_word("uk", "Based in Kyiv, Ukraine"))

        # 'test' in 'latest', 'fastest'
        self.assertFalse(matches_word("test", "Using the latest technology and fastest algorithms"))

        # 'us' in 'status', 'focus', 'bonus'
        self.assertFalse(matches_word("us", "Candidate status, focus on bonus structure"))

    def test_word_boundary_positive_matches(self):
        """Verify words match correctly on boundaries, punctuation, and casing."""
        self.assertTrue(matches_word("rf", "Senior RF Hardware Engineer"))
        self.assertTrue(matches_word("rf", "Design RF/Microwave front-end modules"))
        self.assertTrue(matches_word("rf", "RF-frontend testing"))
        self.assertTrue(matches_word("hr", "Contact the HR department"))
        self.assertTrue(matches_word("sales", "Technical Sales Engineer"))
        self.assertTrue(matches_word("uk", "Bristol, UK"))
        self.assertTrue(matches_word("uk", "Remote - UK"))
        self.assertTrue(matches_word("test", "Hardware Test Engineer"))
        self.assertTrue(matches_word("us", "Austin, US"))
        self.assertTrue(matches_word("c/c++", "Strong proficiency in C/C++"))

    def test_non_engineering_role_detection(self):
        """Verify non-engineering roles are flagged accurately."""
        self.assertTrue(is_non_engineering_role("Technical Recruiter - Engineering Talent"))
        self.assertTrue(is_non_engineering_role("Enterprise Account Executive"))
        self.assertTrue(is_non_engineering_role("Senior Corporate Legal Counsel"))
        self.assertTrue(is_non_engineering_role("Global Brand Marketing Manager"))
        self.assertTrue(is_non_engineering_role("Head of Human Resources"))
        self.assertFalse(is_non_engineering_role("Senior Embedded Systems Engineer"))
        self.assertFalse(is_non_engineering_role("RF Microwave Design Engineer"))

    def test_internship_detection(self):
        """Verify internships, working students, and graduate schemes are detected."""
        self.assertTrue(is_internship_or_graduate("Hardware Engineering Intern - Summer 2026"))
        self.assertTrue(is_internship_or_graduate("Werkstudent - Embedded Software"))
        self.assertTrue(is_internship_or_graduate("Graduate Trainee - Power Electronics"))
        self.assertFalse(is_internship_or_graduate("Senior Hardware Design Engineer"))
        self.assertFalse(is_internship_or_graduate("Principal RF Engineer"))

    def test_technical_jargon_vs_work_mode(self):
        """Verify technical engineering terminology is not misclassified as workplace policy."""
        # Hybrid beamforming / couplers are NOT hybrid workplace
        self.assertTrue(contains_technical_work_mode_jargon("hybrid beamforming antenna array"))
        self.assertTrue(contains_technical_work_mode_jargon("90 degree hybrid coupler"))
        self.assertFalse(is_genuine_hybrid_indicator("Develop hybrid beamforming architectures for 5G mmWave."))
        self.assertFalse(is_genuine_hybrid_indicator("Design planar hybrid couplers and power splitters."))

        # Remote sensing / RPC are NOT remote jobs
        self.assertTrue(contains_technical_work_mode_jargon("satellite remote sensing payload"))
        self.assertTrue(contains_technical_work_mode_jargon("microservice remote procedure calls (RPC)"))
        self.assertFalse(is_genuine_remote_indicator("Processing remote sensing data from satellite radar."))
        self.assertFalse(is_genuine_remote_indicator("Optimize RPC communication over CAN bus."))

        # Genuine Remote & Hybrid policies
        self.assertTrue(is_genuine_remote_indicator("This is a 100% remote position across Europe."))
        self.assertTrue(is_genuine_remote_indicator("Work from home with flexible hours."))
        self.assertTrue(is_genuine_hybrid_indicator("We offer a hybrid workplace with 2 days in office."))
        self.assertTrue(is_genuine_hybrid_indicator("Hybrid schedule: 3 days office, 2 days home."))

    def test_visa_and_citizenship_extraction(self):
        """Verify detection of clearance/citizenship restrictions and sponsorship."""
        # Clearance / ITAR restriction
        text_clearance = "Position requires an active Secret Security Clearance. US citizenship required due to ITAR."
        visa_stat, cit_req, quote = extract_visa_and_citizenship_signals(text_clearance)
        self.assertTrue(cit_req)
        self.assertEqual(visa_stat, "no")
        self.assertIsNotNone(quote)

        # Explicit visa sponsorship
        text_sponsor = "We offer comprehensive relocation support and visa sponsorship for international applicants."
        visa_stat2, cit_req2, quote2 = extract_visa_and_citizenship_signals(text_sponsor)
        self.assertFalse(cit_req2)
        self.assertEqual(visa_stat2, "yes")
        self.assertIsNotNone(quote2)

        # Neutral / unknown
        text_neutral = "Designing microcontrollers and embedded firmware for industrial sensors."
        visa_stat3, cit_req3, quote3 = extract_visa_and_citizenship_signals(text_neutral)
        self.assertFalse(cit_req3)
        self.assertEqual(visa_stat3, "unknown")
        self.assertIsNone(quote3)


if __name__ == "__main__":
    unittest.main()
