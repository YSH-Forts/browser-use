"""Save the main SFC page HTML for debugging."""
from pathlib import Path
from browser_use import BrowserSession
import asyncio

async def main():
    browser = BrowserSession(headless=False)
    await browser.start()
    try:
        page = await browser.get_current_page()
        if page is None:
            print("ERROR: No page")
            return

        await page.goto("https://zx.500.com/zc/odds_sfc.php?expect=24001")
        await asyncio.sleep(5)

        html = await page.evaluate("() => document.documentElement.outerHTML")
        Path("debug_main.html").write_bytes(html.encode("utf-8", errors="replace"))
        print(f"Saved {len(html)} bytes to debug_main.html")

        # Also look for specific patterns
        text = await page.evaluate("() => document.body.innerText")
        print(f"Page text length: {len(text)}")
        print("First 500 chars:", text[:500])
    finally:
        await browser.kill()

asyncio.run(main())
