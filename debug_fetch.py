"""Quick analysis of the daxiao page structure."""
from pathlib import Path
import httpx
import re

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
r = httpx.get("https://odds.500.com/fenxi/daxiao-1092884.shtml", headers=headers, timeout=15)
print(f"Status: {r.status_code}, Length: {len(r.text)}")

# Save for analysis
Path("debug_daxiao.html").write_bytes(r.content)

# Search for company names and table structures
html = r.text
for kw in ["威廉", "立博", "Bet365", "table", "class=", "tbody", "id="]:
    count = html.count(kw)
    idx = html.find(kw)
    snippet = html[max(0, idx-20):idx+100]
    print(f"\n'{kw}': {count} occurrences, first: {snippet!r}")
