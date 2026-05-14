from browser_use import Agent, Browser
from browser_use.llm.deepseek.chat import ChatDeepSeek
from dotenv import load_dotenv
import asyncio
import os

load_dotenv()


def build_login_task():
	username = os.getenv('CAPITALIQ_USERNAME', '')
	password = os.getenv('CAPITALIQ_PASSWORD', '')

	step1 = f'1. Navigate to https://www.capitaliq.com/CIQDotNet/my/dashboard.aspx'
	step2 = '2. Wait 5 seconds for the Okta login page to fully load'
	step3 = f'3. Enter the email/username field with: {username}'
	step4 = '4. Click the Next or Continue button'
	step5 = '5. Wait 5 seconds for the password page to load'
	step6 = f'6. Enter the password field with: {password}'
	step7 = '7. Click the Sign In button'
	step8 = '8. Wait 10 seconds for the page to process login'
	step9 = (
		'9. If redirected to Terms of Use page:\n'
		'   - Wait 3 seconds for the page to render\n'
		'   - Use evaluate JavaScript to check the checkbox:\n'
		'     document.getElementById(\'_chkIAgree\').click()\n'
		'   - Wait 2 seconds\n'
		'   - Use evaluate JavaScript to click the submit button:\n'
		'     document.getElementById(\'btnAccept\').click()'
	)
	step10 = '10. Wait 5 seconds and report the current page URL and title'

	return '\n'.join([step1, step2, step3, step4, step5, step6, step7, step8, step9, step10])


async def main():
	llm = ChatDeepSeek(
		model='deepseek-chat',
		api_key=os.getenv('DEEPSEEK_API_KEY'),
		base_url='https://api.deepseek.com',
	)

	browser = Browser(
		headless=False,
		minimum_wait_page_load_time=2.0,
	)

	async def on_step(browser_state_summary, model_output, step):
		"""Print full model input/output for each step."""
		print(f'\n{"=" * 80}')
		print(f'  STEP {step} - MODEL INPUT/OUTPUT')
		print('=' * 80)
		if model_output.thinking:
			print(f'\n[THINKING]\n{model_output.thinking}\n')
		if model_output.evaluation_previous_goal:
			print(f'[EVALUATION] {model_output.evaluation_previous_goal}')
		if model_output.memory:
			print(f'[MEMORY] {model_output.memory}')
		if model_output.next_goal:
			print(f'[NEXT GOAL] {model_output.next_goal}')
		if model_output.action:
			for i, act in enumerate(model_output.action):
				act_data = act.model_dump(exclude_unset=True)
				print(f'[ACTION {i + 1}] {act_data}')
		print('=' * 80 + '\n')

	agent = Agent(
		task=build_login_task(),
		llm=llm,
		browser=browser,
		step_timeout=180,
		register_new_step_callback=on_step,
		save_conversation_path='./logs/conversations',
	)
	history = await agent.run()
	print('\nFinal URL:', history.urls()[-1] if history.urls() else 'none')
	print('Final result:', history.final_result())


if __name__ == '__main__':
	asyncio.run(main())
