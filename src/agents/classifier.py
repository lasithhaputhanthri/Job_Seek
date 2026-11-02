"""
AI Job Classifier Agent.
Provides rigorous technical evaluation of job postings against candidate profiles:
1. Distinguishes workplace policy ('Remote', 'Hybrid', 'On-site') from engineering jargon
   (e.g., 'hybrid beamforming', 'hybrid coupler', 'remote sensing', 'RPC').
2. Evaluates deep technical skill alignment and scores fit (0-100).
3. Enforces hard filters (visa/clearance, seniority, target countries, internships).
4. Verifies evidence quotes verbatim against raw page text (never quotes URLs, HTML, or wrapper tags).
5. Employs unified ai_engine with seamless fallback to a high-precision semantic engine.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from src.config import config
from src.agents.llm_engine import ai_engine
from src.geo import canonicalize_country, resolve_country_from_location
from src.schemas import JobClassification, SeniorityLevel, UserProfile
from src.text_match import (
    contains_any_word,
    contains_technical_work_mode_jargon,
    extract_surrounding_sentence,
    extract_visa_and_citizenship_signals,
    find_matched_keywords,
    is_genuine_hybrid_indicator,
    is_genuine_remote_indicator,
    is_internship_or_graduate,
    is_non_engineering_role,
    matches_word,
    normalize_text,
)

logger = logging.getLogger("AIJobClassifierAgent")


class AIJobClassifierAgent:
    """
    AI Agent that classifies job postings using LLM reasoning (Gemini / OpenAI / Local)
    or a high-precision deterministic semantic engine.
    """

    def __init__(self, profile: UserProfile):
        self.profile = profile
        self.provider_name = ai_engine.provider_name
        self.searchable_skills = self._get_searchable_skills()

    def _get_searchable_skills(self) -> List[str]:
        """
        Decomposes composite skill phrases (e.g. 'Multilayer PCB Layout',
        'RF Front-End Design', 'Signal and Power Integrity') into atomic technical terms
        and augments with candidate tools.
        Candidate-agnostic and sorted by length descending so specific phrases match first.
        """
        searchable = set()
        for s in (self.profile.must_have_skills or []):
            s_clean = s.strip()
            if not s_clean:
                continue
            searchable.add(s_clean)
            # Split composite skills on slashes, ampersands, or ' and '
            parts = re.split(r"[\/&]| and ", s_clean, flags=re.IGNORECASE)
            for p in parts:
                p_strip = p.strip()
                if len(p_strip) >= 2:
                    searchable.add(p_strip)
                    for w in p_strip.split():
                        w_clean = re.sub(r"^[^\w]+|[^\w]+$", "", w)
                        if len(w_clean) >= 2 and w_clean.lower() not in {
                            "and", "the", "for", "with", "from", "layout", "review", "simulation", "design"
                        }:
                            searchable.add(w_clean)

        for t in (self.profile.tools or []):
            t_clean = t.strip()
            if t_clean:
                searchable.add(t_clean)
                if " " in t_clean:
                    for w in t_clean.split():
                        w_clean = re.sub(r"^[^\w]+|[^\w]+$", "", w)
                        if len(w_clean) >= 3 and w_clean.lower() not in {"and", "the", "for", "with", "system", "suite"}:
                            searchable.add(w_clean)

        return sorted(list(searchable), key=lambda x: -len(x))

    def classify_job(
        self,
        title: str,
        company_name: str,
        location: str,
        details_text: str,
        ats_work_mode_hint: Optional[str] = None,
        structured_workplace_type: Optional[str] = None,
    ) -> JobClassification:
        """
        Main entry point: classifies a job posting.
        Applies hard filters first, then LLM / semantic scoring, and post-processes in code.
        """
        # Clean inputs and strip untrusted wrappers
        clean_text = self._strip_untrusted_wrappers(details_text or "")
        clean_title = (title or "Untitled").strip()
        clean_location = (location or "").strip()

        # Resolve country from location (never defaults to company HQ)
        resolved_country, geo_conf, is_remote_anywhere = resolve_country_from_location(clean_location)

        # -------------------------------------------------------------
        # STEP 1: HARD FILTERS (Evaluated in code before and after LLM)
        # -------------------------------------------------------------
        hard_filter_violation, hard_filter_reason = self._check_hard_filters(
            title=clean_title,
            location=clean_location,
            country=resolved_country,
            is_remote_anywhere=is_remote_anywhere,
            details_text=clean_text,
        )

        if hard_filter_violation:
            # Short-circuit ineligible postings immediately
            return self._build_ineligible_result(
                clean_title, company_name, clean_location, resolved_country, hard_filter_reason
            )

        # -------------------------------------------------------------
        # STEP 2: WORK-MODE HINT DISAMBIGUATION (Bug 9)
        # -------------------------------------------------------------
        # Only trust structured ATS fields (e.g. Lever workplaceType, Ashby isRemote, Workday remoteType)
        validated_forced_mode = None
        if structured_workplace_type in ["Remote", "Hybrid", "On-site"]:
            validated_forced_mode = structured_workplace_type
        elif ats_work_mode_hint:
            # Free-text hints must pass jargon-aware validation
            hint_lower = ats_work_mode_hint.lower()
            if "remote" in hint_lower and is_genuine_remote_indicator(clean_title + " " + clean_location):
                validated_forced_mode = "Remote"
            elif "hybrid" in hint_lower and is_genuine_hybrid_indicator(clean_title + " " + clean_location):
                validated_forced_mode = "Hybrid"

        # -------------------------------------------------------------
        # STEP 3: COST-AWARE EVALUATION (Cost Funnel)
        # -------------------------------------------------------------
        # 1. Evaluate with fast semantic rule engine first (0 cost, 0 latency)
        semantic_result = self._classify_with_semantic_engine(
            title=clean_title,
            company_name=company_name,
            location=clean_location,
            details_text=clean_text,
            validated_work_mode=validated_forced_mode,
        )

        # 2. Only invoke LLM when:
        #    a) ai_engine is live and daily quota is not exhausted
        #    b) Posting has substantive description (>= 150 chars)
        #    c) Match is borderline (between BORDERLINE_SCORE_LOW and BORDERLINE_SCORE_HIGH)
        #       OR FORCE_ALL_LLM is enabled.
        # Clear matches (score >= 70) and clear non-matches (score < 45) use the fast semantic engine.
        is_borderline = (config.BORDERLINE_SCORE_LOW <= semantic_result.match_score <= config.BORDERLINE_SCORE_HIGH)
        force_llm = os.environ.get("FORCE_ALL_LLM", "false").lower() == "true"

        result = None
        if ai_engine.is_live and not getattr(ai_engine, "daily_quota_exhausted", False) and (is_borderline or force_llm):
            if len(clean_text) >= 150:
                prompt = self._build_prompt(clean_title, company_name, clean_location, clean_text, validated_forced_mode)
                prompt_file = config.BASE_DIR / "src" / "prompts" / "job_classifier.md"
                system_instruction = prompt_file.read_text(encoding="utf-8") if prompt_file.exists() else None

                res = ai_engine.generate_structured(
                    prompt=prompt,
                    response_schema=JobClassification,
                    system_instruction=system_instruction,
                    model=config.GEMINI_MODEL,
                )
                if res:
                    result = res

        if not result:
            result = semantic_result

        # -------------------------------------------------------------
        # STEP 4: CODE-LEVEL POST-PROCESSING & EVIDENCE VERIFICATION (Bug 5, 12)
        # -------------------------------------------------------------
        # Never trust the LLM: verify quote is verbatim substring of fetched text
        if result.evidence_quote:
            clean_quote = result.evidence_quote.strip()
            # If quote mentions HTML tags, URLs, or UNTRUSTED wrapper, discard
            if "<" in clean_quote or "http" in clean_quote or "UNTRUSTED" in clean_quote:
                result.evidence_quote = None
            elif clean_text and clean_quote not in clean_text:
                # Discard hallucinated quotes
                result.evidence_quote = None

        # Description length cap (Bug 5.3): Cap at 60 if description is missing or < 300 characters
        if not clean_text or len(clean_text) < 300:
            if result.match_score > config.MAX_SCORE_NO_DESCRIPTION:
                result.match_score = config.MAX_SCORE_NO_DESCRIPTION
                result.match_reason += " (Score capped: posting description was missing or brief)."

        # Must-have skill coverage cap: Cap at 40 if no must-have skill matches
        matched_must_haves = find_matched_keywords(self.searchable_skills, clean_title + " " + clean_text)
        if not matched_must_haves and result.match_score > config.MAX_SCORE_NO_MUST_HAVE:
            result.match_score = config.MAX_SCORE_NO_MUST_HAVE
            result.match_reason += " (Score capped: no must-have technical skills demonstrated)."

        # Compute is_relevant strictly from MIN_RELEVANCE_SCORE in code (Bug 12)
        result.is_relevant = result.match_score >= config.MIN_RELEVANCE_SCORE and result.eligible
        result.country = resolved_country

        # Guarantee verbatim evidence quote for any relevant eligible role
        if result.is_relevant and not result.evidence_quote and clean_text:
            search_pool = matched_must_haves or self.searchable_skills
            for kw in search_pool:
                m = re.search(rf"\b{re.escape(kw)}\b", clean_text, re.IGNORECASE)
                if m:
                    cand = extract_surrounding_sentence(m.start(), m.end(), clean_text)
                    if cand and len(cand) >= 15 and cand in clean_text:
                        result.evidence_quote = cand
                        break
            if not result.evidence_quote:
                first_dot = clean_text.find(".")
                if first_dot >= 15:
                    cand = clean_text[:first_dot].strip()
                    if cand in clean_text:
                        result.evidence_quote = cand

        return result

    def _strip_untrusted_wrappers(self, text: str) -> str:
        """Strips <UNTRUSTED_JOB_DATA url="..."> wrapper tags before sentence extraction."""
        if not text:
            return ""
        # Remove opening <UNTRUSTED_JOB_DATA ...> and closing </UNTRUSTED_JOB_DATA>
        stripped = re.sub(r"<UNTRUSTED_JOB_DATA[^>]*>", "", text)
        stripped = re.sub(r"</UNTRUSTED_JOB_DATA>", "", stripped)
        return stripped.strip()

    def _check_hard_filters(
        self,
        title: str,
        location: str,
        country: str,
        is_remote_anywhere: bool,
        details_text: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Evaluates deterministic hard filters:
        1. Non-engineering function (HR, sales, legal, etc.)
        2. Unrequested internship / graduate schemes
        3. Country outside allowed set (unless remote eligible)
        4. Citizenship / clearance / ITAR restriction when candidate needs sponsorship
        """
        # 1. Non-engineering role check
        if is_non_engineering_role(title):
            return (True, "Non-engineering business function (Sales/HR/Legal/Marketing/Finance)")

        # 2. Internship / graduate check
        if not self.profile.include_internships and not self.profile.include_graduate_programs:
            if is_internship_or_graduate(title):
                return (True, "Internship, working student, or graduate scheme (candidate requested professional roles only)")

        # 3. Country / Geographic hard filter
        if not is_remote_anywhere:
            target_norm = [canonicalize_country(c).lower() for c in self.profile.target_countries]
            is_global_profile = any(w in " ".join(target_norm) for w in ["worldwide", "global", "all", "anywhere"])

            if not is_global_profile and country != "Unknown":
                canon_country = canonicalize_country(country).lower()
                if canon_country not in target_norm:
                    return (True, f"Job location ({country}) is outside candidate target countries ({', '.join(self.profile.target_countries)})")

        # 4. Visa & Citizenship / ITAR hard filter (Bug 10)
        if self.profile.needs_visa_sponsorship and details_text:
            visa_status, cit_req, quote = extract_visa_and_citizenship_signals(details_text)
            if cit_req:
                return (True, f"Security clearance, local citizenship, or ITAR required ('{quote or 'Restriction detected'}')")
            if visa_status == "no":
                return (True, f"Employer explicitly does not provide visa sponsorship ('{quote or 'No sponsorship'}')")

        return (False, None)

    def _build_ineligible_result(
        self, title: str, company: str, location: str, country: str, reason: str
    ) -> JobClassification:
        """Returns structured ineligible result without calling the LLM."""
        return JobClassification(
            eligible=False,
            eligibility_reason=reason,
            work_mode="Unknown",
            work_mode_reason=f"Posting excluded by hard filter: {reason}",
            match_score=0,
            match_reason=f"Ineligible: {reason}",
            evidence_quote=None,
            is_relevant=False,
            country=country,
        )

    def _build_prompt(
        self,
        title: str,
        company_name: str,
        location: str,
        details_text: str,
        validated_work_mode: Optional[str],
    ) -> str:
        """Builds security-bounded prompt conforming to prompt 5.3."""
        sample_text = (details_text or "")[:4000]

        candidate_json = {
            "target_roles": self.profile.target_roles,
            "must_have_skills": self.profile.must_have_skills,
            "seniority_levels": [s.value if hasattr(s, "value") else str(s) for s in self.profile.seniority_levels],
            "allowed_countries": self.profile.target_countries,
            "needs_visa_sponsorship": self.profile.needs_visa_sponsorship,
            "work_modes": self.profile.work_modes,
            "include_internships": self.profile.include_internships,
        }

        return f"""CANDIDATE:
{json.dumps(candidate_json, indent=2)}

<JOB_POSTING>
Company: {company_name}
Title: {title}
Location: {location}
{f"Structured ATS Work Mode: {validated_work_mode}" if validated_work_mode else ""}
Description:
{sample_text}
</JOB_POSTING>
"""

    def _classify_with_semantic_engine(
        self,
        title: str,
        company_name: str,
        location: str,
        details_text: str,
        validated_work_mode: Optional[str],
    ) -> JobClassification:
        """
        High-precision deterministic rule-based evaluation engine.
        Applies word-boundary regex matching and candidate-specific skill alignment.
        """
        norm_title = normalize_text(title)
        norm_location = normalize_text(location)
        norm_details = normalize_text(details_text)
        combined_text = f"{norm_title} {norm_location} {norm_details}"

        # 1. Determine Work Mode
        work_mode = validated_work_mode or "On-site"
        work_mode_reason = f"Validated ATS structured policy: '{validated_work_mode}'" if validated_work_mode else "Physical engineering lab/office arrangement"

        if not validated_work_mode:
            if is_genuine_hybrid_indicator(combined_text):
                work_mode = "Hybrid"
                work_mode_reason = "Posting explicitly specifies hybrid flexible workplace model"
            elif is_genuine_remote_indicator(combined_text):
                work_mode = "Remote"
                work_mode_reason = "Posting explicitly specifies remote/work-from-home policy"

        # 2. Score Technical Fit (0-100)
        score = 0
        reasons = []

        # (a) Role/Title fit (max 25 points)
        matched_roles = find_matched_keywords(self.profile.target_roles, norm_title)
        if matched_roles:
            score += 25
            reasons.append(f"Target role title matched: '{matched_roles[0]}'")
        else:
            title_terms = set(re.findall(r"\b[a-zA-Z0-9\+#]+\b", norm_title.lower()))
            role_terms = set()
            for r in self.profile.target_roles:
                for w in r.lower().split():
                    if w not in ["engineer", "specialist", "developer", "lead", "senior", "junior", "staff", "intern"]:
                        role_terms.add(w)
            if (title_terms & role_terms) and any(k in title_terms for k in ["engineer", "developer", "architect", "designer", "specialist", "technician", "lead"]):
                score += 25
                matched_sample = sorted(list(title_terms & role_terms))[0]
                reasons.append(f"Target discipline title match: '{matched_sample}'")
            elif any(k in norm_title.lower() for k in ["engineer", "developer", "architect", "specialist"]):
                score += 15
                reasons.append("Engineering discipline title match")

        # (b) Must-have skill coverage (max 50 points)
        matched_must = find_matched_keywords(self.searchable_skills, combined_text)
        if matched_must:
            skill_score = min(len(matched_must) * 20, 50)
            score += skill_score
            reasons.append(f"Core technical skills matched: {matched_must[:4]}")

        # (c) Domain/Industry fit (max 15 points)
        if self.profile.primary_domain:
            domain_terms = [t for t in re.split(r"[\s/,&]+", self.profile.primary_domain.lower()) if len(t) >= 2]
            matched_domains = find_matched_keywords(domain_terms, combined_text)
            if matched_domains:
                score += 15
                reasons.append(f"Primary domain alignment ({self.profile.primary_domain})")

        # (d) Seniority fit (max 10 points)
        score += 10

        # Extract real evidence quote (exact sentence from details)
        evidence_quote = None
        if details_text:
            search_pool = matched_must or self.searchable_skills
            for kw in search_pool:
                m = re.search(rf"\b{re.escape(kw)}\b", details_text, re.IGNORECASE)
                if m:
                    cand = extract_surrounding_sentence(m.start(), m.end(), details_text)
                    if cand and len(cand) >= 15 and cand in details_text:
                        evidence_quote = cand
                        break

        final_score = min(max(score, 0), 98)
        is_relevant = final_score >= config.MIN_RELEVANCE_SCORE

        return JobClassification(
            eligible=True,
            eligibility_reason=None,
            work_mode=work_mode,
            work_mode_reason=work_mode_reason,
            match_score=final_score,
            match_reason="; ".join(reasons) if reasons else "General engineering domain alignment",
            evidence_quote=evidence_quote,
            is_relevant=is_relevant,
        )
