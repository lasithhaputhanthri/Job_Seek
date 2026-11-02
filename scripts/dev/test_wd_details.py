import httpx

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

endpoints = [
    ("NXP Semiconductors", "https://nxp.wd3.myworkdayjobs.com/wday/cxs/nxp/careers/jobs", "https://nxp.wd3.myworkdayjobs.com/en-US/careers"),
    ("Analog Devices", "https://analogdevices.wd1.myworkdayjobs.com/wday/cxs/analogdevices/External/jobs", "https://analogdevices.wd1.myworkdayjobs.com/en-US/External"),
    ("Thales Group", "https://thales.wd3.myworkdayjobs.com/wday/cxs/thales/Careers/jobs", "https://thales.wd3.myworkdayjobs.com/en-US/Careers"),
]

keywords = ["RF", "Hardware", "PCB", "Embedded", "FPGA"]

for company, ep, base_url in endpoints:
    print(f"\n=== {company} ===")
    for kw in keywords:
        payload = {"appliedFacets": {}, "limit": 10, "offset": 0, "searchText": kw}
        try:
            r = httpx.post(ep, json=payload, headers=headers, timeout=8.0)
            if r.status_code == 200:
                data = r.json()
                total = data.get("total", 0)
                print(f"  Keyword '{kw}': {total} jobs found")
                for j in data.get("jobPostings", [])[:2]:
                    external_path = j.get("externalPath", "")
                    job_url = f"{base_url}{external_path}"
                    print(f"    * {j.get('title')} | {j.get('locationsText')} -> {job_url}")
        except Exception as e:
            print(f"  Error {kw}: {e}")
