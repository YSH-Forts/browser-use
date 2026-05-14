"""
Browser-use Agent script to:
1. Navigate to 500.com and log in if needed
2. Export the storage state with authenticated cookies
3. Take a screenshot of the logged-in state
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from browser_use import Agent, BrowserSession
from browser_use.llm.deepseek.chat import ChatDeepSeek
from dotenv import load_dotenv


STORAGE_PATH = Path("500_auth_state.json")
SCREENSHOT_PATH = Path("500_logged_in.png")


async def main():
    load_dotenv()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: Set DEEPSEEK_API_KEY in .env")
        return

    llm = ChatDeepSeek(
        model="deepseek-chat",
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )
    browser = BrowserSession(headless=False)

    try:
        agent = Agent(
            task="""请完成以下步骤：

1. 打开 https://zx.500.com/zc/odds_sfc.php?expect=24001
2. 检查页面是否显示登录墙（文字包含"仅登录"、"登录/注册"、或输入框含"用户名"）
3. 如果显示登录墙：
   a. 在当前页面找到登录入口并点击
   b. 如果需要跳转到登录页，在登录页填入用户名和密码（从环境变量 LOGIN_500_USERNAME 和 LOGIN_500_PASSWORD 读取）
   c. 如果没有这些环境变量，尝试使用已保存的浏览器cookie登录
   d. 如果登录成功，回到 https://zx.500.com/zc/odds_sfc.php?expect=24001
4. 如果没有登录墙（页面显示了比赛列表、期号等内容），说明已登录
5. 完成后：
   a. 对当前页面截图保存到 500_logged_in.png
   b. 将浏览器cookie和localStorage导出为JSON格式（使用截图后提取当前页面的cookie信息），写入文件 500_auth_state.json
   c. 文件格式为Playwright storage_state格式：
      {"cookies": [...], "origins": [...]}
   d. 打印"登录验证完成"

请用截图来确认登录状态，不要假设。""",
            llm=llm,
            browser=browser,
            max_steps=20,
            step_timeout=60,
        )
        print("Agent starting...")
        history = await agent.run()
        print(f"Agent done. URLs: {len(history.urls())}")
        print(f"Final result: {history.final_result()}")

    finally:
        await browser.kill()


if __name__ == "__main__":
    asyncio.run(main())
