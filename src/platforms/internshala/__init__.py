"""
src/platforms/internshala/__init__.py
Internshala platform implementation.
Handles login flow, URL construction, scraping, and application.
"""

import re
from pathlib import Path
from playwright.async_api import Page

from src.platforms.base import BasePlatform
from src.platforms.internshala.scraper import scrape_jobs
from src.platforms.internshala.applier import apply_to_job
from src.browser.manager import BrowserManager
from src.utils.config import INTERNSHALA_STATE_PATH
from src.utils.logger import get_logger
from src.llm.generator import classify_domain

logger = get_logger("internshala")

BASE = "https://internshala.com"

# ── Keyword → Internshala domain slug mapping ─────────────────────────────────
DOMAIN_SLUG_MAP = {
    "software development": "software-development",
    "data science": "data-science",
    "artificial intelligence": "artificial-intelligence",
    "ai": "artificial-intelligence",
    "machine learning": "machine-learning",
    "cloud computing": "cloud-computing",
    "cyber security": "cyber-security",
    "information technology": "information-technology",
    "engineering": "engineering",
    "design": "design",
    "digital marketing": "digital-marketing",
    "marketing": "marketing",
    "sales": "sales",
    "finance": "finance",
    "human resources": "human-resources",
    "hr": "human-resources",
    "operations": "operations",
    "product management": "product-management",
    "project management": "project-management",
    "business development": "business-development",
    "general management": "general-management",
    "customer service": "customer-service",
    "supply chain management": "supply-chain-management",
    "scm": "supply-chain-management",
    "law": "law",
    "teaching": "teaching",
    "content writing": "content-writing",
}


# Not Domain , its Role
def role_to_slug(domain: str) -> str:
    """Convert LLM-classified domain name to Internshala URL slug."""
    normalized = domain.lower().strip()
    # Direct lookup
    if normalized in DOMAIN_SLUG_MAP:
        return DOMAIN_SLUG_MAP[normalized]
    # Partial match
    for key, slug in DOMAIN_SLUG_MAP.items():
        if key in normalized or normalized in key:
            return slug
    # Fallback: slugify the raw string
    
    if not slug:
        logger.info("Deterministic classification failed — using LLM.")
        domain = classify_domain(domain)
        slug = role_to_slug(domain)
    
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    logger.warning(f"No slug mapping for domain '{domain}' — using raw slug: {slug}")
    return slug


def build_internshala_url(slug: str, listing_type: str) -> str:
    """
    Build the correct Internshala search URL.
    listing_type: 'internship' | 'job' | 'both'
    """
    if listing_type == "job":
        return f"{BASE}/jobs/{slug}-jobs"
    else:  # internship or both → internship URL (Internshala primary use case)
        return f"{BASE}/internships/{slug}-internship"


class IntershalaPlatform(BasePlatform):

    async def login(self, page: Page) -> None:
        """
        Manual login flow with state persistence.
        If a saved state exists, skip (already logged in).
        """
        bm = BrowserManager(state_path=INTERNSHALA_STATE_PATH)
        if bm.state_exists():
            logger.info("Internshala: using saved session state. Skipping login.")
            return

        logger.info("Opening Internshala for manual login...")
        await page.goto(f"{BASE}/login")
        print("\n[ACTION REQUIRED] Please log in to Internshala in the browser window.")
        print("Once logged in, press ENTER here to continue.")
        input()

        # Save state via a BrowserManager reference
        # We reuse the already-open context from the caller
        from playwright.async_api import BrowserContext
        state = await page.context.storage_state()
        import json
        from src.utils.config import encrypt
        INTERNSHALA_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        INTERNSHALA_STATE_PATH.write_bytes(encrypt(json.dumps(state)))
        logger.info("Internshala session saved.")

    def build_search_url(self, preferences: dict) -> list[str]:
        domain_value = preferences.get("domain")

        # If a domain is explicitly provided, use it.
        # Otherwise, derive it from the primary role.
        if domain_value:
            domain = domain_value
        else:
            role = preferences.get("primary_role", "Software Development")
            domain = role_to_slug(role)

        listing_type = preferences.get("looking_for", "internship").lower()

        if listing_type == "both":
            return [
                build_internshala_url(domain, "internship"),
                build_internshala_url(domain, "job"),
            ]

        return [build_internshala_url(domain, listing_type)]

    async def scrape_jobs(self, page: Page, search_url: str) -> list[dict]:
        return await scrape_jobs(page, search_url)

    async def apply(self, page: Page, job: dict, resume_summary: str, preferences_md: str,automation_mode: str = "semi_automated") -> dict:
        return await apply_to_job(page, job, resume_summary, preferences_md,automation_mode=automation_mode)
