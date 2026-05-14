"""Export 500.com cookies from Chrome profile."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from browser_use import BrowserSession

_CHROME_PATH = os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\User Data")
STORAGE_STATE_PATH = Path("500_com_storage_state.json")


async def main():
    profile_base = Path(_CHROME_PATH)
    print(f"Chrome profile: {profile_base} -> {'exists' if profile_base.exists() else 'NOT FOUND'}")
    if not profile_base.exists():
        return

    browser = BrowserSession(
        headless=False,
        user_data_dir=str(profile_base),
        profile_directory="Default",
    )
    await browser.start()

    try:
        page = await browser.get_current_page()
        if page is None:
            print("ERROR: no page")
            return

        await page.goto("https://zx.500.com/")
        await asyncio.sleep(5)

        text = await page.evaluate("() => document.body.innerText")
        if "登录" in text[:100] or "仅登录" in text:
            print("NOT logged in")
        else:
            print("Logged in!")

        state = await browser.export_storage_state(output_path=str(STORAGE_STATE_PATH))
        print(f"Exported to {STORAGE_STATE_PATH}")
        print(f"  Cookies: {len(state.get('cookies', []))}")
        for c in state.get('cookies', []):
            print(f"    {c.get('domain', '')} | {c.get('name', '')}")

    finally:
        await browser.kill()


if __name__ == "__main__":
    asyncio.run(main())
