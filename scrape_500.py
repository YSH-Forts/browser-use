"""
CDP-based scraper for 500.com SFC pages.
Uses the real Chrome profile so it inherits your logged-in session.
"""
from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import sys
import os
from pathlib import Path

import openpyxl

from browser_use import BrowserSession


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DB_PATH = Path("football_odds.db")
EXCEL_PATH = Path("football_odds.xlsx")
START_EXPECT = "24001"
END_EXPECT = "24001"
BASE_URL = "https://zx.500.com/zc/odds_sfc.php"
DAXIAO_BASE = "https://odds.500.com/fenxi/daxiao-{}.shtml"

# Real Chrome profile path on Windows
_CHROME_USER_DATA = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    r"Google\Chrome\User Data"
)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expect TEXT, league TEXT, match_time TEXT, home_team TEXT,
            away_team TEXT, score TEXT, company TEXT, current_handicap TEXT,
            over_odds REAL, under_odds REAL, initial_handicap TEXT,
            over_initial_odds REAL, under_initial_odds REAL, source_url TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(expect, home_team, away_team, company)
        )
    """)
    conn.commit()
    return conn


def upsert(conn: sqlite3.Connection, row: dict):
    conn.execute(
        f"INSERT OR REPLACE INTO odds ({', '.join(row.keys())}) "
        f"VALUES (:{', :'.join(row.keys())})",
        row,
    )
    conn.commit()


def to_excel(conn: sqlite3.Connection):
    rows = conn.execute(
        "SELECT * FROM odds ORDER BY expect, home_team, company"
    ).fetchall()
    if not rows:
        return
    cols = [d[0] for d in conn.execute("SELECT * FROM odds LIMIT 0").description]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Odds"
    ws.append(cols)
    for row in rows:
        ws.append(list(row))
    wb.save(EXCEL_PATH)
    print(f"  Excel: {len(rows)} rows -> {EXCEL_PATH}")


# ---------------------------------------------------------------------------
# JavaScript for main page
# ---------------------------------------------------------------------------
MAIN_PAGE_JS = r"""
() => {
    const results = [];
    document.querySelectorAll('h3').forEach(h3 => {
        const h3Text = h3.innerText || '';
        const timeMatch = h3Text.match(/(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})/);
        if (!timeMatch) return;
        const matchTime = timeMatch[1];

        let league = '', homeTeam = '', awayTeam = '', score = '', daxiaoUrl = '';

        // Find parent container
        let container = h3.parentElement;
        for (let i = 0; i < 5 && container; i++) {
            if (container.tagName === 'DIV' || container.tagName === 'SECTION' || container.tagName === 'TD') break;
            container = container.parentElement;
        }

        // Search siblings for team data
        let sibling = h3.nextElementSibling;
        let foundTeams = false;
        for (let attempt = 0; attempt < 10 && sibling && !foundTeams; attempt++) {
            const cells = sibling.querySelectorAll ? sibling.querySelectorAll('td, th') : [];
            for (const cell of cells) {
                const cellText = cell.innerText.trim();
                const leagueMatch = cellText.match(/\[([^\]]+)\]/);
                if (leagueMatch) {
                    league = leagueMatch[1];
                    const afterLeague = cellText.replace(/\[([^\]]+)\]/, '').trim();
                    const scoreMatch = afterLeague.match(/(\S+)\s+(\d+:\d+)\s+(\S+)/);
                    if (scoreMatch) {
                        homeTeam = scoreMatch[1].trim();
                        score = scoreMatch[2];
                        awayTeam = scoreMatch[3].trim();
                        foundTeams = true;
                        break;
                    }
                }
            }
            const links = sibling.querySelectorAll ? sibling.querySelectorAll('a[href*="daxiao"]') : [];
            for (const link of links) {
                const href = link.href || '';
                if (href.includes('daxiao')) {
                    daxiaoUrl = href;
                    break;
                }
            }
            sibling = sibling.nextElementSibling;
        }

        // Fallback: container search for daxiao links
        if (!daxiaoUrl && container) {
            const links = container.querySelectorAll ? container.querySelectorAll('a[href*="daxiao"]') : [];
            for (const link of links) {
                if ((link.href || '').includes('daxiao')) {
                    daxiaoUrl = link.href;
                    break;
                }
            }
        }

        let matchId = '';
        const idMatch = daxiaoUrl.match(/daxiao-(\d+)/);
        if (idMatch) matchId = idMatch[1];

        if (homeTeam && awayTeam) {
            results.push({
                expect: '', league, match_time: matchTime,
                home_team: homeTeam, away_team: awayTeam, score,
                match_id: matchId, daxiao_url: daxiaoUrl,
            });
        }
    });
    return JSON.stringify(results);
}
"""

# ---------------------------------------------------------------------------
# JavaScript for daxiao page
# ---------------------------------------------------------------------------
DAXIAO_JS = r"""
() => {
    const companies = ['威廉', '立博', '韦德', '澳门', 'Bet365', '平均值'];
    const results = [];
    const allTds = document.querySelectorAll('td');

    for (let i = 0; i < allTds.length; i++) {
        const td = allTds[i];
        const text = td.innerText.trim();
        if (!companies.includes(text)) continue;

        let row = td.parentElement;
        while (row && row.tagName !== 'TR') row = row.parentElement;
        if (!row) continue;

        const cells = Array.from(row.querySelectorAll('td, th')).map(t => {
            let s = t.innerText.trim();
            return s.replace(/\u2191/g, '').replace(/\u2193/g, '');
        });

        const parseNum = s => { s = (s || '').trim(); return s === '' ? null : parseFloat(s); };

        results.push({
            company: text,
            current_handicap: cells[1] || '',
            over_odds: parseNum(cells[2]),
            under_odds: parseNum(cells[3]),
            initial_handicap: cells[4] || '',
            over_initial_odds: parseNum(cells[5]),
            under_initial_odds: parseNum(cells[6]),
        });
    }

    if (results.length === 0) {
        // Dump first 50 td texts for debugging
        const samples = Array.from(allTds).slice(0, 50).map(t => t.innerText.trim()).filter(s => s);
        return JSON.stringify({_debug: true, count: allTds.length, samples});
    }
    return JSON.stringify(results);
}
"""

# ---------------------------------------------------------------------------
# Scrape one expect
# ---------------------------------------------------------------------------
async def scrape_expect(browser: BrowserSession, expect: str, conn: sqlite3.Connection) -> int:
    url = f"{BASE_URL}?expect={expect}"
    print(f"\n{'='*60}")
    print(f"  Scraping expect={expect}")
    print('='*60)

    page = await browser.get_current_page()
    if page is None:
        print("  ERROR: no page")
        return 0

    await page.goto(url)
    await asyncio.sleep(5)

    # Check if we hit login wall
    body_text = await page.evaluate("() => document.body.innerText")
    if "仅登录" in body_text or "登录/注册" in body_text or "用户名" in body_text[:200]:
        print("  ERROR: Login wall detected. Need to login first.")
        print(f"  Page text: {body_text[:300]}")
        return 0

    matches_json = await page.evaluate(MAIN_PAGE_JS)
    try:
        matches = json.loads(matches_json)
    except Exception:
        matches = []
    print(f"  Found {len(matches)} matches")

    if not matches:
        print(f"  Page text (first 200): {body_text[:200]}")

    total_rows = 0
    for i, match in enumerate(matches):
        match["expect"] = expect
        daxiao_url = match.get("daxiao_url", "")
        print(f"  [{i+1}] {match['home_team']} vs {match['away_team']} | {match['score']}")

        if not daxiao_url:
            row = {
                "expect": expect, "league": match.get("league", ""),
                "match_time": match.get("match_time", ""),
                "home_team": match.get("home_team", ""),
                "away_team": match.get("away_team", ""),
                "score": match.get("score", ""),
                "company": "", "current_handicap": "",
                "over_odds": None, "under_odds": None,
                "initial_handicap": "", "over_initial_odds": None,
                "under_initial_odds": None, "source_url": "",
            }
            upsert(conn, row)
            total_rows += 1
            continue

        new_page = await browser.new_page(daxiao_url)
        await asyncio.sleep(5)

        odds_json = await new_page.evaluate(DAXIAO_JS)
        try:
            odds_data = json.loads(odds_json)
        except Exception:
            odds_data = []

        if isinstance(odds_data, dict) and odds_data.get("_debug"):
            print(f"    [DEBUG] No companies. td count={odds_data.get('count')}, samples={odds_data.get('samples', [])[:8]}")
        else:
            print(f"    {len(odds_data)} companies: {[o.get('company','') for o in odds_data]}")

        for odds in odds_data:
            row = {
                "expect": expect,
                "league": match.get("league", ""),
                "match_time": match.get("match_time", ""),
                "home_team": match.get("home_team", ""),
                "away_team": match.get("away_team", ""),
                "score": match.get("score", ""),
                "company": odds.get("company", ""),
                "current_handicap": odds.get("current_handicap", ""),
                "over_odds": odds.get("over_odds"),
                "under_odds": odds.get("under_odds"),
                "initial_handicap": odds.get("initial_handicap", ""),
                "over_initial_odds": odds.get("over_initial_odds"),
                "under_initial_odds": odds.get("under_initial_odds"),
                "source_url": daxiao_url,
            }
            upsert(conn, row)
            total_rows += 1

        await browser.close_page(new_page)
        await asyncio.sleep(1)

    print(f"  expect={expect}: wrote {total_rows} rows")
    return total_rows


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def main():
    # Use real Chrome profile so we inherit the logged-in session
    profile_dir = Path(_CHROME_USER_DATA)
    if profile_dir.exists():
        print(f"Using Chrome profile: {profile_dir}")
        browser = BrowserSession(
            headless=False,
            user_data_dir=str(profile_dir),
            profile_directory="Default",
        )
    else:
        print(f"Chrome profile not found at {profile_dir}, using default")
        browser = BrowserSession(headless=False)

    await browser.start()

    conn = init_db()
    total_rows = 0
    current_expect = START_EXPECT

    try:
        while True:
            rows = await scrape_expect(browser, current_expect, conn)
            total_rows += rows

            next_int = int(current_expect) + 1
            if next_int > int(END_EXPECT):
                break
            next_expect = str(next_int).zfill(5)

            page = await browser.get_current_page()
            if page is None:
                break
            await page.goto(f"{BASE_URL}?expect={next_expect}")
            await asyncio.sleep(3)
            text = await page.evaluate("() => document.body.innerText")
            if len(text) < 300:
                print(f"\n  Reached end at {next_expect}")
                break
            current_expect = next_expect

    finally:
        await browser.kill()

    to_excel(conn)
    total = conn.execute("SELECT COUNT(*) FROM odds").fetchone()[0]
    expects = conn.execute("SELECT COUNT(DISTINCT expect) FROM odds").fetchone()[0]
    print(f"\n[Done] Total: {total} rows, {expects} expects")
    print(f"  SQLite: {DB_PATH}")
    print(f"  Excel:  {EXCEL_PATH}")
    conn.close()


if __name__ == "__main__":
    asyncio.run(main())
