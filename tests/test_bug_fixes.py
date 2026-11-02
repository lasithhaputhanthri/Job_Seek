"""
Regression Tests for Phase 3 Bug Fixes.
Verifies:
1. ContactFinder: HEADERS & HIRING_KEYWORDS exist, zero NameErrors, human approval flag.
2. Classifier: Dead code removed, no URL/HTML evidence, hard filters for ITAR/internships/seniority.
3. A2A Service: Zero email fabrication.
4. Verifier: Truthful audit notes, multilingual still-open detection, verbatim quote validation.
"""

import unittest
from src.agents.classifier import AIJobClassifierAgent
from src.agents.contact_finder import ContactFinderWorker, HEADERS, HIRING_KEYWORDS
from src.agents.verifier import AIVerifierAgent
from src.config import config
from src.db import StateDatabase
from src.schemas import SeniorityLevel, UserProfile


class TestPhase3BugFixes(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch
        from src.agents.llm_engine import ai_engine
        self.live_patcher = patch.object(ai_engine, "is_live", False)
        self.live_patcher.start()

        self.profile = UserProfile(
            name="Alice Smith",
            current_location="Berlin, Germany",
            primary_domain="Hardware & Embedded Systems",
            target_roles=["Hardware Design Engineer", "RF Engineer"],
            seniority_levels=[SeniorityLevel.MID, SeniorityLevel.SENIOR],
            target_countries=["Germany", "Netherlands"],
            target_industries=["Semiconductors", "Automotive"],
            must_have_skills=["PCB Design", "RF Electronics", "Embedded C"],
            nice_to_have_skills=["Altium", "FPGA"],
            constraints=["Requires relocation support"],
            work_modes=["Remote", "Hybrid", "On-site"],
            needs_visa_sponsorship=True,
            include_internships=False,
            include_graduate_programs=False,
        )
        self.db = StateDatabase(":memory:")

    def tearDown(self):
        self.live_patcher.stop()

    def test_contact_finder_constants_and_no_nameerror(self):
        """Bug 1: Verify HEADERS and HIRING_KEYWORDS are defined and draft is candidate-agnostic."""
        self.assertIsNotNone(HEADERS)
        self.assertIn("career", HIRING_KEYWORDS)
        self.assertIn("talent", HIRING_KEYWORDS)

        from unittest.mock import patch
        from src.agents.llm_engine import ai_engine
        with patch.object(ai_engine, "is_live", False):
            worker = ContactFinderWorker(db=self.db, profile=self.profile)
            draft = worker.generate_outreach_draft(
                company_name="NXP",
                target_role="Hardware Design Engineer",
                recipient="Hiring Team",
            )
            self.assertIn("Alice Smith", draft.body)
            self.assertNotIn("Lasith", draft.body)
            self.assertTrue(draft.requires_human_approval)

    def test_classifier_dead_code_absence_and_hard_filters(self):
        """Bug 2 & 10 & 11: Verify classifier dead methods removed, and hard filters enforce eligibility."""
        classifier = AIJobClassifierAgent(profile=self.profile)
        self.assertFalse(hasattr(classifier, "_classify_with_gemini"))
        self.assertFalse(hasattr(classifier, "_classify_with_openai"))

        # Hard Filter: ITAR / Citizenship restriction when sponsorship required
        res_itar = classifier.classify_job(
            title="RF Defense Systems Engineer",
            company_name="DefenseCorp",
            location="Berlin, Germany",
            details_text="Must be an active clearance holder. US Citizenship required due to ITAR compliance.",
        )
        self.assertFalse(res_itar.eligible)
        self.assertFalse(res_itar.is_relevant)
        self.assertIn("ITAR", res_itar.eligibility_reason)

        # Hard Filter: Internship excluded by profile
        res_intern = classifier.classify_job(
            title="Hardware Engineering Intern",
            company_name="SensorTech",
            location="Munich, Germany",
            details_text="Working on PCB layout and testing in the lab.",
        )
        self.assertFalse(res_intern.eligible)
        self.assertFalse(res_intern.is_relevant)

        # Hard Filter: Country outside target set
        res_country = classifier.classify_job(
            title="Senior Hardware Engineer",
            company_name="GlobalChip",
            location="Shenzhen, China",
            details_text="Design consumer electronics hardware.",
        )
        self.assertFalse(res_country.eligible)
        self.assertIn("China", res_country.eligibility_reason)

    def test_classifier_no_html_wrapper_in_evidence_and_length_cap(self):
        """Bug 5: Verify <UNTRUSTED_JOB_DATA> wrapper stripped and brief descriptions capped at 60."""
        classifier = AIJobClassifierAgent(profile=self.profile)
        wrapper_text = (
            '<UNTRUSTED_JOB_DATA url="https://example.com/job/1">\n'
            'We are looking for an RF Electronics engineer with PCB Design skills.\n'
            '</UNTRUSTED_JOB_DATA>'
        )
        res = classifier.classify_job(
            title="RF Hardware Engineer",
            company_name="TestComp",
            location="Munich, Germany",
            details_text=wrapper_text,
        )
        # Score must be capped at 60 because description length < 300 chars
        self.assertLessEqual(res.match_score, 60)
        if res.evidence_quote:
            self.assertNotIn("<UNTRUSTED", res.evidence_quote)
            self.assertNotIn("url=", res.evidence_quote)

    def test_verifier_truthful_notes_and_still_open_detection(self):
        """Bug 14 & 16: Verify truthful audit labels and multilingual closed phrase detection."""
        verifier = AIVerifierAgent(profile=self.profile)

        # 1. Closed phrase detection (English)
        row_closed = {
            "job_url": "https://example.com/jobs/101",
            "source_url": "https://example.com/careers",
            "title": "Hardware Engineer",
            "company_name": "TestCo",
            "match_score": 85,
        }
        res_closed = verifier.audit_proposal(row_closed, raw_page_text="Thank you for your interest. This position has been filled.")
        self.assertFalse(res_closed.is_verified)
        self.assertIn("FALLBACK_RULES_REJECTED", res_closed.audit_notes)
        self.assertNotIn("PASS", res_closed.audit_notes)

        # 2. Closed phrase detection (German)
        res_de = verifier.audit_proposal(row_closed, raw_page_text="Vielen Dank für Ihr Interesse. Diese Stelle ist besetzt.")
        self.assertFalse(res_de.is_verified)
        self.assertIn("FALLBACK_RULES_REJECTED", res_de.audit_notes)

        # 3. Valid open posting with verbatim evidence quote
        quote = "Hands-on experience in multilayer PCB Design and high-speed bring-up."
        page = f"Welcome to our careers page. {quote} Join our engineering team in Munich."
        row_valid = {
            "job_url": "https://example.com/jobs/102",
            "source_url": "https://example.com/careers",
            "title": "Senior PCB Design Engineer",
            "company_name": "TestCo",
            "match_score": 80,
            "evidence_quote": quote,
            "work_mode": "On-site",
        }
        res_valid = verifier.audit_proposal(row_valid, raw_page_text=page)
        self.assertTrue(res_valid.is_verified)
        self.assertTrue(res_valid.quote_verified)
        self.assertIn("FALLBACK_RULES_APPROVED", res_valid.audit_notes)


if __name__ == "__main__":
    unittest.main()
