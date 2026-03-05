"""
src/platforms/naukri/__init__.py
Naukri platform implementation.
"""

import json
from pathlib import Path
from playwright.async_api import Page

from src.platforms.base import BasePlatform
from src.platforms.naukri.scraper import scrape_jobs, construct_naukri_url
from src.platforms.naukri.applier import apply_to_job
from src.utils.config import CONFIGS_DIR, encrypt
from src.utils.logger import get_logger

logger = get_logger("naukri")

STATE_PATH = CONFIGS_DIR / "naukri_state.enc"


class NaukriPlatform(BasePlatform):

    async def login(self, page: Page) -> None:
        """Manual login + encrypted session persistence."""
        if STATE_PATH.exists():
            logger.info("Naukri: using saved session. Skipping login.")
            return

        logger.info("Opening Naukri for manual login...")
        await page.goto("https://www.naukri.com/")
        print("\n[ACTION REQUIRED] Please log in to Naukri in the browser window.")
        print("Once logged in, press ENTER here to continue.")
        input()

        state = await page.context.storage_state()
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_bytes(encrypt(json.dumps(state)))
        logger.info("Naukri session saved.")

    def build_search_url(self, preferences: dict) -> list[str]:
        primary = preferences.get("primary_role", "software developer")
        others = preferences.get("other_roles", [])
        job_titles = [primary] + (others if isinstance(others, list) else [])
        experience = int(preferences.get("experience_years", 0))
        listing_type = preferences.get("looking_for", "job").lower()

        if listing_type == "both":
            return [
                construct_naukri_url(job_titles, experience, "job"),
                construct_naukri_url(job_titles, experience, "internship"),
            ]
        return [construct_naukri_url(job_titles, experience, listing_type)]

    async def scrape_jobs(self, page: Page, search_url: str) -> list[dict]:
        return await scrape_jobs(page, search_url)

    async def apply(
        self,
        page: Page,
        job: dict,
        resume_summary: str,
        preferences_md: str,
        automation_mode: str = "semi_automated",
    ) -> dict:
        return await apply_to_job(page, job, resume_summary, preferences_md, automation_mode)