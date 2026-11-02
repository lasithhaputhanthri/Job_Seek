import httpx

candidates = [
    ("Lilium (Germany)", "https://boards-api.greenhouse.io/v1/boards/lilium/jobs"),
    ("Celonis (Germany)", "https://boards-api.greenhouse.io/v1/boards/celonis/jobs"),
    ("DeepL (Germany)", "https://boards-api.greenhouse.io/v1/boards/deepl/jobs"),
    ("GetYourGuide (Germany/Europe)", "https://boards-api.greenhouse.io/v1/boards/getyourguide/jobs"),
    ("Oxford Nanopore (UK)", "https://boards-api.greenhouse.io/v1/boards/oxfordnanopore/jobs"),
    ("Canva (Australia)", "https://boards-api.greenhouse.io/v1/boards/canva/jobs"),
    ("SafetyCulture (Australia)", "https://boards-api.greenhouse.io/v1/boards/safetyculture/jobs"),
    ("Rokt (Australia)", "https://boards-api.greenhouse.io/v1/boards/rokt/jobs"),
    ("Careem (UAE)", "https://boards-api.greenhouse.io/v1/boards/careem/jobs"),
    ("Noon (UAE)", "https://api.lever.co/v0/postings/noon?mode=json"),
]

for name, url in candidates:
    try:
        r = httpx.get(url, timeout=5.0)
        if r.status_code == 200:
            count = len(r.json().get("jobs", r.json()) if isinstance(r.json(), dict) else r.json())
            print(f"AVAILABLE: {name} -> {count} jobs")
    except Exception:
        pass
