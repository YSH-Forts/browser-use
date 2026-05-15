"""
500.com SFC Football Odds Scraper
================================

Uses browser-use (browser automation via CDP) to:
1. Open zx.500.com/zc/odds_sfc.php, close login popup, load match list
2. For each match, open its daxiao page and extract company odds data
3. Save results incrementally to JSONL, then SQLite + Excel

Run:
  uv run python run_500_com.py               # fresh start from 24001
  uv run python run_500_com.py --resume      # resume from last checkpoint
  uv run python run_500_com.py --limit=5    # limit to 5 periods
  uv run python run_500_com.py --post-process  # only run DB/Excel export
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any

from browser_use import Browser

logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s %(levelname)s %(message)s',
	stream=sys.stdout,
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
RAW_JSONL = Path('scrape_raw.jsonl')
DB_PATH = Path('football_odds.db')
EXCEL_PATH = Path('football_odds.xlsx')
STATE_FILE = Path('scrape_state.json')

# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------
def load_state() -> dict[str, Any]:
	if STATE_FILE.exists():
		return json.loads(STATE_FILE.read_text(encoding='utf-8'))
	return {
		'current_expect': None,
		'current_match_idx': 0,
		'processed_match_count': 0,
		'total_rows': 0,
		'started': False,
	}


def save_state(state: dict[str, Any]) -> None:
	STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
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


def import_jsonl(conn: sqlite3.Connection) -> int:
	if not RAW_JSONL.exists():
		log.info('No raw file: %s', RAW_JSONL)
		return 0
	count = 0
	with RAW_JSONL.open(encoding='utf-8') as f:
		for line in f:
			line = line.strip()
			if not line:
				continue
			row = json.loads(line)
			cols = list(row.keys())
			placeholders = ':' + ', :'.join(cols)
			try:
				conn.execute(
					f'INSERT OR REPLACE INTO odds ({", ".join(cols)}) VALUES ({placeholders})',
					row,
				)
				count += 1
			except Exception as e:
				log.warning('Insert error: %s', e)
	conn.commit()
	return count


def export_excel(conn: sqlite3.Connection) -> None:
	try:
		import openpyxl
	except ImportError:
		log.warning('openpyxl not available')
		return
	rows = conn.execute('SELECT * FROM odds ORDER BY expect, home_team, company').fetchall()
	if not rows:
		return
	desc = [d[0] for d in conn.execute('SELECT * FROM odds LIMIT 0').description]
	wb = openpyxl.Workbook()
	ws = wb.active
	ws.title = 'Odds'
	ws.append(desc)
	for row in rows:
		ws.append(list(row))
	wb.save(EXCEL_PATH)
	log.info('Excel: %d rows -> %s', len(rows), EXCEL_PATH)


def post_process() -> None:
	log.info('Post-processing: loading into SQLite and Excel...')
	conn = init_db()
	try:
		n = import_jsonl(conn)
		if n > 0:
			export_excel(conn)
			total = conn.execute('SELECT COUNT(*) FROM odds').fetchone()[0]
			expects = conn.execute('SELECT COUNT(DISTINCT expect) FROM odds').fetchone()[0]
			log.info('Rows: %d, Expects: %d', total, expects)
			log.info('SQLite: %s', DB_PATH)
			log.info('Excel:  %s', EXCEL_PATH)
		else:
			log.info('No new rows to import')
	finally:
		conn.close()


# ---------------------------------------------------------------------------
# CDP JS helpers
# ---------------------------------------------------------------------------

async def js_eval(browser: Browser, script: str) -> Any:
	"""Execute JS on current tab, reconnecting once on failure."""
	for attempt in range(2):
		try:
			target_id = browser.agent_focus_target_id
			if target_id is None:
				raise RuntimeError('No agent_focus_target_id')
			cdp = await browser.get_or_create_cdp_session(target_id, focus=True)
			result = await cdp.cdp_client.send.Runtime.evaluate(
				params={
					'expression': script,
					'returnByValue': True,
					'awaitPromise': True,
				},
				session_id=cdp.session_id,
			)
			exc = result.get('exceptionDetails')
			if exc:
				raise RuntimeError(f'JS Error: {exc.get("text", str(exc))}')
			val = result.get('result', {}).get('value')
			if isinstance(val, str):
				val = val.strip()
				if val.startswith(('{', '[')):
					return json.loads(val)
				raise RuntimeError(f'Non-JSON response: {val[:100]}')
			return val if val is not None else {}
		except (json.JSONDecodeError, RuntimeError) as e:
			err = str(e)
			if 'non-JSON' in err:
				raise
			if attempt < 1:
				log.warning('JS eval failed (attempt %d): %s', attempt + 1, err)
				await asyncio.sleep(1)
				continue
			raise

# JS to poll for daxiao page content (ck company rows)
MAIN_PAGE_JS = r"""
(function() {
	var matches = [];
	var allTables = document.querySelectorAll('table');
	for (var ti = 0; ti < allTables.length; ti++) {
		var tbl = allTables[ti];
		var rows = tbl.rows;
		for (var ri = 0; ri < rows.length; ri++) {
			var tr = rows[ri];
			var cells = tr.cells;
			if (cells.length < 3) continue;

			var daxiaoUrl = null;
			var links = tr.getElementsByTagName('a');
			for (var li = 0; li < links.length; li++) {
				var href = links[li].href || '';
				if (href.match(/daxiao/i)) {
					daxiaoUrl = href;
					break;
				}
			}
			if (!daxiaoUrl) continue;

			var txt = (tr.innerText || '').replace(/\s+/g, ' ').trim();
			if (!txt || txt.length < 5) continue;

			// Extract team names from FIRST CELL links only (cell[0] = match info cell)
			var teams = [];
			var firstCell = cells[0];
			var firstCellLinks = firstCell ? firstCell.getElementsByTagName('a') : [];
			for (var ki = 0; ki < firstCellLinks.length; ki++) {
				var lt = (firstCellLinks[ki].innerText || '').replace(/\s+/g, ' ').trim();
				// Skip nav links and non-team links
				if (!lt || lt.length < 2 || lt.length > 15) continue;
				if (/登录|注册|首页|帮助|分析|投注|大.*小|足球|篮球|胜负|竞彩/i.test(lt)) continue;
				if (/^[\d\-\s:：]+$/.test(lt)) continue;
				var isDup = false;
				for (var di = 0; di < teams.length; di++) {
					if (teams[di] === lt) { isDup = true; break; }
				}
				if (!isDup) teams.push(lt);
			}

			var timeMatch = txt.match(/(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2})/);
			var scoreMatch = txt.match(/(\d+)[\s:：-]+(\d+)/);
			var leagueMatch = txt.match(/([\u4e00-\u9fff]+(?:超|甲|乙|丙|冠|联|部|组))/);

			matches.push({
				teams: teams,
				daxiao_url: daxiaoUrl,
				time: timeMatch ? timeMatch[1].replace(/\//g, '-') : '',
				score: (scoreMatch && scoreMatch[0].length < 8) ? (scoreMatch[1] + ':' + scoreMatch[2]) : '',
				league: leagueMatch ? leagueMatch[1] : '',
			});
		}
	}
	return {matches: matches, count: matches.length};
})()
"""

# Extract odds from daxiao page
DAXIAO_DOM_JS = r"""
(function() {
	var state = {companies: [], error: null};
	try {
		// Extract teams from page body text (find pattern "A VS B" or "A - B")
		var bodyText = document.body.innerText || '';

		// Try to find team names - look for "VS" pattern in body
		var vsMatch = bodyText.match(/([\u4e00-\u9fff]{2,10})\s*(?:VS|vs|v[VS])\s*([\u4e00-\u9fff]{2,10})/);
		if (vsMatch) {
			state.home_team = vsMatch[1].trim();
			state.away_team = vsMatch[2].trim();
		}

		// Also try h1 title
		var h1 = document.querySelector('h1');
		var h1text = h1 ? (h1.innerText || '').replace(/\s+/g, ' ').trim() : '';
		var h1Parts = h1text.split(/VS/i);
		if (h1Parts.length >= 2) {
			state.home_team = h1Parts[0].replace(/[^\w\u4e00-\u9fff()（）\s]/g, '').trim();
			state.away_team = h1Parts[1].replace(/[^\w\u4e00-\u9fff()（）\s]/g, '').trim();
		}

		// Extract match time
		var timeMatch = bodyText.match(/(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2})/);
		state.match_time = timeMatch ? timeMatch[1].replace(/\//g, '-') : '';

		// Extract score
		var scoreMatch = bodyText.match(/(\d+)[\s:：-]+(\d+)/);
		if (scoreMatch && scoreMatch[0].length < 8) {
			state.score = scoreMatch[1] + ':' + scoreMatch[2];
		}

		// Extract league
		var leagueMatch = bodyText.match(/(\d{2}\/\d{2}[\u4e00-\u9fff]+(?:第?\d+轮)?)/);
		state.league = leagueMatch ? leagueMatch[1] : '';
		state.url = window.location.href;

		// Extract company odds from table rows
		var allRows = document.querySelectorAll('tr[id]');
		var companies = [];

		function strip(s) {
			// Remove arrow symbols (↑↓ etc.) and normalize whitespace
			s = (s || '').toString()
				.replace(/[\u2191\u2192\u2193\u2195\u25b2\u25bc\u23f4\u23f5\u23f8\u25c6\u25c7]/g, '')
				.replace(/\s+/g, ' ').trim();
			// Remove trailing row numbers (e.g. " 1", " 23", " 42")
			s = s.replace(/\s+\d{1,2}$/, '');
			return s;
		}

		function parseOdds(cellText) {
			// Cell format: over handicap under
			// Examples: "0.80 3.5 0.91", "0.94 3/3.5 0.85", "1.15 2.5 0.61"
			var s = strip(cellText);
			var parts = s.split(/\s+/);
			if (parts.length < 2) return {over: null, handicap: null, under: null};
			// First = over, last = under, middle = handicap
			var over = parseFloat(parts[0]) || null;
			var under = parseFloat(parts[parts.length - 1]) || null;
			var handicap = null;
			if (parts.length >= 3) {
				// Combine middle parts (could be "3/3.5" or "2.5")
				var mid = parts.slice(1, parts.length - 1);
				if (mid.length > 0) handicap = mid.join('/');
			}
			return {over: over, handicap: handicap, under: under};
		}

		for (var i = 0; i < allRows.length; i++) {
			var row = allRows[i];
			var rowId = row.id || '';
			// Company rows have input#ck<number> checkbox inside
			var checkbox = row.querySelector('input[id^="ck"]');
			if (!checkbox) continue;
			var ckId = checkbox.id || '';
			if (!ckId.match(/^ck\d+$/)) continue;

			var cells = row.cells;
			if (!cells || cells.length < 5) continue;

			// cells[0] = row number
			// cells[1] = company name
			// cells[2] = current odds cell: "over handicap under" (may have arrow chars)
			// cells[3] = current change time
			// cells[4] = initial odds cell: "over handicap under"
			// cells[5] = initial change time

			// Extract company name from cells[1]
			var companyName = '';
			var nameCell = cells[1];
			var anchor = nameCell.querySelector('a');
			if (anchor) {
				companyName = (anchor.title || anchor.innerText || '').replace(/\s+/g, ' ').trim();
			}
			if (!companyName) {
				// Strip HTML and get text
				var div = document.createElement('div');
				div.innerHTML = nameCell.innerHTML;
				companyName = (div.innerText || '').replace(/\s+/g, ' ').trim();
			}
			// Final fallback: scan all anchors in the row
			if (!companyName) {
				var anchors = row.querySelectorAll('a');
				for (var ai = 0; ai < anchors.length; ai++) {
					var txt = (anchors[ai].innerText || '').replace(/\s+/g, ' ').trim();
					// Company names are 2-20 Chinese/English chars
					if (txt && txt.length >= 2 && txt.length <= 20
						&& !txt.match(/^\d+$/)
						&& !txt.match(/大小|分析|投注|竞彩|足球|篮球/i)) {
						companyName = txt;
						break;
					}
				}
			}
			if (!companyName || companyName.length > 30 || companyName.length < 2) continue;

			// Parse current odds: cells[2] = "over handicap under"
			var cur = parseOdds(cells[2].innerText);
			var co = cur.over, ch = cur.handicap, cu = cur.under;

			// Parse initial odds: cells[4]
			var init = parseOdds(cells.length > 4 ? cells[4].innerText : '');
			var io = init.over, ih = init.handicap, iu = init.under;

			// Skip if no useful odds
			if (co === null && io === null) continue;

			companies.push({
				company: companyName,
				current_over_odds: co,
				current_handicap: ch || '',
				current_under_odds: cu,
				initial_over_odds: io,
				initial_handicap: ih || '',
				initial_under_odds: iu,
			});
		}

		state.companies = companies;
		state.company_count = companies.length;
	} catch(e) {
		state.error = e.message;
	}
	return state;
})()
"""

# JS to poll for daxiao page content (ck company rows)
PAGE_CONTENT_JS = r"""
(function() {
	var rows = document.querySelectorAll('tr[id]');
	var ckCount = 0;
	for (var i = 0; i < rows.length; i++) {
		if (rows[i].querySelector('input[id^="ck"]')) ckCount++;
	}
	return {ckCount: ckCount, trTotal: rows.length};
})()
"""


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

class Scraper:
	MAIN_URL = 'https://zx.500.com/zc/odds_sfc.php'
	PAGE_LOAD_TIMEOUT = 25

	def __init__(self, start_expect: str = '24001', max_periods: int | None = None):
		self.start_expect = start_expect
		self.max_periods = max_periods

	async def _close_tips_popup(self, browser: Browser) -> bool:
		"""Attempt to close the login tips popup."""
		try:
			script = r"""
(function() {
	var btn = document.querySelector('.tips_close, #tips_close, [class*="tips-close"], .j-close');
	if (btn) { btn.click(); return true; }
	var overlay = document.querySelector('.tips-wrap, .tips-box, .tips-overlay');
	if (overlay) {
		var children = overlay.querySelectorAll('a, button, [class*="close"]');
		for (var i = 0; i < children.length; i++) {
			var c = children[i];
			var txt = (c.innerText || '').replace(/\s+/g, '').trim();
			if (txt === '关闭' || txt === '×' || txt === 'X') {
				c.click();
				return true;
			}
		}
	}
	return false;
})()"""
			result = await js_eval(browser, script)
			return bool(result)
		except Exception as e:
			log.debug('Tips close attempt: %s', e)
			return False

	async def _ensure_page_ready(self, browser: Browser) -> bool:
		"""Wait for page dynamic content to load. Returns True if content is ready."""
		deadline = asyncio.get_event_loop().time() + self.PAGE_LOAD_TIMEOUT

		# First wait a bit for initial render
		await asyncio.sleep(1)

		while asyncio.get_event_loop().time() < deadline:
			# Try to close tips popup
			await self._close_tips_popup(browser)

			# Check if content is loaded
			data = await js_eval(browser, PAGE_CONTENT_JS)
			if isinstance(data, dict):
				ck_count = data.get('ckCount', 0)
				tr_total = data.get('trTotal', 0)
				if tr_total > 5:
					log.info('Page ready: %d tr rows, %d company rows', tr_total, ck_count)
					return True

			await asyncio.sleep(2)

		log.warning('Page content not ready within %ds', self.PAGE_LOAD_TIMEOUT)
		return False

	async def run(self) -> dict[str, Any]:
		state = load_state()
		current_expect = state.get('current_expect') or self.start_expect
		current_match_idx = state.get('current_match_idx', 0)
		total_rows = state.get('total_rows', 0)
		processed_matches = state.get('processed_match_count', 0)

		log.info('=' * 60)
		log.info('500.com Scraper — starting from expect=%s match_idx=%d', current_expect, current_match_idx)
		log.info('State: matches=%d, rows=%d', processed_matches, total_rows)
		log.info('=' * 60)

		browser = Browser(headless=False)
		await browser.start()
		log.info('[Browser] Started')

		for _ in range(30):
			if browser.agent_focus_target_id is not None:
				break
			await asyncio.sleep(0.3)
		else:
			raise RuntimeError('agent_focus_target_id never set')

		log.info('[Focus] %s...', browser.agent_focus_target_id[:16])

		state['started'] = True
		save_state(state)

		expect_num = int(current_expect)
		period_count = 0
		nav_errors = 0
		match_idx = current_match_idx

		while expect_num <= 99999:
			expect_str = f'{expect_num:05d}'
			log.info('')
			log.info('[%d] Expect=%s', period_count + 1, expect_str)

			url = f'{self.MAIN_URL}?expect={expect_str}'
			try:
				await browser.navigate_to(url)
				ready = await self._ensure_page_ready(browser)
			except Exception as e:
				nav_errors += 1
				log.warning('Nav to SFC page failed: %s', e)
				if nav_errors >= 3:
					log.error('Too many nav errors, stopping.')
					break
				await asyncio.sleep(5)
				continue

			nav_errors = 0

			# Close tips popup one more time
			await self._close_tips_popup(browser)

			# Extract match list
			try:
				main_data = await js_eval(browser, MAIN_PAGE_JS)
			except Exception as e:
				log.warning('JS extraction from SFC page failed: %s', e)
				main_data = {'matches': [], 'count': 0}

			matches = main_data.get('matches', [])
			if not matches:
				log.info('  No matches found. End of data.')
				break

			log.info('  Found %d matches', len(matches))

			start_idx = match_idx if expect_str == current_expect else 0

			for idx in range(start_idx, len(matches)):
				match = matches[idx]
				processed_matches += 1
				daxiao_url = match.get('daxiao_url', '')
				if not daxiao_url:
					continue

				teams = match.get('teams', [])
				home = teams[0] if len(teams) > 0 else ''
				away = teams[1] if len(teams) > 1 else ''

				log.info('  M%d/%d: %s vs %s', idx + 1, len(matches), home or '?', away or '?')

				# Navigate to daxiao page
				try:
					await browser.navigate_to(daxiao_url)
					ready = await self._ensure_page_ready(browser)
					if not ready:
						log.warning('    Daxiao page not ready, trying anyway...')
				except Exception as e:
					log.warning('    Nav to daxiao failed: %s', e)
					self._save_checkpoint(state, expect_str, idx + 1, processed_matches, total_rows)
					continue

				# Extract odds
				daxiao_data = {'companies': []}
				try:
					daxiao_data = await js_eval(browser, DAXIAO_DOM_JS)
					companies = daxiao_data.get('companies', [])
					if companies:
						log.info('    Extracted %d company odds', len(companies))
					else:
						log.info('    No companies extracted (error: %s)', daxiao_data.get('error', ''))
				except Exception as e:
					log.warning('    DOM extraction failed: %s', e)

				# Write rows
				rows_written = 0
				for company in companies:
					row = {
						'expect': expect_str,
						'league': daxiao_data.get('league', match.get('league', '')),
						'match_time': daxiao_data.get('match_time', match.get('time', '')),
						'home_team': daxiao_data.get('home_team', home),
						'away_team': daxiao_data.get('away_team', away),
						'score': daxiao_data.get('score', match.get('score', '')),
						'company': company.get('company', ''),
						'current_handicap': str(company.get('current_handicap', '') or ''),
						'over_odds': company.get('current_over_odds'),
						'under_odds': company.get('current_under_odds'),
						'initial_handicap': str(company.get('initial_handicap', '') or ''),
						'over_initial_odds': company.get('initial_over_odds'),
						'under_initial_odds': company.get('initial_under_odds'),
						'source_url': daxiao_data.get('url', daxiao_url),
					}
					with RAW_JSONL.open('a', encoding='utf-8') as f:
						f.write(json.dumps(row, ensure_ascii=False) + '\n')
					rows_written += 1
					total_rows += 1

				self._save_checkpoint(state, expect_str, idx + 1, processed_matches, total_rows)

				if rows_written > 0:
					log.info('    Wrote %d rows (total: %d)', rows_written, total_rows)

				await asyncio.sleep(0.5)

			match_idx = 0
			self._save_checkpoint(state, expect_str, 0, processed_matches, total_rows)

			# Periodic flush to DB/Excel every 10 periods
			if period_count > 0 and period_count % 10 == 0:
				log.info('Periodic flush to DB/Excel...')
				post_process()

			period_count += 1
			expect_num += 1

			max_periods = self.max_periods if self.max_periods is not None else 500
			if period_count >= max_periods:
				log.info('Max periods (%d) reached.', max_periods)
				break

		log.info('')
		log.info('=' * 60)
		log.info('Done! Periods: %d, Matches: %d, Rows: %d', period_count, processed_matches, total_rows)
		log.info('=' * 60)

		await browser.close()
		return {'periods': period_count, 'total_rows': total_rows, 'processed_matches': processed_matches}

	def _save_checkpoint(self, state: dict, expect: str, match_idx: int, matches: int, rows: int) -> None:
		state['current_expect'] = expect
		state['current_match_idx'] = match_idx
		state['processed_match_count'] = matches
		state['total_rows'] = rows
		save_state(state)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def main():
	resume = '--resume' in sys.argv
	post_only = '--post-process' in sys.argv

	# Allow limiting number of periods
	limit_arg = None
	for arg in sys.argv:
		if arg.startswith('--limit='):
			try:
				limit_arg = int(arg.split('=', 1)[1])
			except ValueError:
				pass

	if post_only:
		post_process()
		return

	if resume:
		state = load_state()
		start = state.get('current_expect', '24001')
		log.info('Resuming from expect=%s', start)
	else:
		if STATE_FILE.exists():
			STATE_FILE.unlink()
		if RAW_JSONL.exists():
			RAW_JSONL.unlink()
		start = '24001'
		log.info('Fresh start from 24001')

	scraper = Scraper(start_expect=start, max_periods=limit_arg)
	result = await scraper.run()
	log.info('Result: %s', result)

	post_process()


if __name__ == '__main__':
	asyncio.run(main())
