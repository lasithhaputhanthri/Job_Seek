"""
Phase 3 & Europe Scale: Custom MCP Server - career_page_reader (MCP 2.x)
Supports:
1. Workday CXS REST APIs (NXP, Analog Devices, Thales, etc.) - Essential for Europe!
2. Greenhouse Boards API (Anduril, SpaceX, Astranis, Graphcore, Formlabs)
3. Lever Postings API (Palantir)
4. SmartRecruiters API
5. Generic HTML Fallback with injection defense
"""

import html
import json
import re
import sys
from typing import Any, Dict, List
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("career_page_reader")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
}


def _extract_token_from_url(url: str, pattern: str) -> str:
    match = re.search(pattern, url, re.IGNORECASE)
    return match.group(1).split("/")[0].split("?")[0] if match else ""


@mcp.tool()
def detect_ats(url: str) -> Dict[str, Any]:
    """
    Detects which Applicant Tracking System (ATS) manages a company's careers portal.
    Recognizes Workday, Greenhouse, Lever, Ashby, SmartRecruiters, Workable, or HTML.
    """
    url_lower = url.lower()

    # 1. Workday Detection (Standard for European Giants like NXP, Thales, Analog Devices)
    if "myworkdayjobs.com" in url_lower:
        parsed = urlparse(url)
        # e.g., nxp.wd3.myworkdayjobs.com/en-US/careers -> host: nxp.wd3.myworkdayjobs.com, company: nxp, portal: careers
        host = parsed.netloc
        company = host.split(".")[0]
        parts = [p for p in parsed.path.split("/") if p and p not in ["en-US", "en", "us"]]
        portal = parts[0] if parts else "careers"
        return {
            "ats": "workday",
            "host": host,
            "company": company,
            "portal": portal,
            "token": f"{host}/{company}/{portal}",
            "confidence": 1.0,
        }

    # 2. Greenhouse
    if "greenhouse.io" in url_lower:
        match = re.search(r'greenhouse\.io/(?:embed/job_board\?for=)?([^/?#]+)', url, re.IGNORECASE)
        token = match.group(1).split("/")[0].split("?")[0] if match else ""
        return {"ats": "greenhouse", "token": token, "source": "url_domain", "confidence": 1.0}

    # 3. Lever
    if "jobs.lever.co" in url_lower:
        token = _extract_token_from_url(url, r"jobs\.lever\.co/([^/?#]+)")
        return {"ats": "lever", "token": token, "source": "url_domain", "confidence": 1.0}

    # 4. Ashby
    if "ashbyhq.com" in url_lower:
        token = _extract_token_from_url(url, r"ashbyhq\.com/([^/?#]+)")
        return {"ats": "ashby", "token": token, "source": "url_domain", "confidence": 1.0}

    # 5. SmartRecruiters
    if "smartrecruiters.com" in url_lower:
        token = _extract_token_from_url(url, r"smartrecruiters\.com/([^/?#]+)")
        return {"ats": "smartrecruiters", "token": token, "source": "url_domain", "confidence": 1.0}

    # 6. BambooHR (Marked as needs_adapter instead of brittle JS-shell fallback)
    if "bamboohr.com" in url_lower:
        token = _extract_token_from_url(url, r"([^/?#]+)\.bamboohr\.com")
        return {"ats": "bamboohr", "token": token, "status": "needs_adapter", "source": "url_domain", "confidence": 1.0}

    # 7. Workable, Recruitee, Personio (Marked as needs_adapter)
    if "workable.com" in url_lower:
        token = _extract_token_from_url(url, r"apply\.workable\.com/([^/?#]+)")
        return {"ats": "workable", "token": token, "status": "needs_adapter", "source": "url_domain", "confidence": 1.0}

    if "recruitee.com" in url_lower:
        token = _extract_token_from_url(url, r"([^/?#]+)\.recruitee\.com")
        return {"ats": "recruitee", "token": token, "status": "needs_adapter", "source": "url_domain", "confidence": 1.0}

    if "personio.com" in url_lower or "personio.de" in url_lower:
        token = _extract_token_from_url(url, r"([^/?#]+)\.jobs\.personio\.(?:de|com)")
        return {"ats": "personio", "token": token, "status": "needs_adapter", "source": "url_domain", "confidence": 1.0}

    return {"ats": "html", "token": "", "source": "generic_fallback", "confidence": 0.5}


@mcp.tool()
def list_jobs(careers_url: str) -> List[Dict[str, Any]]:
    """
    Fetches open job postings from a careers URL or ATS board.
    Supports Workday REST API, Greenhouse API, Lever API, and HTML fallback.
    """
    detection = detect_ats(careers_url)
    ats = detection.get("ats")
    token = detection.get("token")
    results: List[Dict[str, Any]] = []

    # =========================================================================
    # 1. WORKDAY REST API (Powers European hardware giants NXP, Thales, ADI)
    # 0. Check if ATS requires dedicated adapter
    if detection.get("status") == "needs_adapter":
        return [{"status": "needs_adapter", "ats": ats, "error": f"ATS '{ats}' requires adapter", "source_url": careers_url}]

    # =========================================================================
    # 1. WORKDAY CXS REST API (Paginated & Taxonomy Search Terms)
    # =========================================================================
    if ats == "workday":
        host = detection["host"]
        company = detection["company"]
        portal = detection["portal"]
        api_url = f"https://{host}/wday/cxs/{company}/{portal}/jobs"
        base_job_url = f"https://{host}/en-US/{portal}"

        # Comprehensive engineering terms derived from search taxonomy
        search_terms = [
            "Hardware", "RF", "PCB", "Embedded", "FPGA", "Electrical",
            "Analog", "Antenna", "Firmware", "Verification", "Validation"
        ]
        seen_paths = set()

        try:
            with httpx.Client(timeout=15.0, headers=HEADERS) as client:
                for term in search_terms:
                    offset = 0
                    limit = 20
                    max_offset = 100  # Cap per term to prevent endless pagination

                    while offset <= max_offset:
                        payload = {"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": term}
                        resp = client.post(api_url, json=payload)
                        if resp.status_code != 200:
                            break

                        body = resp.json()
                        postings = body.get("jobPostings", [])
                        total = body.get("total", 0)

                        if not postings:
                            break

                        for j in postings:
                            ext_path = j.get("externalPath", "")
                            if ext_path and ext_path not in seen_paths:
                                seen_paths.add(ext_path)
                                results.append({
                                    "title": j.get("title", "Untitled"),
                                    "job_url": f"{base_job_url}{ext_path}",
                                    "external_path": ext_path,
                                    "location": j.get("locationsText", "Europe / International"),
                                    "department": "Engineering / Hardware",
                                    "ats": "workday",
                                    "source_url": careers_url,
                                })

                        offset += limit
                        if offset >= total:
                            break

            return results
        except Exception as e:
            print(f"[Workday API Error] {e}")

    # =========================================================================
    # 2. GREENHOUSE JSON API
    # =========================================================================
    if ats == "greenhouse" and token:
        api_url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
        try:
            with httpx.Client(timeout=12.0, headers=HEADERS) as client:
                resp = client.get(api_url)
                if resp.status_code == 200:
                    data = resp.json()
                    for j in data.get("jobs", []):
                        title_str = j.get("title", "Untitled")
                        loc = j.get("location", {}).get("name", "Unspecified")
                        dept = (j.get("departments") or [{}])[0].get("name", "Engineering")
                        loc_lower = loc.lower()
                        title_lower = title_str.lower()
                        wp_hint = "Remote" if ("remote" in loc_lower or "remote" in title_lower) else ("Hybrid" if ("hybrid" in loc_lower or "hybrid" in title_lower) else None)
                        
                        raw_content = j.get("content", "")
                        desc_text = ""
                        if raw_content:
                            soup = BeautifulSoup(html.unescape(raw_content), "html.parser")
                            desc_text = soup.get_text(separator="\n", strip=True)

                        results.append({
                            "title": title_str,
                            "job_url": j.get("absolute_url", careers_url),
                            "location": loc,
                            "department": dept,
                            "work_mode_hint": wp_hint,
                            "description_text": desc_text,
                            "ats": "greenhouse",
                            "source_url": careers_url,
                        })
                    return results
        except Exception:
            pass
        return results

    # =========================================================================
    # 3. LEVER JSON API
    # =========================================================================
    if ats == "lever" and token:
        api_url = f"https://api.lever.co/v0/postings/{token}?mode=json"
        try:
            with httpx.Client(timeout=12.0, headers=HEADERS) as client:
                resp = client.get(api_url)
                if resp.status_code == 200:
                    postings = resp.json()
                    if isinstance(postings, list):
                        for j in postings:
                            cats = j.get("categories", {})
                            raw_wp = str(cats.get("workplaceType") or j.get("workplaceType") or "").lower()
                            wp_hint = None
                            if "remote" in raw_wp:
                                wp_hint = "Remote"
                            elif "hybrid" in raw_wp:
                                wp_hint = "Hybrid"
                            elif "on-site" in raw_wp or "onsite" in raw_wp:
                                wp_hint = "On-site"

                            p_desc = j.get("descriptionPlain") or j.get("description") or ""
                            p_addl = j.get("additionalPlain") or j.get("additional") or ""
                            desc_text = f"{p_desc}\n\n{p_addl}".strip()

                            results.append({
                                "title": j.get("text", "Untitled"),
                                "job_url": j.get("hostedUrl", careers_url),
                                "location": cats.get("location", "Unspecified"),
                                "department": cats.get("department", "Engineering"),
                                "work_mode_hint": wp_hint,
                                "description_text": desc_text,
                                "ats": "lever",
                                "source_url": careers_url,
                            })
                        return results
        except Exception:
            pass
        return results

    # =========================================================================
    # 4. ASHBY JSON API (The Exploration Company, QuantWare, Alta Ares, etc.)
    # =========================================================================
    if ats == "ashby" and token:
        api_url = f"https://api.ashbyhq.com/posting-api/job-board/{token}"
        try:
            with httpx.Client(timeout=12.0, headers=HEADERS) as client:
                resp = client.get(api_url)
                if resp.status_code == 200:
                    for j in resp.json().get("jobs", []):
                        raw_wp = str(j.get("workplaceType") or "").lower()
                        is_remote = bool(j.get("isRemote", False))
                        wp_hint = None
                        if is_remote or "remote" in raw_wp:
                            wp_hint = "Remote"
                        elif "hybrid" in raw_wp:
                            wp_hint = "Hybrid"
                        elif "onsite" in raw_wp or "inperson" in raw_wp:
                            wp_hint = "On-site"

                        desc_plain = j.get("descriptionPlain", "")
                        if not desc_plain and j.get("descriptionHtml"):
                            s = BeautifulSoup(j["descriptionHtml"], "html.parser")
                            desc_plain = s.get_text(separator="\n", strip=True)

                        results.append({
                            "title": j.get("title", "Untitled"),
                            "job_url": j.get("jobUrl", careers_url),
                            "location": j.get("location", "Unspecified"),
                            "department": j.get("department", "Engineering"),
                            "work_mode_hint": wp_hint,
                            "description_text": desc_plain,
                            "ats": "ashby",
                            "source_url": careers_url,
                        })
                    return results
        except Exception:
            pass
        return results

    # =========================================================================
    # 5. SMARTRECRUITERS JSON API
    # =========================================================================
    if ats == "smartrecruiters" and token:
        api_url = f"https://api.smartrecruiters.com/v1/companies/{token}/postings?limit=100"
        try:
            with httpx.Client(timeout=12.0, headers=HEADERS) as client:
                resp = client.get(api_url)
                if resp.status_code == 200:
                    for j in resp.json().get("content", []):
                        loc = j.get("location") or {}
                        city = loc.get("city", "")
                        c_code = loc.get("country", "")
                        loc_str = f"{city}, {c_code}".strip(", ") or "Unspecified"
                        job_id = j.get("id", "")
                        job_link = f"https://jobs.smartrecruiters.com/{token}/{job_id}" if job_id else careers_url

                        results.append({
                            "title": j.get("name", "Untitled"),
                            "job_url": job_link,
                            "location": loc_str,
                            "department": (j.get("department") or {}).get("label", "Engineering"),
                            "ats": "smartrecruiters",
                            "source_url": careers_url,
                        })
                    return results
        except Exception:
            pass
        return results

    # =========================================================================
    # 6. FALLBACK HTML PARSER
    # =========================================================================
    try:
        with httpx.Client(timeout=15.0, headers=HEADERS, follow_redirects=True) as client:
            resp = client.get(careers_url)
            soup = BeautifulSoup(resp.text, "html.parser")
            base_domain = f"{urlparse(careers_url).scheme}://{urlparse(careers_url).netloc}"

            links = soup.find_all("a", href=True)
            seen_urls = set()
            for a in links:
                href = a["href"].strip()
                text = a.get_text(strip=True)
                if not text or len(text) < 4 or len(text) > 80:
                    continue
                if re.search(r"/(?:job|careers|position|opening|vacancy)/", href, re.IGNORECASE):
                    full_job_url = href if href.startswith("http") else f"{base_domain.rstrip('/')}/{href.lstrip('/')}"
                    if full_job_url not in seen_urls:
                        seen_urls.add(full_job_url)
                        results.append({
                            "title": text,
                            "job_url": full_job_url,
                            "location": "See posting",
                            "department": "Engineering",
                            "ats": "html",
                            "source_url": careers_url,
                        })
    except Exception as e:
        results.append({"error": f"HTML fallback failed: {str(e)}", "source_url": careers_url})

    return results


@mcp.tool()
def get_job_details(job_url: str) -> Dict[str, Any]:
    """
    Fetches full job posting text with prompt-injection defense framing.
    """
    try:
        # Check if Workday job URL to call Workday detail REST API
        if "myworkdayjobs.com" in job_url and "/job/" in job_url:
            parsed = urlparse(job_url)
            host = parsed.netloc
            company = host.split(".")[0]
            job_idx = parsed.path.find("/job/")
            if job_idx != -1:
                prefix = parsed.path[:job_idx].strip("/")
                ext_path = parsed.path[job_idx:]
                prefix_parts = [p for p in prefix.split("/") if p and p not in ["en-US", "en", "us"]]
                portal = prefix_parts[-1] if prefix_parts else "careers"
                detail_api = f"https://{host}/wday/cxs/{company}/{portal}{ext_path}"
                try:
                    with httpx.Client(timeout=10.0, headers=HEADERS) as client:
                        resp = client.get(detail_api)
                        if resp.status_code == 200:
                            data = resp.json().get("jobPostingInfo", {})
                            title = data.get("title", "")
                            remote_type = data.get("remoteType", "")
                            add_locs = ", ".join(data.get("additionalLocations", []))
                            header_info = f"Workplace Arrangement: {remote_type}\nLocation: {data.get('location', '')} {add_locs}\n" if remote_type or add_locs else ""
                            desc_html = data.get("jobDescription", "")
                            soup = BeautifulSoup(desc_html, "html.parser")
                            clean_text = (header_info + soup.get_text(separator="\n", strip=True))[:8000]
                            bounded = f"<UNTRUSTED_JOB_DATA url=\"{job_url}\">\n{title}\n\n{clean_text}\n</UNTRUSTED_JOB_DATA>"
                            return {"job_url": job_url, "status": "success", "character_count": len(clean_text), "clean_text": clean_text, "safe_content": bounded}
                except Exception:
                    pass

        # Check if Greenhouse job URL
        gh_id_match = re.search(r'(?:gh_jid=|/jobs/)(\d+)', job_url)
        gh_board_match = re.search(r'greenhouse\.io/(?:embed/job_board\?for=)?([^/?#]+)', job_url)
        if gh_id_match:
            job_id = gh_id_match.group(1)
            board_token = gh_board_match.group(1) if gh_board_match else ""
            if not board_token:
                parsed_host = urlparse(job_url).netloc
                board_token = parsed_host.split(".")[0] if "www." not in parsed_host else parsed_host.split(".")[1]
            if board_token:
                try:
                    gh_api = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}"
                    with httpx.Client(timeout=10.0, headers=HEADERS) as client:
                        resp = client.get(gh_api)
                        if resp.status_code == 200:
                            data = resp.json()
                            title = data.get("title", "")
                            location = (data.get("location") or {}).get("name", "")
                            desc_html = html.unescape(data.get("content", ""))
                            soup = BeautifulSoup(desc_html, "html.parser")
                            clean_text = soup.get_text(separator="\n", strip=True)[:8000]
                            bounded = f"<UNTRUSTED_JOB_DATA url=\"{job_url}\">\n{title}\nLocation: {location}\n\n{clean_text}\n</UNTRUSTED_JOB_DATA>"
                            return {"job_url": job_url, "status": "success", "character_count": len(clean_text), "clean_text": clean_text, "safe_content": bounded}
                except Exception:
                    pass

        # Check if Ashby job URL: https://jobs.ashbyhq.com/{company_slug}/{job_id}
        if "jobs.ashbyhq.com" in job_url:
            ashby_match = re.search(r"jobs\.ashbyhq\.com/([^/?#]+)(?:/([a-f0-9\-]+))?", job_url)
            if ashby_match:
                company_token = ashby_match.group(1)
                target_job_id = ashby_match.group(2)
                try:
                    ashby_api = f"https://api.ashbyhq.com/posting-api/job-board/{company_token}"
                    with httpx.Client(timeout=10.0, headers=HEADERS) as client:
                        resp = client.get(ashby_api)
                        if resp.status_code == 200:
                            jobs = resp.json().get("jobs", [])
                            matched_job = None
                            for j in jobs:
                                if target_job_id and target_job_id in j.get("jobUrl", ""):
                                    matched_job = j
                                    break
                                elif j.get("jobUrl", "") == job_url:
                                    matched_job = j
                                    break
                            if matched_job:
                                title = matched_job.get("title", "")
                                loc = matched_job.get("location", "")
                                desc_text = matched_job.get("descriptionPlain") or ""
                                if not desc_text and matched_job.get("descriptionHtml"):
                                    s = BeautifulSoup(matched_job["descriptionHtml"], "html.parser")
                                    desc_text = s.get_text(separator="\n", strip=True)
                                clean_text = desc_text[:8000]
                                bounded = f"<UNTRUSTED_JOB_DATA url=\"{job_url}\">\n{title}\nLocation: {loc}\n\n{clean_text}\n</UNTRUSTED_JOB_DATA>"
                                return {"job_url": job_url, "status": "success", "character_count": len(clean_text), "clean_text": clean_text, "safe_content": bounded}
                except Exception:
                    pass

        # Standard web page fetch
        with httpx.Client(timeout=12.0, headers=HEADERS, follow_redirects=True) as client:
            resp = client.get(job_url)
            if resp.status_code != 200:
                return {"job_url": job_url, "error": f"HTTP {resp.status_code}"}

            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                tag.decompose()

            raw_text = soup.get_text(separator="\n", strip=True)
            clean_text = re.sub(r"\n{2,}", "\n\n", raw_text)[:8000]

            # Detect JS Shell with negligible text
            if len(clean_text) < 150 or "enable javascript" in clean_text.lower():
                return {"job_url": job_url, "status": "error", "error": "JS client-rendered shell (no static description text)"}

            bounded = f"<UNTRUSTED_JOB_DATA url=\"{job_url}\">\n{clean_text}\n</UNTRUSTED_JOB_DATA>"
            return {"job_url": job_url, "status": "success", "character_count": len(clean_text), "clean_text": clean_text, "safe_content": bounded}
    except Exception as e:
        return {"job_url": job_url, "status": "error", "error": str(e)}


if __name__ == "__main__":
    print("Starting career_page_reader MCP Server...", file=sys.stderr)
    mcp.run()
