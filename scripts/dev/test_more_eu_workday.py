import httpx

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

more_targets = [
    # ASML (Netherlands)
    ("ASML (Netherlands)", "https://asml.wd3.myworkdayjobs.com/wday/cxs/asml/EN_US/jobs"),
    ("ASML (Global)", "https://asml.wd3.myworkdayjobs.com/wday/cxs/asml/ASML_Careers/jobs"),
    # STMicroelectronics (France/Europe)
    ("STMicroelectronics", "https://stmicroelectronics.wd3.myworkdayjobs.com/wday/cxs/stmicroelectronics/careers/jobs"),
    # Rohde & Schwarz (Germany)
    ("Rohde & Schwarz", "https://rohde-schwarz.wd3.myworkdayjobs.com/wday/cxs/rohde-schwarz/careers/jobs"),
    # Safran (France/Europe)
    ("Safran", "https://safran.wd3.myworkdayjobs.com/wday/cxs/safran/Safran/jobs"),
    # Collins Aerospace / Raytheon (Europe)
    ("Collins Aerospace", "https://rtx.wd1.myworkdayjobs.com/wday/cxs/rtx/CollinsAerospace_Careers/jobs"),
    # Qualcomm (Europe / Germany)
    ("Qualcomm (Europe)", "https://qualcomm.wd5.myworkdayjobs.com/wday/cxs/qualcomm/External/jobs"),
]

for name, endpoint in more_targets:
    payload = {"appliedFacets": {}, "limit": 10, "offset": 0, "searchText": "RF"}
    try:
        r = httpx.post(endpoint, json=payload, headers=headers, timeout=8.0)
        if r.status_code == 200:
            data = r.json()
            total = data.get("total", 0)
            print(f"VERIFIED WORKDAY: {name} -> {total} jobs matching 'RF'!")
            for item in data.get("jobPostings", [])[:2]:
                print(f"   * {item.get('title')} ({item.get('locationsText')})")
        else:
            print(f"Status for {name}: HTTP {r.status_code}")
    except Exception as e:
        print(f"Error {name}: {e}")
