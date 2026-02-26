"""
src/browser/actions.py
Human-like browser interaction primitives.
All waits and delays are randomized to reduce bot detection.
"""

import asyncio
import random
from typing import Optional

from playwright.async_api import Page, Locator

from src.utils.config import (
    TYPING_DELAY_MIN,
    TYPING_DELAY_MAX,
    ACTION_DELAY_MIN,
    ACTION_DELAY_MAX,
    PAGE_LOAD_WAIT,
)
from src.utils.logger import get_logger

logger = get_logger("browser.actions")


async def human_delay(min_s: float = ACTION_DELAY_MIN, max_s: float = ACTION_DELAY_MAX) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))


async def human_type(locator: Locator, text: str) -> None:
    """Type text with random per-character delay."""
    await locator.click()
    await locator.fill("")  # clear first
    for char in text:
        await locator.type(char)
        await asyncio.sleep(random.uniform(TYPING_DELAY_MIN, TYPING_DELAY_MAX))


async def safe_click(locator: Locator) -> None:
    await human_delay(0.3, 0.8)
    await locator.scroll_into_view_if_needed()
    await locator.click()


async def wait_for_page_load(page: Page, timeout: float = PAGE_LOAD_WAIT) -> None:
    await page.wait_for_load_state("domcontentloaded")
    await asyncio.sleep(timeout)


async def navigate(page: Page, url: str) -> None:
    logger.debug(f"Navigating to: {url}")
    await page.goto(url, wait_until="domcontentloaded")
    await wait_for_page_load(page)


async def scroll_to_bottom(page: Page, steps: int = 5) -> None:
    """Gradually scroll to the bottom of the page."""
    for _ in range(steps):
        await page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
        await human_delay(0.4, 0.9)


async def fill_text_field(page: Page, selector: str, text: str) -> bool:
    """Locate and fill a text input. Returns True if successful."""
    try:
        locator = page.locator(selector).first
        await locator.wait_for(state="visible", timeout=5000)
        await human_type(locator, text)
        return True
    except Exception as e:
        logger.debug(f"fill_text_field failed for '{selector}': {e}")
        return False


async def select_radio(page: Page, name: str, value: str) -> bool:
    """Click a radio button matching name+value."""
    try:
        locator = page.locator(f"input[type='radio'][name='{name}'][value='{value}']").first
        await safe_click(locator)
        return True
    except Exception as e:
        logger.debug(f"select_radio failed name={name} value={value}: {e}")
        return False


async def select_dropdown(page: Page, selector: str, value: str) -> bool:
    """Select a dropdown option by visible text or value."""
    try:
        locator = page.locator(selector).first
        await locator.wait_for(state="visible", timeout=5000)
        await locator.select_option(label=value)
        return True
    except Exception:
        try:
            await page.locator(selector).first.select_option(value=value)
            return True
        except Exception as e:
            logger.debug(f"select_dropdown failed '{selector}': {e}")
            return False


async def check_checkbox(page: Page, selector: str) -> bool:
    try:
        cb = page.locator(selector).first
        if not await cb.is_checked():
            await safe_click(cb)
        return True
    except Exception as e:
        logger.debug(f"check_checkbox failed '{selector}': {e}")
        return False
