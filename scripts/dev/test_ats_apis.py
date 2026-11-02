import httpx

# Test Greenhouse public API
print("Testing Greenhouse (Anduril)...")
try:
    r = httpx.get("https://boards-api.greenhouse.io/v1/boards/andurilindustries/jobs", timeout=10.0)
    data = r.json()
    jobs = data.get("jobs", [])
    print(f"Greenhouse Anduril: Found {len(jobs)} open jobs! First: {jobs[0]['title'] if jobs else 'None'}")
except Exception as e:
    print(f"Greenhouse error: {e}")

# Test Ashby public API
print("Testing Ashby (Oxide Computer)...")
try:
    r = httpx.get("https://api.ashbyhq.com/posting-api/job-board/oxidecomputer", timeout=10.0)
    data = r.json()
    jobs = data.get("jobs", [])
    print(f"Ashby Oxide: Found {len(jobs)} open jobs! First: {jobs[0]['title'] if jobs else 'None'}")
except Exception as e:
    print(f"Ashby error: {e}")

# Test Lever public API
print("Testing Lever...")
try:
    r = httpx.get("https://api.lever.co/v0/postings/palantir?mode=json", timeout=10.0)
    data = r.json()
    print(f"Lever Palantir: Found {len(data)} open jobs! First: {data[0]['text'] if data else 'None'}")
except Exception as e:
    print(f"Lever error: {e}")
