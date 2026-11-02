import httpx

candidates = [
    "https://morsemicro.bamboohr.com/careers",
    "https://morsemicro.bamboohr.com/jobs",
    "https://droneshield.bamboohr.com/careers",
    "https://gilmourspace.bamboohr.com/careers",
    "https://fleetspace.bamboohr.com/careers",
    "https://baraja.bamboohr.com/careers",
]

for url in candidates:
    try:
        r = httpx.get(url, timeout=4.0, follow_redirects=True)
        if r.status_code == 200 and "bamboohr.com" in str(r.url):
            print(f"VERIFIED BAMBOOHR: {url} -> status 200 (URL: {r.url})")
    except Exception:
        pass
