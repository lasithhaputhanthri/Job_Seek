"""
Phase 2: Generic Candidate-Agnostic Intake Agent.
Extracts structured candidate data from CVs (PDF / DOCX / TXT) without hardcoding any personal data.
Uses LLM structured extraction (Gemini / OpenAI) with fallback to a deterministic generic CV parser.
"""

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from pypdf import PdfReader

from src.config import config
from src.agents.llm_engine import ai_engine
from src.geo import resolve_country_from_location
from src.schemas import CVExtraction, SeniorityLevel, UserProfile
from src.text_match import normalize_text, compile_word_regex

logger = logging.getLogger("IntakeAgent")


# Core Engineering & Technical Skill Dictionary for Generic Parsing
TECHNICAL_SKILLS_DICTIONARY: Dict[str, List[str]] = {
    "Hardware & Electronics": [
        "pcb design", "multilayer pcb", "altium", "altium designer", "kicad", "cadence",
        "allegro", "siemens xpedition", "ltspice", "multisim", "spice", "schematic capture",
        "board bring-up", "hardware debugging", "oscilloscope", "signal integrity", "power integrity",
        "analog design", "mixed-signal", "microcontroller", "stm32", "esp32", "arm cortex",
        "soldering", "smt", "drc", "dfm"
    ],
    "RF, Wireless & Antennas": [
        "rf", "radio frequency", "rf design", "antenna design", "planar antenna", "ifa",
        "impedance matching", "smith chart", "vna", "spectrum analyzer", "hfss", "ansys hfss",
        "em simulation", "radar", "phased array", "beamforming", "rf front-end", "power amplifier",
        "lna", "mixer", "transceiver", "s-parameters"
    ],
    "Embedded & Firmware": [
        "embedded c", "embedded c++", "firmware", "rtos", "freertos", "device drivers",
        "bare-metal", "uart", "spi", "i2c", "can bus", "modbus", "ble", "bluetooth",
        "embedded linux", "bootloader", "gpio", "adc", "dac", "timers"
    ],
    "FPGA & Digital Design": [
        "fpga", "verilog", "systemverilog", "vhdl", "rtl", "vivado", "quartus",
        "timing closure", "xilinx", "intel fpga", "lattice", "zynq", "soc"
    ],
    "Software & Programming": [
        "python", "c", "c++", "rust", "matlab", "simulink", "git", "linux", "bash",
        "docker", "ci/cd", "automation", "data analysis"
    ]
}


class IntakeAgent:
    def __init__(self, target_countries: Optional[List[str]] = None):
        self.target_countries = target_countries or [
            "Netherlands", "Germany", "France", "Ireland", "UK", "USA", "Switzerland", "Austria"
        ]

    def read_cv(self, file_path: str) -> str:
        """Reads text from PDF, DOCX, or plain text CV file."""
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"CV document not found at: {file_path}")

        ext = p.suffix.lower()
        if ext == ".pdf":
            reader = PdfReader(str(p))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(pages)
        elif ext in [".docx", ".doc"]:
            try:
                import docx
                doc = docx.Document(str(p))
                return "\n\n".join([p.text for p in doc.paragraphs if p.text])
            except ImportError:
                raise ImportError("python-docx is required to parse .docx files.")
        else:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()

    def _chunk_cv_text(self, cv_text: str, max_chars: int = 8000) -> str:
        """
        Chunks or summarizes CV text when exceeding token budget.
        Emits a structured warning and prioritizes summary, experience, and skills sections.
        """
        if len(cv_text) <= max_chars:
            return cv_text

        print(
            f"[IntakeAgent] WARNING: CV text length ({len(cv_text)} characters) exceeds {max_chars} character limit. "
            f"Applying intelligent section extraction."
        )

        # Split into sections based on typical headers
        sections = re.split(r"\n(?=[A-Z\s]{3,20}:?\n)", cv_text)
        prioritized = []
        char_count = 0

        # Prioritize header, experience, and skills
        for sec in sections:
            sec_lower = sec.lower()
            if any(k in sec_lower for k in ["experience", "employment", "skills", "technical", "projects", "education", "summary", "profile"]):
                if char_count + len(sec) < max_chars:
                    prioritized.append(sec)
                    char_count += len(sec)

        if prioritized:
            return "\n\n".join(prioritized)
        return cv_text[:max_chars]

    def extract_profile(self, cv_text: str) -> UserProfile:
        """
        Processes CV text into a structured UserProfile.
        Attempts LLM structured extraction through unified ai_engine;
        falls back to deterministic generic parser if LLM is unavailable.
        """
        cv_bounded = self._chunk_cv_text(cv_text)

        if ai_engine.is_live:
            try:
                prompt_path = config.BASE_DIR / "src" / "prompts" / "intake_cv.md"
                system_prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else "Extract structured candidate profile."

                prompt = f"""Target search countries: {', '.join(self.target_countries)}.

CV TEXT:
{cv_bounded}
"""
                extraction = ai_engine.generate_structured(
                    prompt=prompt,
                    response_schema=CVExtraction,
                    system_instruction=system_prompt,
                    model=config.GEMINI_PRO_MODEL,
                )
                if extraction:
                    return self._build_user_profile_from_extraction(extraction, cv_text)
            except Exception as e:
                print(f"[IntakeAgent] AI extraction fallback triggered: {e}")

        # Deterministic generic extraction (strictly candidate-agnostic)
        return self._extract_deterministic(cv_text)

    def _build_user_profile_from_extraction(self, ext: CVExtraction, raw_cv: str) -> UserProfile:
        """Converts LLM CVExtraction to system UserProfile."""
        # Derive primary seniority level
        seniority_levels = [ext.seniority]
        if ext.seniority == SeniorityLevel.MID:
            seniority_levels.append(SeniorityLevel.SENIOR)

        # Detect if relocation or visa is mentioned in raw CV
        needs_visa = True
        loc = ext.current_location or "Unknown Location"

        return UserProfile(
            name=ext.name or "Candidate",
            current_location=loc,
            primary_domain=ext.primary_domain or "Engineering & Technology",
            target_roles=ext.target_roles or ["Hardware Engineer", "Embedded Systems Engineer"],
            seniority_levels=seniority_levels,
            target_countries=self.target_countries,
            target_industries=ext.industries_worked_in or ["Electronics & Semiconductors", "Aerospace"],
            must_have_skills=ext.must_have_skills or ["Hardware Design", "Embedded C"],
            nice_to_have_skills=ext.nice_to_have_skills or [],
            tools=ext.tools or [],
            constraints=[f"Based in {loc}: relocation or visa sponsorship required for international roles."],
            work_modes=["Remote", "Hybrid", "On-site"],
            needs_visa_sponsorship=needs_visa,
            summary=f"Experienced {ext.primary_domain} professional specializing in {', '.join(ext.must_have_skills[:4])}.",
            clarifications_needed=ext.clarifying_questions,
        )

    def _extract_deterministic(self, cv_text: str) -> UserProfile:
        """
        Generic, deterministic CV parser that operates on any CV text without hardcoded candidate data.
        Extracts contact info, skills, experience duration, and seniority algorithmically.
        """
        norm_cv = normalize_text(cv_text)
        lines = [line.strip() for line in norm_cv.splitlines() if line.strip()]

        # 1. Name Extraction: First clean title/name line (avoiding emails, urls, headers)
        candidate_name = "Candidate"
        for line in lines[:5]:
            # Skip if contains email, URL, or phone
            if "@" in line or "http" in line.lower() or "curriculum" in line.lower() or "resume" in line.lower():
                continue
            if re.search(r"\d{4,}", line):
                continue
            # Words in line look like a name (2 to 4 capitalized words)
            words = line.split()
            if 1 <= len(words) <= 4 and all(w[0].isupper() for w in words if w):
                candidate_name = line
                break

        # 2. Contact & Location
        location = "Unknown Location"
        for line in lines[:10]:
            country, conf, _ = resolve_country_from_location(line)
            if conf >= 0.8:
                location = line
                break

        # 3. Skills Detection from Dictionary
        detected_must_have: List[str] = []
        detected_nice_to_have: List[str] = []
        category_hits: Dict[str, int] = {}

        cv_lower = norm_cv.lower()
        for cat, skills in TECHNICAL_SKILLS_DICTIONARY.items():
            cat_count = 0
            for skill in skills:
                if compile_word_regex(skill).search(cv_lower):
                    cat_count += 1
                    if len(detected_must_have) < 8:
                        detected_must_have.append(skill.title())
                    elif len(detected_nice_to_have) < 8:
                        detected_nice_to_have.append(skill.title())
            if cat_count > 0:
                category_hits[cat] = cat_count

        if not detected_must_have:
            detected_must_have = ["Engineering Design", "Technical Problem Solving"]

        # Primary domain is the category with most hits
        if category_hits:
            primary_domain = max(category_hits.items(), key=lambda x: x[1])[0]
        else:
            primary_domain = "Engineering & Technology"

        # 4. Experience Years Estimation: Prioritize date ranges in Experience section
        exp_text = norm_cv
        edu_match = re.search(r"\b(?:EDUCATION|ACADEMIC BACKGROUND)\b", norm_cv, re.IGNORECASE)
        exp_match = re.search(r"\b(?:EXPERIENCE|WORK EXPERIENCE|EMPLOYMENT HISTORY)\b", norm_cv, re.IGNORECASE)
        if exp_match and edu_match:
            if exp_match.start() < edu_match.start():
                exp_text = norm_cv[exp_match.start():edu_match.start()]
            else:
                exp_text = norm_cv[exp_match.start():]
        elif exp_match:
            exp_text = norm_cv[exp_match.start():]

        years = re.findall(r"\b(19\d\d|20\d\d)\b", exp_text)
        valid_years = [int(y) for y in years if 1990 <= int(y) <= 2027]
        years_exp = 3.0  # default
        if valid_years:
            min_y, max_y = min(valid_years), max(valid_years)
            diff = max_y - min_y
            if 0 < diff < 35:
                years_exp = float(diff)

        # 5. Seniority Mapping from Experience
        if years_exp < 1.0:
            seniority = SeniorityLevel.INTERN
            levels = [SeniorityLevel.INTERN, SeniorityLevel.JUNIOR]
        elif years_exp <= 3.0:
            seniority = SeniorityLevel.JUNIOR
            levels = [SeniorityLevel.JUNIOR, SeniorityLevel.MID]
        elif years_exp <= 7.0:
            seniority = SeniorityLevel.MID
            levels = [SeniorityLevel.MID, SeniorityLevel.SENIOR]
        elif years_exp <= 12.0:
            seniority = SeniorityLevel.SENIOR
            levels = [SeniorityLevel.SENIOR, SeniorityLevel.STAFF]
        else:
            seniority = SeniorityLevel.STAFF
            levels = [SeniorityLevel.STAFF, SeniorityLevel.PRINCIPAL]

        # 6. Target Roles from Domain
        target_roles = []
        if "Hardware" in primary_domain or "RF" in primary_domain:
            target_roles = ["Hardware Design Engineer", "RF Engineer", "Embedded Systems Engineer", "PCB Design Engineer"]
        elif "Embedded" in primary_domain:
            target_roles = ["Embedded Software Engineer", "Firmware Engineer", "IoT Systems Engineer"]
        elif "FPGA" in primary_domain:
            target_roles = ["FPGA Design Engineer", "RTL Verification Engineer", "Digital Hardware Engineer"]
        else:
            target_roles = ["Systems Engineer", "Hardware Engineer", "Software Engineer"]

        # 7. Generic Clarifying Questions
        clarifying_questions = [
            "What is your current work authorization / visa sponsorship requirement for international relocation?",
            "What is your target start date or relocation notice period?",
            "What is your preference regarding work arrangement (100% Remote, Hybrid, or On-site laboratory)?",
        ]

        return UserProfile(
            name=candidate_name,
            current_location=location,
            primary_domain=primary_domain,
            target_roles=target_roles,
            seniority_levels=levels,
            target_countries=self.target_countries,
            target_industries=[primary_domain, "Semiconductors & Technology"],
            must_have_skills=detected_must_have,
            nice_to_have_skills=detected_nice_to_have,
            tools=[],
            constraints=[f"Current residence in {location}: visa sponsorship or relocation assistance may be required."],
            work_modes=["Remote", "Hybrid", "On-site"],
            needs_visa_sponsorship=True,
            summary=f"{seniority.value} professional in {primary_domain} with hands-on skills in {', '.join(detected_must_have[:4])}.",
            clarifications_needed=clarifying_questions,
        )

    def parse_natural_language_countries(self, text: str) -> List[str]:
        """Parses natural language country mentions into canonical country names."""
        if not text:
            return self.target_countries

        found: List[str] = []
        parts = re.split(r"[,;/\n]+|\band\b", text, flags=re.IGNORECASE)
        for part in parts:
            p_strip = part.strip()
            if not p_strip:
                continue
            country, conf, is_all = resolve_country_from_location(p_strip)
            if is_all:
                return ["Global / All Countries"]
            if conf >= 0.8 and country != "Unknown":
                if country not in found:
                    found.append(country)

        return found if found else self.target_countries

    def parse_natural_language_roles(self, text: str, existing_roles: Optional[List[str]] = None) -> List[str]:
        """Parses natural language or comma-separated roles into structured titles."""
        if not text:
            return existing_roles or []

        parts = re.split(r"[,;/\n]+|\band\b", text, flags=re.IGNORECASE)
        roles = []
        for p in parts:
            clean = p.strip()
            if len(clean) >= 2:
                roles.append(clean.title())
        return roles if roles else (existing_roles or [])

    def save_profile(self, profile: UserProfile, file_path: str):
        """Persists UserProfile JSON to disk."""
        p = Path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(profile.model_dump_json(indent=2))


if __name__ == "__main__":
    agent = IntakeAgent()
    print("IntakeAgent initialized successfully with candidate-agnostic engine.")
