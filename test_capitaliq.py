from browser_use import Agent, Browser
from browser_use.llm.deepseek.chat import ChatDeepSeek
from dotenv import load_dotenv
import asyncio
import os

load_dotenv()


async def main():
	llm = ChatDeepSeek(
		model='deepseek-chat',
		api_key=os.getenv('DEEPSEEK_API_KEY'),
		base_url='https://api.deepseek.com',
	)

	browser = Browser(
		headless=False,
		minimum_wait_page_load_time=2.0,
		user_data_dir=os.path.expandvars('%LOCALAPPDATA%\\Google\\Chrome\\User Data'),
		profile_directory='Default',
	)

	task = """
1. Navigate to https://www.capitaliq.com/CIQDotNet/my/dashboard.aspx
2. Wait 5 seconds for the page to fully load
3. Enter the email/username field with: meijun.sun@bowayalloy.com
4. Click the Next or Continue or Submit button to proceed
5. Wait 5 seconds for the password page to load
6. Enter the password field with: Bowayalloy$2025
7. Click the Sign In or Login button
8. Wait 15 seconds for the login to process
9. If a Terms of Use page appears:
   - Wait 3 seconds for the page to render
   - Use evaluate JavaScript to click the checkbox: document.getElementById('_chkIAgree').click()
   - Wait 2 seconds
   - Use evaluate JavaScript to click the accept button: document.getElementById('btnAccept').click()
   - Wait 5 seconds
10. Report the current page URL and title after login

After successful login:
11. Look for a "Screening" menu item in the top navigation bar and click it
12. In the dropdown/submenu that appears, look for "Saved Screens" and click it
13. Wait 5 seconds for the saved screens page to load
14. Find and click the saved screen named "主要经济体上市公司投资 23.1-8"
15. Wait 8 seconds for the screen to open

16. IMPORTANT: On the screening results page, look for an "Export" section with an Excel option and a "Go" button next to it. Click the "Go" button (NOT the excelReport link which triggers background generation).
17. After clicking "Go", a NEW WINDOW will open. Check for this new window/tab.
18. If a new window opened, SWITCH to that new window/tab.
19. Maximize the new window if not already maximized.
20. Look for a "Download" button in the new window and click it to initiate the Excel download.
21. Wait 10 seconds for the download to complete.
22. Report success: confirm the download was initiated, report the new window URL, and list any downloaded files.
"""

	agent = Agent(
		task=task,
		llm=llm,
		browser=browser,
		step_timeout=180,
		save_conversation_path='./logs/conversations',
	)
	history = await agent.run()
	print('\n=== FINAL RESULT ===')
	print('Final URL:', history.urls()[-1] if history.urls() else 'none')
	print('Final result:', history.final_result())
	print('Total steps:', history.number_of_steps())


if __name__ == '__main__':
	asyncio.run(main())
