import httpx

# Test Workday public REST endpoint for European hardware giants
# ASML, NXP, Ericsson, Analog Devices, Thales
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

workday_targets = [
    # NXP Semiconductors (Netherlands / Germany / Europe)
    ("NXP (Europe)", "https://nxp.wd3.myworkdayjobs.com/wday/cxs/nxp/careers/jobs"),
    # Ericsson (Sweden / Europe - Massive RF / 5G)
    ("Ericsson (Europe/Sweden)", "https://ericsson.wd3.myworkdayjobs.com/wday/cxs/ericsson/External/jobs"),
    # Analog Devices (Ireland / Europe)
    ("Analog Devices (Europe)", "https://analogdevices.wd1.myworkdayjobs.com/wday/cxs/analogdevices/External/jobs"),
    # Thales (France / Europe - Defense / Radar)
    ("Thales (Europe)", "https://thales.wd3.myworkdayjobs.com/wday/cxs/thales/Careers/jobs"),
]

for name, endpoint in workday_targets:
    payload = {
        "appliedFacets": {},
        "limit": 20,
        "offset": 0,
        "searchText": "Hardware",
    }
    try:
        r = httpx.post(endpoint, json=payload, headers=headers, timeout=10.0)
        print(f"Testing {name}: HTTP {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            total = data.get("total", 0)
            items = data.get("jobPostings", [])
            print(f"  -> SUCCESS! Found {total} total jobs matching 'Hardware' at {name}!")
            for item in items[:3]:
                print(f"     * {item.get('title')} ({item.get('locationsText')})")
    except Exception as e:
        print(f"  -> Error for {name}: {e}")
