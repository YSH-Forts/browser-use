"""Analyze the downloaded daxiao page HTML."""
from pathlib import Path
from bs4 import BeautifulSoup

html = Path("debug_daxiao.html").read_bytes()
# Try utf-8 first, fall back to gbk
try:
    html_text = html.decode("utf-8")
except UnicodeDecodeError:
    try:
        html_text = html.decode("gbk", errors="replace")
    except Exception:
        html_text = html.decode("latin-1", errors="replace")
soup = BeautifulSoup(html_text, "html.parser")

out = []

# Find all tables
tables = soup.find_all("table")
out.append(f"Tables found: {len(tables)}")

for i, tbl in enumerate(tables):
    tbl_id = tbl.get("id", "")
    tbl_class = tbl.get("class", [])
    rows = tbl.find_all("tr")
    out.append(f"\nTable {i}: id={tbl_id!r} class={tbl_class} rows={len(rows)}")

    # Look for company rows
    for j, row in enumerate(rows[:5]):
        tds = row.find_all("td")
        if tds:
            first_td_text = tds[0].get_text(strip=True)
            out.append(f"  Row {j}: first_td={first_td_text!r}, td_count={len(tds)}")

# Find rows with company names
for company in ["威廉", "立博", "Bet365", "韦德", "澳门"]:
    found = soup.find_all("td", string=lambda t: t and company in t)
    out.append(f"\nCompany '{company}' found in {len(found)} td elements")

# Find the main odds table structure
# Look for table with company rows
all_tds = soup.find_all("td")
out.append(f"\nTotal td elements: {len(all_tds)}")

# Sample of first few td texts
sample = [td.get_text(strip=True)[:30] for td in all_tds[:30]]
out.append(f"\nFirst 30 td texts: {sample}")

# Check for specific class patterns
for cls in ["tb_pl", "tb_bf", "pc", "odds"]:
    els = soup.find_all(class_=lambda c: c and cls in str(c))
    out.append(f"\nClass containing '{cls}': {len(els)} elements")

Path("analysis.txt").write_text("\n".join(out), encoding="utf-8")
print("Analysis written to analysis.txt")
