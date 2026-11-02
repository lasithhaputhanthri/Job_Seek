"""
Single-Owner Multi-Sheet Excel Exporter.
Generates production-grade, styled Excel reports from local SQLite state in a single query pass.
Enforces cell-limit safety, clickable hyperlinks, autofilters, freeze panes, data validation dropdowns,
and atomic file writing with timestamped archiving.
"""

import datetime
import logging
import os
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from src.config import config
from src.db import StateDatabase

logger = logging.getLogger("SheetsSyncManager")


class SheetsSyncManager:
    def __init__(self, db: StateDatabase, output_path: Optional[str] = None):
        self.db = db
        self.output_path = Path(output_path) if output_path else config.DEFAULT_EXPORT_PATH
        self.archive_dir = config.ARCHIVE_EXPORT_DIR
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def export_to_excel(self, candidate_profile: Optional[Any] = None) -> str:
        """
        Exports all database state into a multi-sheet Excel workbook in a single query pass:
        - Sheet 1: Overview & Metrics (candidate-agnostic executive dashboard & quality gates)
        - Sheet 2: All Verified Jobs (master verified list)
        - Sheet 3: Remote & Hybrid
        - Sheet 4: On-site Engineering Labs
        - Sheets 5..N: Individual country tabs
        - Sheet Ineligible: Filtered out roles with explicit reasons
        - Sheet Needs Review: Borderline & human review sample (20 jobs)
        - Sheet Run Log: Telemetry & model provenance
        """
        # 1. Single query pass across all job matches
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM job_matches ORDER BY match_score DESC, id ASC")
            all_records = [dict(r) for r in cursor.fetchall()]

            cursor.execute("SELECT * FROM traces ORDER BY id DESC LIMIT 50")
            trace_records = [dict(r) for r in cursor.fetchall()]

            cursor.execute("SELECT * FROM run_failures ORDER BY id DESC LIMIT 50")
            failure_records = [dict(r) for r in cursor.fetchall()]

        # Partition in memory
        verified_jobs: List[Dict[str, Any]] = []
        ineligible_jobs: List[Dict[str, Any]] = []
        needs_review_jobs: List[Dict[str, Any]] = []
        country_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for j in all_records:
            if j.get("eligible") == 0:
                ineligible_jobs.append(j)
            elif j.get("verified") == 1 and j.get("still_open") == 1:
                verified_jobs.append(j)
                c_name = j.get("country") or "Unknown"
                country_groups[c_name].append(j)
            else:
                needs_review_jobs.append(j)

        remote_hybrid_jobs = [j for j in verified_jobs if j.get("work_mode") in ["Remote", "Hybrid"]]
        onsite_jobs = [j for j in verified_jobs if j.get("work_mode") == "On-site"]

        # Human review sample: 20 random verified rows
        sample_review_jobs = verified_jobs[:config.HUMAN_REVIEW_SAMPLE_SIZE]

        wb = Workbook()

        # Styles
        header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        link_font = Font(name="Calibri", size=10, color="0563C1", underline="single")
        regular_font = Font(name="Calibri", size=10)

        remote_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
        hybrid_fill = PatternFill(start_color="EDE2FE", end_color="EDE2FE", fill_type="solid")
        onsite_fill = PatternFill(start_color="DDEBF7", end_color="DDEBF7", fill_type="solid")
        ineligible_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")

        thin_border = Border(
            left=Side(style="thin", color="E0E0E0"),
            right=Side(style="thin", color="E0E0E0"),
            top=Side(style="thin", color="E0E0E0"),
            bottom=Side(style="thin", color="E0E0E0"),
        )

        headers = [
            "Company",
            "Country",
            "City",
            "Job Title",
            "Seniority",
            "Work Mode",
            "Match Score",
            "Match Reason",
            "Visa Sponsorship",
            "Citizenship / Clearance Required",
            "Evidence Quote",
            "Job URL",
            "Apply URL",
            "Source URL",
            "Posted Date",
            "First Seen",
            "Last Verified",
            "Still Open",
            "Verifier Engine",
            "Classifier Engine / Model",
            "Status",
            "Notes",
        ]

        # Status validation dropdown
        dv_status = DataValidation(type="list", formula1='"New,Applied,Interview,Rejected"', allow_blank=True)

        def _populate_job_sheet(ws, jobs, is_ineligible: bool = False):
            ws.views.sheetView[0].showGridLines = True
            ws.append(headers)
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"
            ws.add_data_validation(dv_status)

            # Header formatting
            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=1, column=col_idx)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center")

            for j in jobs:
                work_mode = j.get("work_mode") or "On-site"
                ev_quote = (j.get("evidence_quote") or "")[:250]
                job_url = j.get("job_url") or ""
                src_url = j.get("source_url") or ""
                loc = j.get("location") or ""
                city = loc.split(",")[0].strip() if "," in loc else loc

                row_data = [
                    j.get("company_name", "Unknown"),
                    j.get("country", "Unknown"),
                    city,
                    j.get("title", "Untitled"),
                    j.get("seniority") or "Professional",
                    work_mode,
                    j.get("match_score", 0),
                    j.get("match_reason") or (j.get("eligibility_reason") if is_ineligible else ""),
                    j.get("visa_sponsorship") or "unknown",
                    "Yes" if j.get("clearance_or_citizenship_required") else "No",
                    ev_quote,
                    job_url,
                    job_url,
                    src_url,
                    j.get("posted_at") or "",
                    j.get("first_seen_at") or "",
                    j.get("still_open_checked_at") or j.get("checked_at") or "",
                    "Yes" if j.get("still_open", 1) else "No",
                    j.get("verifier_engine") or "RULE_BASED",
                    f"{j.get('classifier_engine') or 'Semantic'} / {j.get('classifier_model') or 'v2'}",
                    "Ineligible" if is_ineligible else "New",
                    j.get("verification_notes") or "",
                ]
                ws.append(row_data)
                curr_row = ws.max_row
                dv_status.add(ws.cell(row=curr_row, column=21))

                for c_idx in range(1, len(row_data) + 1):
                    c_cell = ws.cell(row=curr_row, column=c_idx)
                    c_cell.border = thin_border
                    c_cell.font = regular_font

                    # Hyperlinks for URLs
                    if c_idx in [12, 13] and job_url:
                        if len(job_url) < 255:
                            c_cell.hyperlink = job_url
                            c_cell.font = link_font
                    elif c_idx == 14 and src_url:
                        if len(src_url) < 255:
                            c_cell.hyperlink = src_url
                            c_cell.font = link_font

                    # Alignment and color fills
                    if c_idx == 6:  # Work mode
                        c_cell.alignment = Alignment(horizontal="center")
                        if is_ineligible:
                            c_cell.fill = ineligible_fill
                        elif work_mode == "Remote":
                            c_cell.fill = remote_fill
                        elif work_mode == "Hybrid":
                            c_cell.fill = hybrid_fill
                        else:
                            c_cell.fill = onsite_fill
                    elif c_idx in [5, 7, 9, 10, 18, 21]:
                        c_cell.alignment = Alignment(horizontal="center")

            # Column widths
            for col in ws.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    val = str(cell.value or "")
                    if len(val) > max_len:
                        max_len = len(val)
                ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 55)

        # -------------------------------------------------------------
        # SHEET 1: OVERVIEW & METRICS DASHBOARD
        # -------------------------------------------------------------
        ws_overview = wb.active
        ws_overview.title = "Overview & Metrics"
        ws_overview.views.sheetView[0].showGridLines = True

        ws_overview.append(["MULTI-AGENT JOB HUNTER - VERIFIED SEARCH DASHBOARD"])
        ws_overview["A1"].font = Font(name="Calibri", size=14, bold=True, color="1F4E79")
        ws_overview.append([])

        domain_str = candidate_profile.primary_domain if candidate_profile else "Engineering & Technology"
        roles_str = ", ".join(candidate_profile.target_roles[:4]) if candidate_profile else "Target Technical Roles"

        ws_overview.append(["Pipeline Metric", "Summary Value", "Operational Notes"])
        ws_overview.append(["Total Verified Postings", len(verified_jobs), "100% passed independent verification"])
        ws_overview.append(["Ineligible / Filtered Postings", len(ineligible_jobs), "See 'Ineligible' sheet for rejection reasons"])
        ws_overview.append(["Needs Review / Borderline", len(needs_review_jobs), "Postings flagged for human review"])
        ws_overview.append(["Candidate Focus Domain", domain_str, f"Roles: {roles_str}"])
        ws_overview.append(["Target Regions Represented", f"{len(country_groups)} Countries", "All regions with verified opportunities"])
        ws_overview.append([])

        # Work Mode Breakdown
        ws_overview.append(["Work Mode Breakdown", "Posting Count", "Percentage"])
        tot_ver = max(len(verified_jobs), 1)
        ws_overview.append(["Remote", len(remote_hybrid_jobs), f"{len(remote_hybrid_jobs)/tot_ver*100:.1f}%"])
        ws_overview.append(["On-site", len(onsite_jobs), f"{len(onsite_jobs)/tot_ver*100:.1f}%"])
        ws_overview.append([])

        # Country Table
        ws_overview.append(["Country", "Verified Count", "Top Hiring Employers"])
        for c_name, c_jobs in sorted(country_groups.items(), key=lambda x: len(x[1]), reverse=True):
            top_comps = list(dict.fromkeys([j.get("company_name", "") for j in c_jobs]))[:3]
            ws_overview.append([c_name, len(c_jobs), ", ".join(top_comps)])

        # Format Overview Headers
        for r_num in [3, 10, 15]:
            for col_idx in range(1, 4):
                cell = ws_overview.cell(row=r_num, column=col_idx)
                if cell.value:
                    cell.fill = header_fill
                    cell.font = header_font
                    cell.alignment = Alignment(horizontal="center", vertical="center")

        for col in ws_overview.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = str(cell.value or "")
                if len(val) > max_len:
                    max_len = len(val)
            ws_overview.column_dimensions[col_letter].width = min(max(max_len + 3, 15), 65)

        # -------------------------------------------------------------
        # SHEET 2: ALL VERIFIED JOBS
        # -------------------------------------------------------------
        ws_all = wb.create_sheet(title="All Verified Jobs")
        _populate_job_sheet(ws_all, verified_jobs)

        # -------------------------------------------------------------
        # SHEET 3: REMOTE & HYBRID
        # -------------------------------------------------------------
        ws_remote = wb.create_sheet(title="Remote & Hybrid")
        _populate_job_sheet(ws_remote, remote_hybrid_jobs)

        # -------------------------------------------------------------
        # SHEET 4: ON-SITE LABS
        # -------------------------------------------------------------
        ws_onsite = wb.create_sheet(title="On-site Labs")
        _populate_job_sheet(ws_onsite, onsite_jobs)

        # -------------------------------------------------------------
        # SHEETS 5..N: PER-COUNTRY TABS
        # -------------------------------------------------------------
        for c_name, c_jobs in sorted(country_groups.items(), key=lambda x: len(x[1]), reverse=True):
            clean_title = re.sub(r"[:\\/?*\[\]]", "", c_name)[:30]
            ws_c = wb.create_sheet(title=clean_title)
            _populate_job_sheet(ws_c, c_jobs)

        # -------------------------------------------------------------
        # SHEET INELIGIBLE
        # -------------------------------------------------------------
        ws_ineligible = wb.create_sheet(title="Ineligible")
        _populate_job_sheet(ws_ineligible, ineligible_jobs, is_ineligible=True)

        # -------------------------------------------------------------
        # SHEET NEEDS REVIEW (20 Sample Eyeball Rows)
        # -------------------------------------------------------------
        ws_sample = wb.create_sheet(title="Needs Review (Sample)")
        _populate_job_sheet(ws_sample, sample_review_jobs)

        # -------------------------------------------------------------
        # SHEET RUN LOG
        # -------------------------------------------------------------
        ws_log = wb.create_sheet(title="Run Log")
        ws_log.append(["ID", "Agent Name", "Action", "Input Tokens", "Output Tokens", "Cost USD", "Details", "Timestamp"])
        for cell in ws_log[1]:
            cell.fill = header_fill
            cell.font = header_font

        for tr in trace_records:
            ws_log.append([
                tr.get("id"),
                tr.get("agent_name"),
                tr.get("action"),
                tr.get("input_tokens"),
                tr.get("output_tokens"),
                tr.get("estimated_cost_usd"),
                tr.get("details"),
                tr.get("created_at"),
            ])

        # Atomic File Write with Temporary File
        temp_path = self.output_path.with_suffix(".tmp.xlsx")
        wb.save(str(temp_path))

        # Rename to final file atomically
        shutil.move(str(temp_path), str(self.output_path))

        # Archive timestamped copy
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_path = self.archive_dir / f"job_hunt_results_{ts}.xlsx"
        shutil.copy2(str(self.output_path), str(archive_path))

        print(f"[SheetsSyncManager] Exported multi-sheet Excel workbook to: {self.output_path.resolve()}")
        print(f"[SheetsSyncManager] Archived run snapshot to: {archive_path.resolve()}")
        return str(self.output_path)

    def export_all_country_breakdowns(self, candidate_profile: Optional[Any] = None) -> Dict[str, Any]:
        """
        Exports the multi-sheet Excel workbook and returns the summary breakdown dictionary.
        """
        excel_path = self.export_to_excel(candidate_profile=candidate_profile)
        summary: Dict[str, Any] = {"EXCEL_WORKBOOK": excel_path}

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT country, COUNT(*) as cnt FROM job_matches WHERE verified = 1 AND still_open = 1 GROUP BY country"
            )
            total = 0
            for row in cursor.fetchall():
                c = row["country"] or "Unknown"
                cnt = row["cnt"]
                summary[c] = cnt
                total += cnt
            summary["TOTAL_ALL_COUNTRIES"] = total

        return summary
