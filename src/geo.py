"""
Geographic Location & Country Resolution Module.
Resolves accurate country information from job location strings using strict word boundaries,
comprehensive alias dictionaries, US state mapping, and multilingual city definitions.

Strict Ground Rule:
Never falls back to the company's headquarters country.
If location cannot be resolved, returns 'Unknown' with 0.0 confidence.
"""

import re
from typing import Dict, List, Optional, Set, Tuple
from src.text_match import normalize_text, compile_word_regex


# Canonical Country Definitions & ISO Codes
CANONICAL_COUNTRIES: Dict[str, str] = {
    "NL": "Netherlands",
    "DE": "Germany",
    "FR": "France",
    "IE": "Ireland",
    "GB": "UK",
    "UK": "UK",
    "US": "USA",
    "USA": "USA",
    "CH": "Switzerland",
    "AT": "Austria",
    "BE": "Belgium",
    "ES": "Spain",
    "IT": "Italy",
    "SE": "Sweden",
    "DK": "Denmark",
    "PL": "Poland",
    "CZ": "Czech Republic",
    "AU": "Australia",
    "AE": "UAE",
    "IN": "India",
    "CN": "China",
    "MY": "Malaysia",
    "PH": "Philippines",
    "SG": "Singapore",
    "TR": "Turkey",
    "CA": "Canada",
    "JP": "Japan",
    "NO": "Norway",
    "FI": "Finland",
    "PT": "Portugal",
    "TW": "Taiwan",
}


def canonicalize_country(c: Optional[str]) -> str:
    """Canonicalizes country string or code into unified canonical name."""
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
        "england": "UK",
        "scotland": "UK",
        "wales": "UK",
        "deutschland": "Germany",
        "the netherlands": "Netherlands",
        "holland": "Netherlands",
    }
    if norm in synonyms:
        return synonyms[norm]
    if c.upper() in CANONICAL_COUNTRIES:
        return CANONICAL_COUNTRIES[c.upper()]
    return COUNTRY_NAME_ALIASES.get(norm, c.strip())

# Country name aliases (lowercase) -> Canonical Country Name
COUNTRY_NAME_ALIASES: Dict[str, str] = {
    "netherlands": "Netherlands",
    "the netherlands": "Netherlands",
    "holland": "Netherlands",
    "germany": "Germany",
    "deutschland": "Germany",
    "france": "France",
    "republique francaise": "France",
    "ireland": "Ireland",
    "republic of ireland": "Ireland",
    "united kingdom": "UK",
    "great britain": "UK",
    "england": "UK",
    "scotland": "UK",
    "wales": "UK",
    "northern ireland": "UK",
    "united states": "USA",
    "united states of america": "USA",
    "switzerland": "Switzerland",
    "schweiz": "Switzerland",
    "suisse": "Switzerland",
    "svizzera": "Switzerland",
    "austria": "Austria",
    "osterreich": "Austria",
    "belgium": "Belgium",
    "belgique": "Belgium",
    "belgie": "Belgium",
    "spain": "Spain",
    "espana": "Spain",
    "italy": "Italy",
    "italia": "Italy",
    "sweden": "Sweden",
    "sverige": "Sweden",
    "denmark": "Denmark",
    "danmark": "Denmark",
    "poland": "Poland",
    "polska": "Poland",
    "czech republic": "Czech Republic",
    "czechia": "Czech Republic",
    "australia": "Australia",
    "united arab emirates": "UAE",
    "india": "India",
    "china": "China",
    "peoples republic of china": "China",
    "malaysia": "Malaysia",
    "philippines": "Philippines",
    "singapore": "Singapore",
    "turkey": "Turkey",
    "turkiye": "Turkey",
    "canada": "Canada",
    "japan": "Japan",
    "norway": "Norway",
    "norge": "Norway",
    "finland": "Finland",
    "suomi": "Finland",
    "portugal": "Portugal",
    "taiwan": "Taiwan",
}

# Multilingual Cities & Regions -> Canonical Country
CITY_REGION_MAP: Dict[str, str] = {
    # Netherlands
    "amsterdam": "Netherlands",
    "eindhoven": "Netherlands",
    "delft": "Netherlands",
    "rotterdam": "Netherlands",
    "utrecht": "Netherlands",
    "hengelo": "Netherlands",
    "nijmegen": "Netherlands",
    "enschede": "Netherlands",
    "veldhoven": "Netherlands",
    "groningen": "Netherlands",
    "leiden": "Netherlands",
    "hertogenbosch": "Netherlands",
    "den bosch": "Netherlands",
    "arnhem": "Netherlands",
    "tilburg": "Netherlands",
    "breda": "Netherlands",

    # Germany
    "berlin": "Germany",
    "munich": "Germany",
    "munchen": "Germany",
    "dresden": "Germany",
    "stuttgart": "Germany",
    "nuremberg": "Germany",
    "nurnberg": "Germany",
    "frankfurt": "Germany",
    "frankfurt am main": "Germany",
    "hamburg": "Germany",
    "augsburg": "Germany",
    "dusseldorf": "Germany",
    "koln": "Germany",
    "cologne": "Germany",
    "leipzig": "Germany",
    "erlangen": "Germany",
    "regensburg": "Germany",
    "parsdorf": "Germany",
    "ingolstadt": "Germany",
    "hannover": "Germany",
    "bonn": "Germany",
    "mannheim": "Germany",
    "karlsruhe": "Germany",
    "ulm": "Germany",
    "braunschweig": "Germany",
    "aachen": "Germany",
    "bremen": "Germany",

    # France
    "paris": "France",
    "toulouse": "France",
    "sophia-antipolis": "France",
    "sophia antipolis": "France",
    "valbonne": "France",
    "grenoble": "France",
    "bordeaux": "France",
    "merignac": "France",
    "lyon": "France",
    "rennes": "France",
    "nantes": "France",
    "marseille": "France",
    "nice": "France",
    "caen": "France",
    "strasbourg": "France",
    "lille": "France",
    "montpellier": "France",
    "massy": "France",
    "velizy": "France",

    # Ireland
    "dublin": "Ireland",
    "cork": "Ireland",
    "limerick": "Ireland",
    "galway": "Ireland",
    "shannon": "Ireland",
    "waterford": "Ireland",
    "leixlip": "Ireland",

    # UK
    "london": "UK",
    "cambridge": "UK",
    "bristol": "UK",
    "edinburgh": "UK",
    "glasgow": "UK",
    "belfast": "UK",
    "oxford": "UK",
    "reading": "UK",
    "manchester": "UK",
    "birmingham": "UK",
    "leeds": "UK",
    "sheffield": "UK",
    "southampton": "UK",
    "newcastle": "UK",
    "bath": "UK",
    "shetland": "UK",
    "malmesbury": "UK",
    "hull": "UK",
    "warwick": "UK",

    # Austria
    "vienna": "Austria",
    "wien": "Austria",
    "graz": "Austria",
    "gratkorn": "Austria",
    "linz": "Austria",
    "salzburg": "Austria",
    "innsbruck": "Austria",
    "villach": "Austria",
    "klagenfurt": "Austria",

    # Switzerland
    "zurich": "Switzerland",
    "geneva": "Switzerland",
    "geneve": "Switzerland",
    "lausanne": "Switzerland",
    "basel": "Switzerland",
    "bern": "Switzerland",
    "neuchatel": "Switzerland",
    "zug": "Switzerland",
    "winterthur": "Switzerland",

    # Belgium
    "brussels": "Belgium",
    "bruxelles": "Belgium",
    "leuven": "Belgium",
    "antwerp": "Belgium",
    "ghent": "Belgium",
    "tubize": "Belgium",
    "liege": "Belgium",
    "charleroi": "Belgium",

    # Spain
    "madrid": "Spain",
    "barcelona": "Spain",
    "valencia": "Spain",
    "seville": "Spain",
    "sevilla": "Spain",
    "malaga": "Spain",
    "bilbao": "Spain",
    "zaragoza": "Spain",

    # Italy
    "rome": "Italy",
    "roma": "Italy",
    "milan": "Italy",
    "milano": "Italy",
    "turin": "Italy",
    "torino": "Italy",
    "bologna": "Italy",
    "florence": "Italy",
    "firenze": "Italy",
    "agrate": "Italy",
    "catania": "Italy",
    "genoa": "Italy",
    "naples": "Italy",

    # Sweden
    "stockholm": "Sweden",
    "gothenburg": "Sweden",
    "goteborg": "Sweden",
    "malmo": "Sweden",
    "lund": "Sweden",
    "kiruna": "Sweden",
    "kista": "Sweden",
    "linkoping": "Sweden",
    "uppsala": "Sweden",

    # Denmark
    "copenhagen": "Denmark",
    "kobenhavn": "Denmark",
    "aarhus": "Denmark",
    "odense": "Denmark",
    "aalborg": "Denmark",
    "horsholm": "Denmark",

    # Czech Republic
    "prague": "Czech Republic",
    "praha": "Czech Republic",
    "brno": "Czech Republic",
    "ostrava": "Czech Republic",
    "plzen": "Czech Republic",

    # Poland
    "warsaw": "Poland",
    "warszawa": "Poland",
    "krakow": "Poland",
    "wroclaw": "Poland",
    "gdansk": "Poland",
    "katowice": "Poland",
    "poznan": "Poland",

    # Turkey
    "istanbul": "Turkey",
    "ankara": "Turkey",
    "izmir": "Turkey",
    "bursa": "Turkey",

    # China
    "shanghai": "China",
    "shenzhen": "China",
    "beijing": "China",
    "guangzhou": "China",
    "chengdu": "China",
    "hangzhou": "China",
    "wuhan": "China",
    "suzhou": "China",
    "xian": "China",

    # Malaysia
    "kuala lumpur": "Malaysia",
    "penang": "Malaysia",
    "george town": "Malaysia",
    "petaling jaya": "Malaysia",
    "cyberjaya": "Malaysia",
    "johor bahru": "Malaysia",
    "kulim": "Malaysia",

    # Philippines
    "manila": "Philippines",
    "taguig": "Philippines",
    "makati": "Philippines",
    "cebu": "Philippines",
    "quezon city": "Philippines",

    # Singapore
    "singapore": "Singapore",

    # India
    "bangalore": "India",
    "bengaluru": "India",
    "hyderabad": "India",
    "noida": "India",
    "pune": "India",
    "chennai": "India",
    "mumbai": "India",
    "gurgaon": "India",
    "gurugram": "India",
    "delhi": "India",
    "new delhi": "India",

    # Australia
    "sydney": "Australia",
    "melbourne": "Australia",
    "brisbane": "Australia",
    "adelaide": "Australia",
    "perth": "Australia",
    "canberra": "Australia",
    "hobart": "Australia",

    # UAE
    "dubai": "UAE",
    "abu dhabi": "UAE",
    "sharjah": "UAE",

    # USA Major Cities
    "san francisco": "USA",
    "san jose": "USA",
    "austin": "USA",
    "seattle": "USA",
    "boston": "USA",
    "redmond": "USA",
    "los angeles": "USA",
    "san diego": "USA",
    "new york": "USA",
    "new york city": "USA",
    "nyc": "USA",
    "denver": "USA",
    "boulder": "USA",
    "dallas": "USA",
    "houston": "USA",
    "chicago": "USA",
    "atlanta": "USA",
    "raleigh": "USA",
    "durham": "USA",
    "reston": "USA",
    "broomfield": "USA",
    "somerville": "USA",
    "costa mesa": "USA",
    "sunnyvale": "USA",
    "santa clara": "USA",
    "mountain view": "USA",
    "palo alto": "USA",
    "cupertino": "USA",
    "chandler": "USA",
    "wilmington": "USA",
    "somerset": "USA",
}

# US State Names & 2-letter Postal Codes (mapped to USA)
US_STATE_NAMES: Set[str] = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york", "north carolina",
    "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania", "rhode island",
    "south carolina", "south dakota", "tennessee", "texas", "utah", "vermont",
    "virginia", "washington", "west virginia", "wisconsin", "wyoming",
    "district of columbia"
}

US_STATE_CODES: Set[str] = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC"
}

# Remote anywhere indicators
REMOTE_ANYWHERE_PATTERNS = [
    r"\b(?:remote\s*-\s*anywhere|work\s+from\s+anywhere|remote\s+worldwide)\b",
    r"\b(?:anywhere\s+in\s+the\s+world|global\s+remote|fully\s+remote\s+global)\b",
    r"\b(?:remote\s*-\s*(?:global|emea|worldwide|international))\b",
]


def resolve_country_from_location(location_str: Optional[str]) -> Tuple[str, float, bool]:
    """
    Resolves the canonical country from a job posting's location string.
    Returns: (country_name, confidence, is_remote_anywhere)

    confidence ranges from 0.0 (unresolved) to 1.0 (exact country/city match).
    If unresolvable, returns ('Unknown', 0.0, False).
    """
    if not location_str:
        return ("Unknown", 0.0, False)

    raw_str = normalize_text(location_str).strip()
    norm = raw_str.lower()
    if not norm:
        return ("Unknown", 0.0, False)

    # 1. Check for remote anywhere indicators
    is_remote_anywhere = False
    for p in REMOTE_ANYWHERE_PATTERNS:
        if re.search(p, norm, re.IGNORECASE):
            is_remote_anywhere = True
            break

    # 2. Check for Specific City / Region match first (highest specificity)
    for city, canonical in CITY_REGION_MAP.items():
        if compile_word_regex(city).search(norm):
            return (canonical, 0.95, is_remote_anywhere)

    # 3. Check for US State names or Postal Codes (e.g., "Austin, TX", "San Jose, CA")
    for state_name in US_STATE_NAMES:
        if compile_word_regex(state_name).search(norm):
            return ("USA", 0.95, is_remote_anywhere)

    # Look for US state code pattern: ", CA", ", TX", "- CA", "/ CA"
    for code in US_STATE_CODES:
        # Match ", TX" or "Austin TX" or "TX, USA"
        if re.search(rf"(?:,\s*|\s*-\s*|\s*/\s*|\b){code}\b", raw_str):
            # Only treat as US state if followed or preceded by city/punctuation, or if US code
            if re.search(rf"[,\-/]\s*{code}\b", raw_str) or re.search(rf"\b{code}\s*,\s*(?:USA|US)\b", raw_str, re.IGNORECASE):
                return ("USA", 0.90, is_remote_anywhere)

    # 4. Check for exact full country name match in dictionary
    for alias, canonical in COUNTRY_NAME_ALIASES.items():
        if compile_word_regex(alias).search(norm):
            return (canonical, 1.0, is_remote_anywhere)

    # 5. Check for unambiguous 2-3 letter ISO country codes (e.g. "NL", "DE", "FR", "UK", "USA")
    for code, canonical in CANONICAL_COUNTRIES.items():
        # Avoid confusing state code CA with Canada unless standalone or with Canada context
        if code == "CA" and ("california" in norm or re.search(r"[,\-/]\s*CA\b", raw_str)):
            continue
        if compile_word_regex(code).search(raw_str):
            return (canonical, 0.90, is_remote_anywhere)

    # 6. Fallback if "Remote" is the only word
    if norm in ["remote", "work from home", "virtual", "anywhere"]:
        return ("Remote / Global", 0.60, True)

    return ("Unknown", 0.0, is_remote_anywhere)
