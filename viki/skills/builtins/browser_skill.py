import asyncio
from typing import Dict, Any, Optional
from playwright.async_api import async_playwright
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger

class BrowserSkill(BaseSkill):
    """
    Advanced Browser Automation Skill using Playwright.
    Enables VIKI to navigate, click, and interact with live web pages.
    """
    def __init__(self):
        self._name = "browser"
        self._description = (
            "Automate a web browser. Actions: navigate, click, type, screenshot, evaluate.\n"
            "Usage: browser(action='navigate', url='google.com')\n"
            "Actions: click(selector), type(selector, text), screenshot()"
        )
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    async def _init_browser(self, headless=True):
        if not self.playwright:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=headless)
            self.context = await self.browser.new_context()
            self.page = await self.context.new_page()

    async def execute(self, params: Dict[str, Any]) -> str:
        # ABSOLUTE HEADLESS ENFORCEMENT
        # We ignore any 'headless' param from LLM to respect user wish
        action = params.get("action", "navigate")
        await self._init_browser(headless=True)

        try:
            if action == "navigate":
                url = params.get("url")
                if not url or not str(url).strip():
                    return "Provide url= for navigate action."
                url = str(url).strip()
                if not url.startswith("http"):
                    url = "https://" + url
                await self.page.goto(url)
                title = await self.page.title()
                return f"Navigated to {url}. Title: {title}"
                
            elif action == "click":
                selector = params.get("selector")
                await self.page.click(selector)
                return f"Clicked element: {selector}"
                
            elif action == "type":
                selector = params.get("selector")
                text = params.get("text")
                await self.page.fill(selector, text)
                return f"Typed '{text}' into {selector}"
                
            elif action == "screenshot":
                path = "data/browser_screenshot.png"
                await self.page.screenshot(path=path)
                return f"Browser screenshot saved to {path}"
            
            elif action == "content":
                content = await self.page.content()
                return f"Page content captured (truncated): {content[:2000]}..."

            return f"Error: Unknown browser action '{action}'"

        except Exception as e:
            viki_logger.error(f"Browser action failed: {e}")
            return f"Browser Error: {str(e)}"
        finally:
            if self.browser:
                try:
                    await self.browser.close()
                except Exception as e:
                    viki_logger.debug(f"Browser close: {e}")
                self.browser = None
                self.context = None
                self.page = None
            if self.playwright:
                try:
                    await self.playwright.stop()
                except Exception as e:
                    viki_logger.debug(f"Playwright stop: {e}")
                self.playwright = None

    async def shutdown(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
