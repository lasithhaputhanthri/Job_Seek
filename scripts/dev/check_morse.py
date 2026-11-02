import httpx
from bs4 import BeautifulSoup

r = httpx.get("https://www.morsemicro.com/careers", follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
soup = BeautifulSoup(r.text, "html.parser")
links = [a["href"] for a in soup.find_all("a", href=True) if any(k in a["href"] for k in ["greenhouse", "lever", "ashby", "bamboohr", "workable", "jobs"])]
print("Morse Micro Job Links:", links[:5])
