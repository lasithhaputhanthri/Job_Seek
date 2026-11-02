import httpx

# Ashby uses a POST or public job-board API
headers = {"User-Agent": "Mozilla/5.0"}
try:
    r = httpx.get("https://jobs.ashbyhq.com/framework", headers=headers, follow_redirects=True)
    print("Framework Ashby HTML status:", r.status_code)
    # Check if Ashby embed json is present in the HTML
    if "window.__INITIAL_STATE__" in r.text or "job-board" in r.text:
        print("Framework Ashby HTML contains job data")
except Exception as e:
    print("Ashby error:", e)

# SmartRecruiters
try:
    r = httpx.get("https://api.smartrecruiters.com/v1/companies/smartrecruiters/postings", headers=headers)
    print("SmartRecruiters status:", r.status_code, "count:", len(r.json().get("content", [])))
except Exception as e:
    print("SmartRecruiters error:", e)
