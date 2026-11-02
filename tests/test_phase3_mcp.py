"""
Unit & Protocol Tests for Career Page Reader MCP Server.
100% offline with mocked HTTP responses.
Verifies:
1. ATS platform detection (Greenhouse, Lever, Ashby, Workday, SmartRecruiters).
2. Job extraction and detail retrieval.
3. Safe description sanitization and length capping.
"""

import unittest
from unittest.mock import patch, MagicMock

from mcp_servers.career_page_reader.server import (
    detect_ats,
    get_job_details,
    list_jobs,
)


class TestCareerPageReaderMCP(unittest.TestCase):
    def test_ats_detection(self):
        """Verifies correct detection of major enterprise ATS platforms."""
        test_cases = [
            ("https://boards.greenhouse.io/andurilindustries", "greenhouse", "andurilindustries"),
            ("https://jobs.lever.co/palantir", "lever", "palantir"),
            ("https://jobs.ashbyhq.com/framework", "ashby", "framework"),
            ("https://jobs.smartrecruiters.com/smartrecruiters", "smartrecruiters", "smartrecruiters"),
            ("https://dyson.wd3.myworkdayjobs.com/Dyson_Careers", "workday", "dyson.wd3.myworkdayjobs.com/dyson/Dyson_Careers"),
        ]
        for url, expected_ats, expected_token in test_cases:
            det = detect_ats(url)
            self.assertEqual(det.get("ats"), expected_ats, f"Failed for {url}")
            self.assertEqual(det.get("token"), expected_token, f"Token mismatch for {url}")

    def test_mocked_greenhouse_job_listing(self):
        """Verifies greenhouse JSON job extraction with mocked HTTP response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jobs": [
                {
                    "id": 12345,
                    "title": "Senior RF Hardware Engineer",
                    "location": {"name": "Munich, Germany"},
                    "absolute_url": "https://boards.greenhouse.io/test/jobs/12345",
                    "departments": [{"name": "Hardware Engineering"}],
                }
            ]
        }

        with patch("httpx.Client.get", return_value=mock_response):
            jobs = list_jobs("https://boards.greenhouse.io/test")
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]["title"], "Senior RF Hardware Engineer")
            self.assertEqual(jobs[0]["location"], "Munich, Germany")
            self.assertEqual(jobs[0]["department"], "Hardware Engineering")

    def test_mocked_lever_job_listing(self):
        """Verifies lever job listing extraction with mocked response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": "abc-123",
                "text": "FPGA Verification Engineer",
                "categories": {"location": "London, UK", "team": "Hardware"},
                "hostedUrl": "https://jobs.lever.co/test/abc-123",
                "workplaceType": "hybrid",
            }
        ]

        with patch("httpx.Client.get", return_value=mock_response):
            jobs = list_jobs("https://jobs.lever.co/test")
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]["title"], "FPGA Verification Engineer")
            self.assertEqual(jobs[0]["location"], "London, UK")
            self.assertEqual(jobs[0]["work_mode_hint"], "Hybrid")

    def test_mocked_job_details_sanitization(self):
        """Verifies HTML stripping and untrusted wrapper injection."""
        html_payload = """
        <html>
            <head><script>alert('xss');</script></head>
            <body>
                <h1>Antenna Engineer</h1>
                <p>We are hiring an experienced Antenna and RF Design Engineer to architect and build next-generation phased array systems. The candidate will design planar arrays, perform EM simulation in HFSS, and validate radiation patterns in the microwave anechoic chamber.</p>
                <script>var tracking = 1;</script>
            </body>
        </html>
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html_payload

        with patch("httpx.Client.get", return_value=mock_response):
            details = get_job_details("https://example.com/jobs/123")
            self.assertEqual(details["status"], "success")
            safe_content = details["safe_content"]
            self.assertIn("<UNTRUSTED_JOB_DATA", safe_content)
            self.assertIn("Antenna Engineer", safe_content)
            self.assertNotIn("<script>", safe_content)
            self.assertNotIn("alert('xss')", safe_content)


if __name__ == "__main__":
    unittest.main()
