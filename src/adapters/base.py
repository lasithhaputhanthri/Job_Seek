"""
Base Job Source Interface for Public Job Boards & Aggregators.
Standardizes harvesting with honest User-Agent headers, rate limiting, and schema normalization.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.config import config


class JobRecord(BaseModel):
    """Normalized job posting returned by all harvest sources."""
    title: str
    company_name: str
    location: str
    job_url: str
    source_url: str
    description: str = ""
    work_mode_hint: Optional[str] = None
    company_domain: Optional[str] = None
    posted_date: Optional[str] = None


class JobSource(ABC):
    """Abstract interface implemented by all job board adapters."""

    def __init__(self, name: str, user_agent: Optional[str] = None):
        self.name = name
        self.user_agent = user_agent or config.USER_AGENT
        self.headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
        }

    @abstractmethod
    def list_jobs(self, limit: int = 100) -> List[JobRecord]:
        """Fetches raw jobs and returns normalized JobRecord instances."""
        pass
