"""
src/browser/manager.py
Manages the Playwright browser lifecycle and storage state persistence.
"""

import json
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
)

from src.utils.config import encrypt, decrypt
from src.utils.logger import get_logger

logger = get_logger("browser")


class BrowserManager:
    """
    Context manager that owns the Playwright browser and context.
    Supports encrypted storage_state persistence for session reuse.
    """

    def __init__(self, state_path: Optional[Path] = None, headless: bool = False):
        self.state_path = state_path
        self.headless = headless
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def __aenter__(self) -> "BrowserManager":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )

        storage_state = self._load_state()
        if storage_state:
            logger.info("Loading saved browser session state.")
            self._context = await self._browser.new_context(storage_state=storage_state)
        else:
            logger.info("No saved session — starting fresh browser context.")
            self._context = await self._browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            )

        return self

    async def __aexit__(self, *args):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def new_page(self) -> Page:
        return await self._context.new_page()

    async def save_state(self) -> None:
        """Encrypt and persist the current browser storage state."""
        if not self._context or not self.state_path:
            return
        state = await self._context.storage_state()
        state_json = json.dumps(state)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_bytes(encrypt(state_json))
        logger.info(f"Browser state saved to {self.state_path}")

    def _load_state(self) -> Optional[dict]:
        """Load and decrypt stored browser state."""
        if not self.state_path or not self.state_path.exists():
            return None
        try:
            decrypted = decrypt(self.state_path.read_bytes())
            return json.loads(decrypted)
        except Exception as e:
            logger.warning(f"Could not load browser state: {e}. Starting fresh.")
            return None

    def state_exists(self) -> bool:
        return self.state_path is not None and self.state_path.exists()
