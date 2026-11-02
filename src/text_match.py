"""
High-Precision Word-Boundary & Technical Jargon Matching Module.
Eliminates substring false positives (e.g., 'rf' in 'performance', 'hr' in 'through',
'sales' in 'salesforce', 'uk' in 'ukraine', 'test' in 'latest', 'us' in 'status').
Provides pre-compiled regex caches, Unicode handling, and technical jargon disambiguation.
"""

import re
import unicodedata
from functools import lru_cache
from typing import Iterable, List, Optional, Pattern, Set, Tuple


# Technical jargon phrases that must NOT be confused with workplace arrangement
TECHNICAL_JARGON_WORK_MODE_BLOCKLIST: Set[str] = {
    "hybrid beamforming",
    "hybrid coupler",
    "hybrid microwave ic",
    "hybrid mic",
    "hybrid powertrain",
    "hybrid propulsion",
    "hybrid circuit",
    "hybrid architecture",
    "hybrid bonding",
    "hybrid integration",
    "remotely piloted aircraft",
    "remotely operated vehicle",
    "remotely piloted",
    "remote sensing",
    "remote procedure call",
    "remote procedure calls",
    "rpc",
    "remote parts of the globe",
    "remote telemetry",
    "remote monitoring",
    "remote sensor",
    "remote i/o",
    "remote control",
    "remote terminal unit",
    "rtu",
}

# Standard non-engineering exclusion roles
DEFAULT_NON_ENGINEERING_ROLES: Set[str] = {
    "sales",
    "sales representative",
    "account executive",
    "business development",
    "recruiter",
    "technical recruiter",
    "talent acquisition",
    "human resources",
    "hr",
    "hr specialist",
    "hr manager",
    "legal counsel",
    "attorney",
    "paralegal",
    "corporate legal",
    "marketing",
    "marketing manager",
    "brand marketing",
    "product marketing",
    "growth marketing",
    "copywriter",
    "content creator",
    "finance",
    "accountant",
    "financial analyst",
    "controller",
    "nurse",
    "medical doctor",
    "receptionist",
    "executive assistant",
    "office manager",
    "customer support",
    "customer service",
}

# Security clearance / citizenship requirement phrases
CITIZENSHIP_CLEARANCE_PATTERNS: List[str] = [
    r"\b(?:security\s+clearance(?:\s+required)?)\b",
    r"\b(?:active\s+(?:secret|top\s+secret|ts/sci)\s+clearance)\b",
    r"\b(?:must\s+hold\s+(?:a\s+)?(?:secret|ts/sci|security)\s+clearance)\b",
    r"\b(?:citizenship\s+required)\b",
    r"\b(?:us\s+citizenship\s+required)\b",
    r"\b(?:u\.s\.\s+citizen(?:ship)?\s+(?:only|required))\b",
    r"\b(?:must\s+be\s+a\s+(?:u\.s\.|us)\s+citizen)\b",
    r"\b(?:us\s+person\s+(?:status\s+)?required)\b",
    r"\b(?:itar\s+(?:restricted|compliance|requirement|mandate))\b",
    r"\b(?:itar\s+regulated|itar\s+clearance)\b",
    r"\b(?:sole\s+australian\s+citizenship)\b",
    r"\b(?:nv1|nv2|positive\s+vetting)\s+clearance\b",
    r"\b(?:uk\s+national\s+only|sc\s+clearance|dv\s+clearance)\b",
    r"\b(?:eu\s+citizenship\s+required)\b",
]

# Visa sponsorship indicators
VISA_SPONSORSHIP_PATTERNS: List[str] = [
    r"\b(?:visa\s+sponsorship(?:\s+is)?\s+available)\b",
    r"\b(?:we\s+(?:offer|provide)\s+visa\s+sponsorship)\b",
    r"\b(?:visa\s+support(?:\s+provided)?)\b",
    r"\b(?:relocation\s+(?:support|package|assistance|allowance))\b",
    r"\b(?:international\s+applicants\s+welcome)\b",
    r"\b(?:relocation\s+support\s+available)\b",
]

VISA_RESTRICTION_PATTERNS: List[str] = [
    r"\b(?:no\s+visa\s+sponsorship)\b",
    r"\b(?:visa\s+sponsorship\s+not\s+(?:available|offered|provided))\b",
    r"\b(?:unable\s+to\s+sponsor\s+(?:visas?|work\s+authorization))\b",
    r"\b(?:cannot\s+sponsor\s+visas?)\b",
    r"\b(?:must\s+have\s+current\s+work\s+authorization)\b",
    r"\b(?:not\s+providing\s+sponsorship)\b",
]

INTERNSHIP_GRADUATE_PATTERNS: List[str] = [
    r"\b(?:intern|internship|internships|working\s+student|werkstudent)\b",
    r"\b(?:graduate\s+program|graduate\s+scheme|trainee|traineeship)\b",
    r"\b(?:summer\s+intern|co-op|apprentice|apprenticeship)\b",
]


def normalize_text(text: Optional[str]) -> str:
    """Normalizes Unicode characters, linebreaks, and whitespaces."""
    if not text:
        return ""
    # NFKD normalization decomposes accents / special chars cleanly
    normalized = unicodedata.normalize("NFKD", text)
    # Replace non-breaking spaces and exotic whitespace with standard space
    normalized = re.sub(r"[\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]", " ", normalized)
    return normalized


@lru_cache(maxsize=1024)
def compile_word_regex(keyword: str) -> Pattern:
    """
    Compiles a strict word-boundary regex pattern for single or multi-word terms.
    Correctly handles punctuation, slashes (e.g. 'c/c++', 'rf/microwave'), and numbers.
    """
    kw_norm = normalize_text(keyword.strip().lower())
    if not kw_norm:
        return re.compile(r"$^")  # Matches nothing

    # If term contains slashes or hyphens (like 'c/c++' or 'rf-frontend'), escape appropriately
    escaped = re.escape(kw_norm)

    # If first or last character is alphanumeric, wrap with word boundary \b
    prefix = r"\b" if kw_norm[0].isalnum() else r"(?:^|\s)"
    suffix = r"\b" if kw_norm[-1].isalnum() else r"(?:$|\s)"

    return re.compile(prefix + escaped + suffix, re.IGNORECASE)


def matches_word(keyword: str, text: str) -> bool:
    """Checks whether keyword exists as a complete word/phrase in text."""
    if not keyword or not text:
        return False
    norm = normalize_text(text)
    pattern = compile_word_regex(keyword)
    return bool(pattern.search(norm))


def contains_any_word(keywords: Iterable[str], text: str) -> bool:
    """Returns True if any keyword in the list matches as a whole word in text."""
    if not text:
        return False
    norm = normalize_text(text)
    for kw in keywords:
        if compile_word_regex(kw).search(norm):
            return True
    return False


def find_matched_keywords(keywords: Iterable[str], text: str) -> List[str]:
    """Returns all keywords from the collection that match text on word boundaries."""
    if not text:
        return []
    norm = normalize_text(text)
    hits = []
    for kw in keywords:
        if compile_word_regex(kw).search(norm):
            hits.append(kw)
    return hits


def is_non_engineering_role(title: str, custom_exclusions: Optional[Iterable[str]] = None) -> bool:
    """
    Checks if a job title represents a business/non-engineering role
    (e.g., HR, Sales, Legal, Marketing, Nursing, Accounting).
    """
    exclusions = set(custom_exclusions) if custom_exclusions else DEFAULT_NON_ENGINEERING_ROLES
    return contains_any_word(exclusions, title)


def is_internship_or_graduate(title: str) -> bool:
    """Checks if a job title refers to an internship, co-op, or graduate program."""
    norm = normalize_text(title)
    for p in INTERNSHIP_GRADUATE_PATTERNS:
        if re.search(p, norm, re.IGNORECASE):
            return True
    return False


def extract_visa_and_citizenship_signals(details_text: str) -> Tuple[Optional[str], bool, Optional[str]]:
    """
    Scans text for visa sponsorship and citizenship/clearance requirements.
    Returns: (visa_status, citizenship_or_clearance_required, evidence_quote)
    visa_status: 'yes' | 'no' | 'unknown'
    """
    if not details_text:
        return ("unknown", False, None)

    norm = normalize_text(details_text)

    # 1. Check for citizenship / clearance requirements
    for p in CITIZENSHIP_CLEARANCE_PATTERNS:
        m = re.search(p, norm, re.IGNORECASE)
        if m:
            # Extract sentence around match
            quote = extract_surrounding_sentence(m.start(), m.end(), norm)
            return ("no", True, quote)

    # 2. Check for explicit visa restrictions
    for p in VISA_RESTRICTION_PATTERNS:
        m = re.search(p, norm, re.IGNORECASE)
        if m:
            quote = extract_surrounding_sentence(m.start(), m.end(), norm)
            return ("no", False, quote)

    # 3. Check for positive visa sponsorship
    for p in VISA_SPONSORSHIP_PATTERNS:
        m = re.search(p, norm, re.IGNORECASE)
        if m:
            quote = extract_surrounding_sentence(m.start(), m.end(), norm)
            return ("yes", False, quote)

    return ("unknown", False, None)


def extract_surrounding_sentence(start_idx: int, end_idx: int, text: str, max_chars: int = 300) -> str:
    """Extracts the verbatim sentence containing the span [start_idx, end_idx] without mutating text."""
    if not text:
        return ""
    # Find sentence boundaries
    left_delims = [text.rfind(d, 0, start_idx) for d in [".", "!", "?", "\n", "\r"]]
    start = max(left_delims)
    start = 0 if start == -1 else start + 1

    right_delims = [
        idx for idx in [
            text.find(".", end_idx),
            text.find("!", end_idx),
            text.find("?", end_idx),
            text.find("\n", end_idx),
            text.find("\r", end_idx),
        ] if idx != -1
    ]
    end = min(right_delims) if right_delims else len(text)

    quote = text[start:end].strip()
    # Strip leading/trailing quote characters
    quote = quote.strip("\"'“”)")

    if len(quote) < 15:
        s = max(0, start_idx - 10)
        e = min(len(text), end_idx + 40)
        quote = text[s:e].strip()

    return quote


def contains_technical_work_mode_jargon(text: str) -> bool:
    """Checks if text mentions technical phrases that could cause work-mode false positives."""
    norm = normalize_text(text).lower()
    for phrase in TECHNICAL_JARGON_WORK_MODE_BLOCKLIST:
        if phrase in norm:
            return True
    return False


def is_genuine_remote_indicator(text: str) -> bool:
    """
    Checks if text specifies a genuine Remote work arrangement,
    excluding engineering jargon like 'remote sensing' or 'remote procedure calls'.
    """
    norm = normalize_text(text).lower()

    genuine_patterns = [
        r"\b(?:100%\s+remote|fully\s+remote|remote\s+work|work\s+from\s+home|wfh)\b",
        r"\b(?:remote\s+first|remote\s+eligible|remote\s+role|remote\s+opportunity|remote\s+position)\b",
        r"\b(?:telecommute|distributed\s+team|remote\s+option)\b",
        r"\b(?:anywhere\s+in\s+[a-z\s]+|remote\s*-\s*[a-z\s]+)\b",
        r"\b(?:remote,\s*[a-z]+)\b",
        r"\(remote\)",
        r"\b(?:firmware|software|hardware|linux|embedded|developer|engineer|specialist)\s*-\s*remote\b",
    ]

    for p in genuine_patterns:
        if re.search(p, norm, re.IGNORECASE):
            return True

    # If only technical jargon appears without employment terms, reject
    has_jargon = contains_technical_work_mode_jargon(norm)

    if not has_jargon and re.search(r"\b(?:remote)\b", norm, re.IGNORECASE):
        # Bare word 'remote' is genuine only if not adjacent to technical engineering nouns
        if not re.search(r"\bremote\s+(?:sensing|sensing/gis|vehicle|piloting|control|sensor|telemetry|io|monitoring)\b", norm, re.IGNORECASE):
            return True

    return False


def is_genuine_hybrid_indicator(text: str) -> bool:
    """
    Checks if text specifies a genuine Hybrid workplace policy,
    excluding jargon like 'hybrid beamforming' or 'hybrid couplers'.
    """
    norm = normalize_text(text).lower()

    hybrid_policy_patterns = [
        r"\b(?:hybrid\s+workplace|hybrid\s+model|hybrid\s+schedule|hybrid\s+role)\b",
        r"\b(?:hybrid\s+working|hybrid\s+work\s+arrangement|hybrid\s+working\s+environment)\b",
        r"\b(?:\d\s*-\s*\d\s+days\s+(?:per\s+week\s+)?(?:in\s+office|from\s+home))\b",
        r"\b(?:\d\s+days\s+in\s+(?:the\s+)?[a-z\s]+lab\s+and\s+\d\s+days\s+(?:from\s+)?home)\b",
        r"\b(?:\d\s+days\s+in\s+office\s+and\s+\d\s+days\s+remote)\b",
        r"\b(?:\d\s+days\s+on\s+site)\b",
        r"\b(?:hybrid\s*-\s*\d\s+days)\b",
        r"\b(?:hybrid\s+\(\d\s*-\s*\d\s+days\))\b",
        r"\b(?:flexible\s+office\s+and\s+home)\b",
        r"\(hybrid\)",
        r"\b(?:hybrid\s+opportunity)\b",
    ]

    for p in hybrid_policy_patterns:
        if re.search(p, norm, re.IGNORECASE):
            return True

    # Bare 'hybrid' check: ensure it is not an engineering term
    if re.search(r"\bhybrid\b", norm, re.IGNORECASE):
        if not contains_technical_work_mode_jargon(norm):
            # Check context: must not be 'hybrid circuit', 'hybrid bonding', etc.
            if not re.search(r"\bhybrid\s+(?:beamforming|coupler|circuit|bonding|propulsion|powertrain|integration|architecture|ic|cloud)\b", norm, re.IGNORECASE):
                return True

    return False
