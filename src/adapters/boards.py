"""
Public Job Board Adapters (Arbeitnow, Remotive, Jobicy, RemoteOK).
Queries official public feeds using honest User-Agent headers, respects rate limits,
and returns normalized JobRecord objects.
Zero scraping of forbidden platforms.
"""

import logging
from typing import List, Optional
import httpx
from bs4 import BeautifulSoup

from src.adapters.base import JobRecord, JobSource
from src.config import config

logger = logging.getLogger("JobBoardAdapters")


class ArbeitnowSource(JobSource):
    """European Tech Job Board API (Germany, Netherlands, UK, EU-wide)."""

    def __init__(self, client: Optional[httpx.Client] = None):
        super().__init__("Arbeitnow")
        self.client = client

    def list_jobs(self, limit: int = 100) -> List[JobRecord]:
        records = []
        max_pages = min((limit // 30) + 1, 4)
        client = self.client or httpx.Client(headers=self.headers, timeout=config.HTTP_TIMEOUT)
        should_close = self.client is None

        try:
            for page in range(1, max_pages + 1):
                if len(records) >= limit:
                    break
                url = f"https://www.arbeitnow.com/api/job-board-api?page={page}"
                try:
                    resp = client.get(url)
                    if resp.status_code != 200:
                        break
                    data = resp.json().get("data", [])
                    if not data:
                        break
                    for item in data:
                        job_url = item.get("url", "")
                        if not job_url:
                            continue
                        desc_html = item.get("description", "")
                        clean_desc = BeautifulSoup(desc_html, "html.parser").get_text(separator="\n", strip=True) if desc_html else ""
                        records.append(JobRecord(
                            title=item.get("title", "Untitled"),
                            company_name=item.get("company_name", "Unknown Employer"),
                            location=item.get("location", "Europe"),
                            job_url=job_url,
                            source_url="https://www.arbeitnow.com",
                            description=clean_desc,
                            work_mode_hint="Remote" if item.get("remote") is True else None,
                        ))
                        if len(records) >= limit:
                            break
                except Exception as e:
                    logger.warning(f"[Arbeitnow] Harvest error on page {page}: {e}")
                    break
        finally:
            if should_close:
                client.close()

        return records


class RemotiveSource(JobSource):
    """Remotive Remote Jobs API."""

    def __init__(self, client: Optional[httpx.Client] = None):
        super().__init__("Remotive")
        self.client = client

    def list_jobs(self, limit: int = 100) -> List[JobRecord]:
        records = []
        url = f"https://remotive.com/api/remote-jobs?limit={limit}"
        client = self.client or httpx.Client(headers=self.headers, timeout=config.HTTP_TIMEOUT)
        should_close = self.client is None

        try:
            resp = client.get(url)
            if resp.status_code == 200:
                jobs = resp.json().get("jobs", [])
                for item in jobs[:limit]:
                    job_url = item.get("url", "")
                    if not job_url:
                        continue
                    desc_html = item.get("description", "")
                    clean_desc = BeautifulSoup(desc_html, "html.parser").get_text(separator="\n", strip=True) if desc_html else ""
                    records.append(JobRecord(
                        title=item.get("title", "Untitled"),
                        company_name=item.get("company_name", "Unknown Employer"),
                        location=item.get("candidate_required_location") or "Remote Worldwide",
                        job_url=job_url,
                        source_url="https://remotive.com",
                        description=clean_desc,
                        work_mode_hint="Remote",
                    ))
        except Exception as e:
            logger.warning(f"[Remotive] Harvest error: {e}")
        finally:
            if should_close:
                client.close()

        return records


class JobicySource(JobSource):
    """Jobicy Remote Engineering API."""

    def __init__(self, client: Optional[httpx.Client] = None):
        super().__init__("Jobicy")
        self.client = client

    def list_jobs(self, limit: int = 100) -> List[JobRecord]:
        records = []
        url = f"https://jobicy.com/api/v2/remote-jobs?count={limit}&tag=engineering"
        client = self.client or httpx.Client(headers=self.headers, timeout=config.HTTP_TIMEOUT)
        should_close = self.client is None

        try:
            resp = client.get(url)
            if resp.status_code == 200:
                jobs = resp.json().get("jobs", [])
                for item in jobs[:limit]:
                    job_url = item.get("url", "")
                    if not job_url:
                        continue
                    desc_html = item.get("jobDescription", "")
                    clean_desc = BeautifulSoup(desc_html, "html.parser").get_text(separator="\n", strip=True) if desc_html else ""
                    records.append(JobRecord(
                        title=item.get("jobTitle", "Untitled"),
                        company_name=item.get("companyName", "Unknown Employer"),
                        location=item.get("jobGeo") or "Remote / Global",
                        job_url=job_url,
                        source_url="https://jobicy.com",
                        description=clean_desc,
                        work_mode_hint="Remote",
                    ))
        except Exception as e:
            logger.warning(f"[Jobicy] Harvest error: {e}")
        finally:
            if should_close:
                client.close()

        return records


class RemoteOKSource(JobSource):
    """RemoteOK Public Feed API."""

    def __init__(self, client: Optional[httpx.Client] = None):
        super().__init__("RemoteOK")
        self.client = client

    def list_jobs(self, limit: int = 100) -> List[JobRecord]:
        records = []
        url = "https://remoteok.com/api"
        client = self.client or httpx.Client(headers=self.headers, timeout=config.HTTP_TIMEOUT)
        should_close = self.client is None

        try:
            resp = client.get(url)
            if resp.status_code == 200:
                items = resp.json()
                for item in items:
                    if not isinstance(item, dict) or "legal" in item:
                        continue
                    job_url = item.get("url", "")
                    if not job_url:
                        continue
                    desc_html = item.get("description", "")
                    clean_desc = BeautifulSoup(desc_html, "html.parser").get_text(separator="\n", strip=True) if desc_html else ""
                    records.append(JobRecord(
                        title=item.get("position", "Untitled"),
                        company_name=item.get("company", "Unknown Employer"),
                        location=item.get("location") or "Remote / Global",
                        job_url=job_url if job_url.startswith("http") else f"https://remoteok.com{job_url}",
                        source_url="https://remoteok.com",
                        description=clean_desc,
                        work_mode_hint="Remote",
                    ))
                    if len(records) >= limit:
                        break
        except Exception as e:
            logger.warning(f"[RemoteOK] Harvest error: {e}")
        finally:
            if should_close:
                client.close()

        return records
