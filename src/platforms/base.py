"""
src/platforms/base.py
Abstract base class all platforms must implement.
"""

from abc import ABC, abstractmethod
from playwright.async_api import Page


class BasePlatform(ABC):

    @abstractmethod
    async def login(self, page: Page) -> None:
        """Handle login. May be manual + state-save or automated."""
        ...

    @abstractmethod
    def build_search_url(self, preferences: dict) -> list[str]:
        """Construct the job search URL from user preferences."""
        ...

    @abstractmethod
    async def scrape_jobs(self, page: Page, search_url: str) -> list[dict]:
        """Scrape raw job listings from the platform."""
        ...

    @abstractmethod
    async def apply(self, page: Page, job: dict, resume_summary: str, preferences_md: str, automation_mode: str = "semi_automated") -> dict:
        """Apply to a single job. Return result dict."""
        ...
