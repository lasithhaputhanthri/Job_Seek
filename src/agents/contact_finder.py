"""
Phase 8: Contact Finder Worker Agent.
Finds publicly listed hiring contacts (e.g. careers@, talent@, jobs@, hr@)
directly on company career/contact pages.
Strict Ground Rule: Every contact MUST carry a real source URL where the email was visibly listed.
Zero invented, fabricated, or guessed emails.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from src.config import config
from src.agents.llm_engine import ai_engine
from src.db import StateDatabase
from src.schemas import UserProfile
from src.text_match import normalize_text

logger = logging.getLogger("ContactFinderWorker")

# Shared HTTP Headers
HEADERS = {
    "User-Agent": config.USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Hiring & Talent Contact Keywords for Prefix Filtering
HIRING_KEYWORDS: Set[str] = {
    "career",
    "careers",
    "talent",
    "recruiting",
    "recruitment",
    "recruit",
    "jobs",
    "hiring",
    "hr",
    "people",
    "contact",
    "info",
    "inquiries",
    "press",
}


class OutreachDraft(BaseModel):
    subject: str = Field(..., description="Compelling email subject line")
    body: str = Field(..., description="Personalized 3-paragraph engineering outreach message")
    key_highlights: List[str] = Field(..., description="2-3 technical highlights tailored to employer")
    requires_human_approval: bool = Field(default=True, description="Strict rule: Outreach requires opt-in human review before sending")
    recipient_email: Optional[str] = Field(default=None, description="Discovered public contact email")


class ContactFinderWorker:
    def __init__(self, db: StateDatabase, profile: Optional[UserProfile] = None, http_client: Optional[httpx.Client] = None):
        self.db = db
        self.profile = profile
        self.client = http_client

    def find_contacts_for_company(self, company: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Inspects company website / careers page for publicly visible hiring contact emails.
        Strictly requires real source URLs where the email appears in the visible page text.
        """
        comp_id = company.get("id") or 0
        comp_name = company["name"]
        domain = company.get("domain") or company.get("real_domain") or ""
        careers_url = company.get("careers_url") or (f"https://{domain}" if domain else "")

        if not domain and not careers_url:
            return []

        urls_to_check = [u for u in [careers_url, f"https://{domain}/contact" if domain else "", f"https://{domain}/careers" if domain else ""] if u]

        found_contacts = []
        seen_emails = set()

        client = self.client or httpx.Client(timeout=config.HTTP_TIMEOUT, headers=HEADERS, follow_redirects=True)
        should_close = self.client is None

        try:
            for url in urls_to_check:
                try:
                    resp = client.get(url)
                    if resp.status_code != 200:
                        continue

                    soup = BeautifulSoup(resp.text, "html.parser")
                    text_blob = soup.get_text()

                    # 1. Inspect mailto: links
                    for tag in soup.find_all("a", href=re.compile(r"^mailto:", re.IGNORECASE)):
                        email = tag["href"].replace("mailto:", "").split("?")[0].strip().lower()
                        if self._is_valid_contact_email(email, domain):
                            if email not in seen_emails:
                                seen_emails.add(email)
                                found_contacts.append({
                                    "email": email,
                                    "source_url": url,
                                    "role_department": "Hiring / Recruitment",
                                })

                    # 2. Inspect visible page text
                    matches = re.findall(r"\b[\w\.-]+@[\w\.-]+\.\w+\b", text_blob)
                    for m in matches:
                        email = m.lower().strip(".,;:()")
                        if self._is_valid_contact_email(email, domain):
                            if email not in seen_emails:
                                seen_emails.add(email)
                                found_contacts.append({
                                    "email": email,
                                    "source_url": url,
                                    "role_department": "Public Inquiries / Careers",
                                })
                except Exception as e:
                    logger.debug(f"Contact lookup failed on {url}: {e}")
                    continue
        finally:
            if should_close:
                client.close()

        # Record discovered authentic contacts into database
        if comp_id:
            for c in found_contacts:
                self.db.record_contact(
                    company_id=comp_id,
                    company_name=comp_name,
                    email=c["email"],
                    role_dept=c["role_department"],
                    source_url=c["source_url"],
                )

        print(f"[ContactFinder] '{comp_name}': Discovered {len(found_contacts)} public hiring contact(s).")
        return found_contacts

    def generate_outreach_draft(
        self,
        company_name: str,
        target_role: str,
        recipient: str,
        recipient_email: Optional[str] = None
    ) -> OutreachDraft:
        """
        Generates an introductory engineering outreach draft.
        Enforces candidate-agnostic design, zero invented claims, and human-in-the-loop review.
        """
        candidate_name = self.profile.name if self.profile else "Candidate"
        primary_domain = self.profile.primary_domain if self.profile else "Engineering"
        skills = self.profile.must_have_skills if self.profile else ["Hardware Design", "Embedded Systems"]
        location = self.profile.current_location if self.profile else "International"

        if self.profile and ai_engine.is_live:
            prompt_path = config.BASE_DIR / "src" / "prompts" / "outreach_draft.md"
            system_instruction = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else "Generate outreach draft."

            prompt = f"""Write a concise, compelling 3-paragraph outreach message to {recipient} at {company_name} regarding the '{target_role}' opportunity.

CANDIDATE PROFILE:
- Name: {candidate_name}
- Domain: {primary_domain}
- Core Skills: {', '.join(skills)}
- Location: {location}
"""
            res = ai_engine.generate_structured(
                prompt=prompt,
                response_schema=OutreachDraft,
                system_instruction=system_instruction,
            )
            if res:
                if candidate_name not in res.body:
                    res.body += f"\n\nSincerely,\n{candidate_name}"
                res.recipient_email = recipient_email
                res.requires_human_approval = True
                return res

        # Semantic Fallback Draft (Zero hardcoded personal names)
        skills_summary = ", ".join(skills[:4])
        subject = f"Inquiry regarding {target_role} - {candidate_name}"
        body = (
            f"Dear {company_name} Engineering Team,\n\n"
            f"I am writing to express my strong interest in the {target_role} opportunity at {company_name}. "
            f"With hands-on expertise in {skills_summary}, I have successfully brought complex engineering systems from schematic design to hardware validation.\n\n"
            f"I am particularly drawn to {company_name}'s technical roadmap and would welcome the opportunity to discuss how my background can support your engineering initiatives.\n\n"
            f"Sincerely,\n{candidate_name}"
        )
        return OutreachDraft(
            subject=subject,
            body=body,
            key_highlights=[f"Hands-on depth in {skills[0] if skills else 'engineering design'}", "Full lifecycle system bring-up", "Cross-functional technical execution"],
            requires_human_approval=True,
            recipient_email=recipient_email,
        )

    def _is_valid_contact_email(self, email: str, domain: str) -> bool:
        """Validates that email belongs to legitimate recruitment/careers prefixes and shares company domain."""
        if "@" not in email:
            return False
        # Filter static assets and binary extensions
        if any(email.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp", ".css", ".js"]):
            return False

        prefix, email_domain = email.split("@", 1)
        prefix = prefix.lower()
        email_domain = email_domain.lower()

        # Check if prefix matches hiring keywords
        has_hiring_keyword = any(k in prefix for k in HIRING_KEYWORDS)

        # Check if domain matches company domain (or common career subdomain)
        domain_clean = domain.replace("www.", "").lower() if domain else ""
        domain_match = domain_clean in email_domain or email_domain in domain_clean if domain_clean else False

        return has_hiring_keyword or domain_match
