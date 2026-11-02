import httpx

more_candidates = [
    # Australia
    ("Atlassian (Australia)", "https://api.lever.co/v0/postings/atlassian?mode=json"),
    ("SafetyCulture (Australia)", "https://api.lever.co/v0/postings/safetyculture?mode=json"),
    ("Gilmour Space (Australia)", "https://api.lever.co/v0/postings/gilmourspace?mode=json"),
    ("Advanced Navigation (Australia)", "https://boards-api.greenhouse.io/v1/boards/advancednavigation/jobs"),
    # UAE
    ("Careem (UAE)", "https://boards-api.greenhouse.io/v1/boards/careem/jobs"),
    ("Kitopi (UAE)", "https://boards-api.greenhouse.io/v1/boards/kitopi/jobs"),
    ("Talabat (UAE)", "https://boards-api.greenhouse.io/v1/boards/talabat/jobs"),
    # Europe / Germany / Netherlands
    ("Celonis (Germany)", "https://boards-api.greenhouse.io/v1/boards/celonis/jobs"),
    ("Volocopter (Germany)", "https://boards-api.greenhouse.io/v1/boards/volocopter/jobs"),
    ("Lilium (Germany)", "https://api.lever.co/v0/postings/lilium?mode=json"),
    ("Picnic (Netherlands)", "https://boards-api.greenhouse.io/v1/boards/picnic/jobs"),
    ("Adyen (Netherlands)", "https://boards-api.greenhouse.io/v1/boards/adyen/jobs"),
]

for name, url in more_candidates:
    try:
        r = httpx.get(url, timeout=5.0)
        if r.status_code == 200:
            data = r.json()
            count = len(data.get("jobs", data) if isinstance(data, dict) else data)
            print(f"VERIFIED: {name} -> {count} jobs")
    except Exception as e:
        pass
