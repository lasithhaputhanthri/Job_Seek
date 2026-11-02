import httpx

aus_candidates = [
    ("Airwallex (Australia)", "https://boards-api.greenhouse.io/v1/boards/airwallex/jobs"),
    ("Immutable (Australia)", "https://boards-api.greenhouse.io/v1/boards/immutable/jobs"),
    ("Culture Amp (Australia)", "https://boards-api.greenhouse.io/v1/boards/cultureamp/jobs"),
    ("SafetyCulture (Australia)", "https://boards-api.greenhouse.io/v1/boards/safetyculture/jobs"),
    ("Nearmap (Australia)", "https://boards-api.greenhouse.io/v1/boards/nearmap/jobs"),
    ("Cochlear (Australia)", "https://boards-api.greenhouse.io/v1/boards/cochlear/jobs"),
]

for name, url in aus_candidates:
    try:
        r = httpx.get(url, timeout=5.0)
        if r.status_code == 200:
            count = len(r.json().get("jobs", []))
            print(f"VERIFIED AUS: {name} -> {count} jobs")
    except Exception:
        pass
