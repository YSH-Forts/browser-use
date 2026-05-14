"""
Browser-use script to scrape football odds from 500.com SFC pages.
Run: python run_500_com.py

Strategy: The browser agent extracts data via evaluate() JS and writes each
match+company row to a JSON Lines file (append mode). A separate Python
post-processor loads all lines into SQLite and exports to Excel.

Environment:
  DEEPSEEK_API_KEY in .env
  openpyxl for Excel export
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

from browser_use import Agent, Browser
from browser_use.llm.deepseek.chat import ChatDeepSeek

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
RAW_JSONL = Path("scrape_raw.jsonl")
DB_PATH = Path("football_odds.db")
EXCEL_PATH = Path("football_odds.xlsx")

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
COLUMNS = [
    "expect", "league", "match_time", "home_team", "away_team", "score",
    "company", "current_handicap", "over_odds", "under_odds",
    "initial_handicap", "over_initial_odds", "under_initial_odds",
    "source_url",
]


def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f"""
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


def import_jsonl(conn: sqlite3.Connection):
    """Load all rows from the JSON Lines file into SQLite."""
    if not RAW_JSONL.exists():
        print(f"  No raw file found: {RAW_JSONL}")
        return 0

    count = 0
    with RAW_JSONL.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            cols = list(row.keys())
            placeholders = ":" + ", :".join(cols)
            try:
                conn.execute(
                    f"INSERT OR REPLACE INTO odds ({', '.join(cols)}) "
                    f"VALUES ({placeholders})",
                    row,
                )
                count += 1
            except Exception as e:
                print(f"  [WARN] Failed to insert row: {e}")
    conn.commit()
    print(f"  Imported {count} rows into SQLite")
    return count


def export_excel(conn: sqlite3.Connection):
    try:
        import openpyxl
    except ImportError:
        print("  openpyxl not available, skipping Excel")
        return

    rows = conn.execute(
        "SELECT * FROM odds ORDER BY expect, home_team, company"
    ).fetchall()
    if not rows:
        return

    cols = [
        desc[0] for desc in
        conn.execute("SELECT * FROM odds LIMIT 0").description
    ]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Odds"
    ws.append(cols)
    for row in rows:
        ws.append(list(row))
    wb.save(EXCEL_PATH)
    print(f"  Excel: {len(rows)} rows -> {EXCEL_PATH}")


def post_process():
    """Called after the agent finishes to consolidate data."""
    print("\n[Post-processing] Loading data into SQLite and Excel...")
    conn = init_db()
    try:
        n = import_jsonl(conn)
        if n > 0:
            export_excel(conn)
            total = conn.execute("SELECT COUNT(*) FROM odds").fetchone()[0]
            expects = conn.execute(
                "SELECT COUNT(DISTINCT expect) FROM odds"
            ).fetchone()[0]
            print(f"\n[Done] Total rows: {total}, Total expects: {expects}")
            print(f"  SQLite: {DB_PATH}")
            print(f"  Excel:  {EXCEL_PATH}")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Task description for the browser agent
# ---------------------------------------------------------------------------
TASK = """从500.com足彩页面抓取足球赔率数据，提取到JSON文件。

## 目标
https://zx.500.com/zc/odds_sfc.php?expect=24001
从24001期开始，每期14场比赛，遍历所有期号。

## 数据格式
每场比赛的每个公司算一行，JSON格式，追加写入文件 scrape_raw.jsonl：
{"expect":"24001","league":"英超","match_time":"2024-01-02 04:00:00","home_team":"利物浦","away_team":"纽卡斯","score":"4:2","company":"威廉","current_handicap":"球半","over_odds":0.95,"under_odds":0.85,"initial_handicap":"球半","over_initial_odds":0.90,"under_initial_odds":0.80,"source_url":"https://odds.500.com/fenxi/daxiao-1092884.shtml"}

## 操作步骤

1. 打开 https://zx.500.com/zc/odds_sfc.php?expect=24001
   等待3秒让页面完全加载。

2. 在主页面：
   向下滚动，识别全部14场比赛。
   每场比赛：
   a. 从页面可见文字提取：联赛、时间、主队、客队、比分。
   b. 找到该场比赛行中的"大小对比"链接（href含"daxiao"），点击它，新tab打开。
   c. 在大小球页面提取各公司的盘口和赔率数据。
   d. 将每公司一行数据追加写入文件 scrape_raw.jsonl（使用write_file action，append=true）。
   e. 关闭该tab，回到主tab，继续下一场。

3. 当期全部14场完成后：
   点击"期指数对比"下拉框，选择下一个期号（如24002）。
   重复第2步。
   如果下拉框没有更多选项了，停止。

4. 所有期号采集完成后报告：总期数、总行数。

## 重要规则
- 提取数据必须用 evaluate() JavaScript，在控制台执行document.body.innerText或DOM查询获取文字。
- 用write_file写入scrape_raw.jsonl，必须设置append=true追加模式，每次写入1行JSON。
- 每次提取到数据后立即写入文件，不要等到最后。
- 如果某个公司没有数据，字段留空字符串（不要省略key）。
- 如果页面出现验证码，停止并报告。
- 每完成5行数据在日志里打印一次进度。"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def main():
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: Set DEEPSEEK_API_KEY in .env")
        sys.exit(1)

    llm = ChatDeepSeek(
        model="deepseek-chat",
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )
    browser = Browser(headless=False)

    try:
        agent = Agent(
            task=TASK,
            llm=llm,
            browser=browser,
            max_steps=500,
            step_timeout=120,
            save_conversation_path="./logs/500_com",
        )
        print("Agent starting (browser will open)...")
        history = await agent.run()
        print(f"\nAgent finished. URLs: {len(history.urls())}")
        print(f"Final result: {history.final_result()}")
    finally:
        await browser.close()

    post_process()


if __name__ == "__main__":
    asyncio.run(main())
