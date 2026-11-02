"""
Evaluation Benchmark Runner for Job_Seek Multi-Agent System.
Evaluates AIJobClassifierAgent and AIVerifierAgent against the 100-job Ground-Truth Golden Dataset.

Measures:
1. Precision (Must be >= 0.85)
2. Recall
3. F1 Score
4. Work Mode Classification Accuracy
5. Country Resolution Accuracy
6. Multilingual Still-Open Detection Rate (EN, DE, FR, NL, ES, IT)
7. Evidence Quote Validity Rate (Must be 100% - verbatim, non-empty, free of HTML/URLs)
"""

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import patch

from src.agents.classifier import AIJobClassifierAgent
from src.agents.llm_engine import ai_engine
from src.agents.verifier import AIVerifierAgent
from src.config import config
from src.schemas import SeniorityLevel, UserProfile

logger = logging.getLogger("EvalBenchmark")


def get_benchmark_profile() -> UserProfile:
    """Returns candidate-agnostic benchmark profile for ground-truth testing."""
    return UserProfile(
        name="Benchmark Candidate",
        current_location="Sri Lanka",
        primary_domain="Electronics, RF & Embedded Hardware",
        target_roles=[
            "RF Design Engineer",
            "Hardware Engineer",
            "Hardware Systems Engineer",
            "Embedded Systems Engineer",
            "Embedded Firmware Engineer",
            "FPGA Engineer",
            "Antenna Engineer",
            "PCB Layout Engineer",
            "Microwave Engineer",
        ],
        seniority_levels=[SeniorityLevel.MID, SeniorityLevel.SENIOR],
        target_countries=[
            "Netherlands",
            "Germany",
            "France",
            "Ireland",
            "United Kingdom",
            "United States",
            "Austria",
            "Switzerland",
            "Sweden",
            "Belgium",
            "Australia",
            "Spain",
            "Italy",
        ],
        target_industries=["Semiconductors", "Aerospace", "Defense", "Robotics", "Telecommunications"],
        must_have_skills=[
            "RF",
            "Hardware",
            "PCB",
            "FPGA",
            "Embedded C",
            "Antenna",
            "Microcontroller",
            "Microwave",
            "Electronics",
            "Firmware",
            "Analog",
        ],
        nice_to_have_skills=["Altium", "HFSS", "RTOS", "DSP"],
        constraints=["Requires visa sponsorship"],
        needs_visa_sponsorship=True,
        include_internships=False,
        include_graduate_programs=False,
        work_modes=["On-site", "Hybrid", "Remote"],
    )


def normalize_country(c: Optional[str]) -> str:
    """Normalizes country synonyms (e.g. USA/United States, UK/United Kingdom)."""
    if not c:
        return "Unknown"
    norm = c.lower().strip()
    synonyms = {
        "united states": "USA",
        "united states of america": "USA",
        "us": "USA",
        "usa": "USA",
        "united kingdom": "UK",
        "great britain": "UK",
        "uk": "UK",
    }
    return synonyms.get(norm, c.strip())


def is_valid_evidence_quote(quote: Optional[str], full_text: str) -> bool:
    """Checks whether an evidence quote strictly adheres to the evidence rules."""
    if not quote or not isinstance(quote, str):
        return False
    clean = quote.strip()
    if len(clean) < 15:
        return False
    # Check for forbidden artifacts: HTML tags or URL fragments
    if "<" in clean or ">" in clean or "&" in clean:
        return False
    if "http://" in clean or "https://" in clean or "www." in clean or ".com/" in clean or "job/" in clean:
        return False
    if "UNTRUSTED" in clean:
        return False
    # Must be a verbatim substring
    return clean in full_text


def run_evaluation_benchmark(
    golden_path: str = "tests/golden/golden_jobs.json",
    min_score: int = 50,
) -> Dict[str, Any]:
    """Runs evaluation benchmark against golden dataset."""
    path = Path(golden_path)
    if not path.exists():
        raise FileNotFoundError(f"Golden dataset not found at: {golden_path}")

    with open(path, "r", encoding="utf-8") as f:
        golden_jobs: List[Dict[str, Any]] = json.load(f)

    profile = get_benchmark_profile()
    classifier = AIJobClassifierAgent(profile=profile)
    verifier = AIVerifierAgent(profile=profile)

    tp, fp, tn, fn = 0, 0, 0, 0
    work_mode_correct = 0
    work_mode_total = 0
    country_correct = 0
    country_total = 0
    closed_detected = 0
    closed_total = 0
    valid_quotes = 0
    relevant_predicted_count = 0

    print("\n" + "=" * 78)
    print(f"RUNNING EVALUATION BENCHMARK ON {len(golden_jobs)} GOLDEN JOBS")
    print(f"Relevance Threshold Score: {min_score}")
    print("=" * 78)

    # Force offline deterministic evaluation for benchmark reproducibility
    with patch.object(ai_engine, "is_live", False):
        for job in golden_jobs:
            jid = job["id"]
            title = job["title"]
            company = job["company"]
            location = job["location"]
            description = job["description"]
            gt = job["ground_truth"]

            # Ground truth determination:
            # A job is a True Positive only if it is relevant, eligible, AND open.
            is_gt_positive = gt["is_relevant"] and gt["is_eligible"] and gt.get("is_open", True)

            # 1. Run Classifier
            classification = classifier.classify_job(
                title=title,
                company_name=company,
                location=location,
                details_text=description,
            )

            # 2. Check Still-Open via Verifier
            is_open_verdict = True
            if not gt.get("is_open", True):
                closed_total += 1
                proposal = {
                    "job_url": f"https://example.com/jobs/{jid}",
                    "source_url": f"https://example.com/jobs/{jid}",
                    "title": title,
                    "company_name": company,
                    "location": location,
                    "work_mode": classification.work_mode,
                    "match_score": classification.match_score,
                    "match_reason": classification.match_reason,
                    "evidence_quote": classification.evidence_quote,
                }
                audit_res = verifier.audit_proposal(proposal, raw_page_text=description)
                if not audit_res.still_open or not audit_res.is_verified:
                    closed_detected += 1
                    is_open_verdict = False
            else:
                # Also run verifier on open jobs to verify quote
                proposal = {
                    "job_url": f"https://example.com/jobs/{jid}",
                    "source_url": f"https://example.com/jobs/{jid}",
                    "title": title,
                    "company_name": company,
                    "location": location,
                    "work_mode": classification.work_mode,
                    "match_score": classification.match_score,
                    "match_reason": classification.match_reason,
                    "evidence_quote": classification.evidence_quote,
                }
                audit_res = verifier.audit_proposal(proposal, raw_page_text=description)

            # System prediction: job is approved if classified relevant, eligible, and verified open
            predicted_positive = classification.is_relevant and classification.eligible and is_open_verdict

            if predicted_positive and is_gt_positive:
                tp += 1
            elif predicted_positive and not is_gt_positive:
                fp += 1
            elif not predicted_positive and not is_gt_positive:
                tn += 1
            else:
                fn += 1

            # Work Mode Accuracy (evaluated on positive & open engineering roles)
            if gt["is_relevant"] and gt.get("is_open", True):
                work_mode_total += 1
                if classification.work_mode == gt["expected_work_mode"]:
                    work_mode_correct += 1

            # Country Resolution Accuracy
            country_total += 1
            if normalize_country(classification.country) == normalize_country(gt["expected_country"]):
                country_correct += 1

            # Quote Validity Rate
            if classification.is_relevant:
                relevant_predicted_count += 1
                if is_valid_evidence_quote(classification.evidence_quote, description):
                    valid_quotes += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    work_mode_acc = work_mode_correct / work_mode_total if work_mode_total > 0 else 1.0
    country_acc = country_correct / country_total if country_total > 0 else 1.0
    closed_detection_rate = closed_detected / closed_total if closed_total > 0 else 1.0
    quote_validity_rate = valid_quotes / relevant_predicted_count if relevant_predicted_count > 0 else 1.0

    precision_passed = precision >= 0.85
    quote_passed = quote_validity_rate >= 0.999

    print("\nBENCHMARK EVALUATION RESULTS:")
    print("-" * 55)
    print(f"  * Total Samples Evaluated    : {len(golden_jobs)}")
    print(f"  * Confusion Matrix           : TP={tp}, FP={fp}, TN={tn}, FN={fn}")
    print(f"  * Precision                  : {precision:.2%} (Target >= 85.00%) -> {'PASS' if precision_passed else 'FAIL'}")
    print(f"  * Recall                     : {recall:.2%}")
    print(f"  * F1 Score                   : {f1:.2%}")
    print(f"  * Work Mode Accuracy         : {work_mode_acc:.2%}")
    print(f"  * Country Resolution Acc     : {country_acc:.2%}")
    print(f"  * Multilingual Closed Detect : {closed_detection_rate:.2%} ({closed_detected}/{closed_total})")
    print(f"  * Quote-Validity Rate        : {quote_validity_rate:.2%} (Target = 100%) -> {'PASS' if quote_passed else 'FAIL'}")
    print("-" * 55)

    results = {
        "total_samples": len(golden_jobs),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "work_mode_accuracy": work_mode_acc,
        "country_accuracy": country_acc,
        "closed_detection_rate": closed_detection_rate,
        "quote_validity_rate": quote_validity_rate,
        "passed": precision_passed and quote_passed,
    }

    if not results["passed"]:
        print("\n[WARNING] Benchmark targets not met!")
    else:
        print("\n[SUCCESS] All benchmark acceptance criteria satisfied!")

    return results


if __name__ == "__main__":
    res = run_evaluation_benchmark()
    if not res["passed"]:
        sys.exit(1)
    sys.exit(0)
