"""
Taxonomy Engine & Search Vocabulary Generator.
Converts UserProfile into a multi-language search taxonomy (data/taxonomy.json)
for zero-token deterministic title filtering and targeted ATS queries.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.config import config
from src.agents.llm_engine import ai_engine
from src.schemas import UserProfile
from src.text_match import normalize_text

logger = logging.getLogger("TaxonomyEngine")


class SearchTaxonomy(BaseModel):
    role_synonyms: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Target roles and equivalents (including DE/FR/NL multilingual variants)"
    )
    skill_synonyms: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Core technical skill aliases and tools"
    )
    sector_keywords: List[str] = Field(default_factory=list)
    include_title_patterns: List[str] = Field(default_factory=list)
    exclude_title_patterns: List[str] = Field(default_factory=list)
    seniority_terms_to_include: List[str] = Field(default_factory=list)
    seniority_terms_to_exclude: List[str] = Field(default_factory=list)
    ambiguous_terms_with_rules: Dict[str, str] = Field(default_factory=dict)
    workday_search_terms: List[str] = Field(default_factory=list)


class TaxonomyGenerator:
    def __init__(self, profile: UserProfile):
        self.profile = profile
        self.taxonomy_file = config.DEFAULT_TAXONOMY_PATH

    def generate_or_load(self, force_refresh: bool = False) -> SearchTaxonomy:
        """Loads cached taxonomy or generates a new one."""
        if not force_refresh and self.taxonomy_file.exists():
            try:
                with open(self.taxonomy_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return SearchTaxonomy(**data)
            except Exception as e:
                logger.warning(f"Failed to read taxonomy cache: {e}. Generating new taxonomy.")

        taxonomy = self._generate()
        self.save_taxonomy(taxonomy)
        return taxonomy

    def save_taxonomy(self, taxonomy: SearchTaxonomy):
        """Persists taxonomy to data/taxonomy.json."""
        self.taxonomy_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.taxonomy_file, "w", encoding="utf-8") as f:
            f.write(taxonomy.model_dump_json(indent=2))
        print(f"[TaxonomyEngine] Saved search taxonomy to {self.taxonomy_file.resolve()}")

    def _generate(self) -> SearchTaxonomy:
        """Generates taxonomy using prompt 5.2 or deterministic fallback."""
        if ai_engine.is_live:
            try:
                prompt_file = config.BASE_DIR / "src" / "prompts" / "taxonomy_generator.md"
                system_instruction = prompt_file.read_text(encoding="utf-8") if prompt_file.exists() else "Generate search taxonomy."

                prompt = f"""CANDIDATE PROFILE:
- Target Roles: {', '.join(self.profile.target_roles)}
- Core Skills: {', '.join(self.profile.must_have_skills)}
- Primary Domain: {self.profile.primary_domain}
- Target Countries: {', '.join(self.profile.target_countries)}
- Seniority Levels: {[s.value if hasattr(s, 'value') else str(s) for s in self.profile.seniority_levels]}
"""
                res = ai_engine.generate_structured(
                    prompt=prompt,
                    response_schema=SearchTaxonomy,
                    system_instruction=system_instruction,
                    model=config.GEMINI_PRO_MODEL,
                )
                if res and res.include_title_patterns:
                    # Supplement workday search terms
                    if not res.workday_search_terms:
                        res.workday_search_terms = self._build_default_workday_terms()
                    return res
            except Exception as e:
                logger.warning(f"[TaxonomyEngine] AI generation warning: {e}. Using deterministic taxonomy.")

        return self._generate_deterministic()

    def _generate_deterministic(self) -> SearchTaxonomy:
        """Deterministic, candidate-tailored taxonomy generation."""
        # Derive search queries from candidate's profile
        include_patterns = []
        for r in self.profile.target_roles:
            include_patterns.append(r.lower())

        for s in self.profile.must_have_skills:
            include_patterns.append(s.lower())

        # Standard non-engineering exclusion titles
        exclude_patterns = [
            "recruiter", "talent acquisition", "human resources", "hr",
            "sales", "account executive", "business development", "marketing",
            "legal", "counsel", "finance", "accountant", "controller",
            "nurse", "receptionist", "assistant", "customer support"
        ]

        # Seniority terms
        seniority_include = [s.value if hasattr(s, "value") else str(s) for s in self.profile.seniority_levels]
        seniority_exclude = ["intern", "internship", "graduate", "trainee", "werkstudent"] if not self.profile.include_internships else []

        # Ambiguous terms rules
        ambiguous = {
            "hybrid beamforming": "Technical antenna concept, NOT hybrid workplace",
            "hybrid coupler": "Passive microwave component, NOT hybrid workplace",
            "remote sensing": "Satellite/radar imaging, NOT remote employment",
            "remotely piloted": "UAV/drone piloting, NOT remote employment",
            "rpc": "Remote procedure call, NOT remote employment",
        }

        # Role multilingual synonyms
        role_synonyms = {}
        for role in self.profile.target_roles:
            role_synonyms[role] = [
                role,
                f"Senior {role}",
                f"{role} (m/w/d)",
                f"Ingenieur {role}",
                f"Ingénieur {role}",
            ]

        return SearchTaxonomy(
            role_synonyms=role_synonyms,
            skill_synonyms={s: [s] for s in self.profile.must_have_skills},
            sector_keywords=self.profile.target_industries or [self.profile.primary_domain],
            include_title_patterns=include_patterns,
            exclude_title_patterns=exclude_patterns,
            seniority_terms_to_include=seniority_include,
            seniority_terms_to_exclude=seniority_exclude,
            ambiguous_terms_with_rules=ambiguous,
            workday_search_terms=self._build_default_workday_terms(),
        )

    def _build_default_workday_terms(self) -> List[str]:
        """Builds diverse Workday search queries derived from profile."""
        terms = set()
        # Add target role keywords
        for r in self.profile.target_roles:
            terms.update([w for w in r.split() if len(w) > 2 and w.lower() not in ["engineer", "developer", "lead"]])

        # Add must have skills
        for s in self.profile.must_have_skills:
            terms.update([w for w in s.split() if len(w) > 2 and w.lower() not in ["design", "systems", "and"]])

        # Comprehensive engineering terms
        fallback_terms = [
            "Hardware", "RF", "PCB", "Embedded", "FPGA", "Electrical",
            "Analog", "Antenna", "Firmware", "Verification", "Validation"
        ]
        terms.update(fallback_terms)
        return sorted(list(terms))[:15]
