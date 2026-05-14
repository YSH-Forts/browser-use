"""
CapitalIQ Saved Screen Excel Downloader

Usage:
    python download_ciq.py "Screen Name" "download_dir"

Prerequisites:
    - Chrome already logged into CapitalIQ (script reuses Chrome profile)
    - DEEPSEEK_API_KEY set in .env
"""
from browser_use import Agent, Browser
from browser_use.llm.deepseek.chat import ChatDeepSeek
from dotenv import load_dotenv
import asyncio
import glob
import os
import shutil
import tempfile
import time

load_dotenv()


# CapitalIQ credentials (auto-loaded from environment)
CAPITALIQ_USERNAME = os.getenv('CAPITALIQ_USERNAME', 'meijun.sun@bowayalloy.com')
CAPITALIQ_PASSWORD = os.getenv('CAPITALIQ_PASSWORD', 'Bowayalloy$2025')


def build_task(screen_names: list[str]) -> str:
	"""Build the agent task description for CIQ download."""
	screens_text = '\n'.join(f'{i+1}. {name}' for i, name in enumerate(screen_names))
	return f"""Download Excel reports from CapitalIQ Saved Screens.

For EACH saved screen listed below, complete ALL steps in order before moving to the next one:

{screens_text}

Workflow for each screen:
1. Click "Screening" in the top navigation bar
2. Click "Saved Screens" in the dropdown/submenu
3. Wait 5 seconds for the saved screens page to load
4. Find and click the saved screen by its exact name
5. Wait 8 seconds for the screening results to load (URL changes to ScreenResults.aspx)
6. On the results page, find the Export section on the right side
7. Ensure "Excel" option is selected (click Excel if not already selected)
8. Click the "Go" button next to the Excel option (DO NOT click excelReport link)
9. A NEW WINDOW will open automatically showing Monitor.aspx
10. SWITCH to the new window/tab (use the switch action with tab index)
11. If the window is not maximized, click the maximize button
12. Wait for the report to generate:
    - The page shows "Generating Report(s)" initially
    - Refresh the page every 5 seconds if needed
    - Look for the "Recently Completed Reports" section to appear
13. Once the report appears in "Recently Completed Reports", click the "Download" button for it
14. Wait 5 seconds for the download to complete
15. Report the downloaded file path

After ALL screens are downloaded, report the complete list of downloaded files with their paths.

IMPORTANT RULES:
- Always switch to the new window after clicking Go — the download starts there
- If Monitor.aspx shows "Generating", refresh the page every 5 seconds (up to 60 seconds total)
- The Download button is inside the Monitor.aspx "Recently Completed Reports" section
- Do NOT click the excelReport link — it queues a background job, not immediate download
"""


async def download_screens(screen_names: list[str], download_dir: str) -> list[str]:
	"""Run the browser agent to download screens and return list of downloaded files."""
	os.makedirs(download_dir, exist_ok=True)

	llm = ChatDeepSeek(
		model='deepseek-chat',
		api_key=os.getenv('DEEPSEEK_API_KEY'),
		base_url='https://api.deepseek.com',
	)

	# Create a temp dir for this session's downloads
	session_id = int(time.time())
	download_path = os.path.join(download_dir, f'ciq_session_{session_id}')
	os.makedirs(download_path, exist_ok=True)

	browser = Browser(
		headless=False,
		minimum_wait_page_load_time=2.0,
		accept_downloads=True,
		downloads_path=download_path,
	)

	task = build_task(screen_names)

	agent = Agent(
		task=task,
		llm=llm,
		browser=browser,
		step_timeout=180,
		save_conversation_path='./logs/conversations',
	)

	print(f'  Starting download for {len(screen_names)} screen(s)...')
	history = await agent.run()
	print(f'  Agent completed in {history.number_of_steps()} steps')

	# Collect downloaded files
	downloaded = []
	for pattern in [download_path, os.environ.get('TEMP', '')]:
		base = pattern
		if base == os.environ.get('TEMP', ''):
			base = os.path.join(base, 'browser-use-downloads-*')
			for td in glob.glob(base):
				for fname in os.listdir(td):
					if fname.endswith(('.xls', '.xlsx')):
						src = os.path.join(td, fname)
						dst = os.path.join(download_path, fname)
						if not os.path.exists(dst):
							shutil.copy2(src, dst)
						downloaded.append(dst)
		else:
			for fname in os.listdir(pattern):
				if fname.endswith(('.xls', '.xlsx')) and os.path.isfile(os.path.join(pattern, fname)):
					downloaded.append(os.path.join(pattern, fname))

	return downloaded


async def main():
	import sys

	if len(sys.argv) < 3:
		print('Usage: python download_ciq.py "Screen Name 1" "Screen Name 2" ... "download_dir"')
		print('Example: python download_ciq.py "主要经济体上市公司投资 23.1-8" "D:\\CapitalIQ_Downloads"')
		sys.exit(1)

	download_dir = sys.argv[-1]
	screen_names = sys.argv[1:-1]

	if not os.getenv('DEEPSEEK_API_KEY'):
		print('Error: DEEPSEEK_API_KEY not set in .env')
		sys.exit(1)

	print(f'\n=== CIQ Download ===')
	print(f'Screens: {screen_names}')
	print(f'Download dir: {download_dir}')
	print()

	downloaded = await download_screens(screen_names, download_dir)

	print(f'\n=== COMPLETE ===')
	print(f'Downloaded {len(downloaded)} file(s):')
	for path in downloaded:
		size = os.path.getsize(path) / 1024 / 1024
		print(f'  {path} ({size:.1f} MB)')


if __name__ == '__main__':
	asyncio.run(main())
