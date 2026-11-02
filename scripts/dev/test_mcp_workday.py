import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp_servers.career_page_reader.server import detect_ats, list_jobs

print("Testing NXP (Europe)...")
det = detect_ats("https://nxp.wd3.myworkdayjobs.com/careers")
print("Detection:", det)
jobs = list_jobs("https://nxp.wd3.myworkdayjobs.com/careers")
print(f"NXP Jobs extracted via MCP Server: {len(jobs)}")
for j in jobs[:3]:
    print(f"  * {j['title']} | {j['location']} -> {j['job_url']}")

print("\nTesting Thales (Europe)...")
det_thales = detect_ats("https://thales.wd3.myworkdayjobs.com/Careers")
print("Detection:", det_thales)
thales_jobs = list_jobs("https://thales.wd3.myworkdayjobs.com/Careers")
print(f"Thales Jobs extracted via MCP Server: {len(thales_jobs)}")
for j in thales_jobs[:3]:
    print(f"  * {j['title']} | {j['location']} -> {j['job_url']}")
