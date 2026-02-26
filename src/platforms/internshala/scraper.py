"""
src/platforms/internshala/scraper.py
Scrapes job listings from Internshala search pages.
Handles pagination and extracts structured job data.
"""

import asyncio
from typing import Optional

from playwright.async_api import Page

from src.browser.actions import navigate, scroll_to_bottom, human_delay
from src.platforms.internshala import selectors as S
from src.platforms.internshala.schemas import InternshalaJob
from src.utils.logger import get_logger

logger = get_logger("internshala.scraper")

BASE_URL = "https://internshala.com"

_CARD       = ".internship_meta:has(.job-title-href)"
_TITLE      = ".job-title-href"
_COMPANY    = ".company-name"
_LOCATION   = ".locations span"
_STIPEND    = ".stipend"
_DURATION   = ".row-1-item"          # use nth(2)
_DESCRIPTION= ".about_job .text"
_POSTED     = ".status-inactive span"
_NEXT_PAGE  = "a.next_page, .pagination .next a"
_ANCHOR_WAIT= ".job-title-href"  

async def scrape_jobs(page: Page, search_url: str, max_pages: int = 1) -> list[dict]:
    """
    Scrape job listings from Internshala starting at search_url.
    Paginates up to max_pages pages.
    Returns list of raw job dicts.
    """
    all_jobs: list[dict] = []
    current_url = search_url
    for page_num in range(1, max_pages + 1):
        logger.info(f"Scraping page {page_num}: {current_url}")

        # networkidle is important for Internshala — JS renders the cards
        await page.goto(current_url, wait_until="networkidle")

        # Wait until at least one job title is visible
        try:
            await page.wait_for_selector(_ANCHOR_WAIT, timeout=15_000)
        except Exception:
            logger.warning(f"Timed out waiting for job cards on page {page_num}. Stopping.")
            break

        jobs_on_page = await _extract_jobs_from_page(page)
        logger.info(f"  Found {len(jobs_on_page)} jobs on page {page_num}")
        all_jobs.extend(jobs_on_page)
        
        if len(jobs_on_page)>40:
            logger.info("More than 40 jobs found in the first page itself.")
            break

        next_url = await _get_next_page_url(page)
        if not next_url:
            logger.info("No more pages.")
            break
        current_url = next_url
        await human_delay(1.5, 3.0)

    logger.info(f"Total scraped: {len(all_jobs)} jobs")
    return all_jobs


async def _extract_jobs_from_page(page: Page) -> list[dict]:
    """Extract all job cards from the current page using the Locator API."""
    jobs = []
    cards = page.locator(_CARD)
    count = await cards.count()

    for i in range(count):
        try:
            card = cards.nth(i)
            job = await _parse_card(card)
            if job:
                jobs.append(job.model_dump())
        except Exception as e:
            logger.debug(f"Failed to parse job card #{i}: {e}")

    return jobs


async def _parse_card(card) -> Optional[InternshalaJob]:
    """Parse a single Locator card into an InternshalaJob."""
    try:
        # Title + link
        title_loc = card.locator(_TITLE).first
        if not await title_loc.count():
            return None
        title = (await title_loc.text_content()).strip()
        relative_link = await title_loc.get_attribute("href") or ""
        link = (BASE_URL + relative_link) if relative_link and not relative_link.startswith("http") else relative_link

        # Company
        company_loc = card.locator(_COMPANY)
        company = (await company_loc.text_content()).strip() if await company_loc.count() else "Unknown"

        # Location — first visible span inside .locations
        loc_loc = card.locator(_LOCATION).first
        location = (await loc_loc.text_content()).strip() if await loc_loc.count() else None

        # Stipend
        stipend_loc = card.locator(_STIPEND)
        stipend = (await stipend_loc.text_content()).strip() if await stipend_loc.count() else None

        # Duration — the third .row-1-item (index 2)
        dur_loc = card.locator(_DURATION).nth(2)
        duration = (await dur_loc.text_content()).strip() if await dur_loc.count() else None

        # Short description shown on card
        desc_loc = card.locator(_DESCRIPTION)
        description = (await desc_loc.text_content()).strip() if await desc_loc.count() else None

        # Days since posted
        posted_loc = card.locator(_POSTED)
        days_posted = (await posted_loc.text_content()).strip() if await posted_loc.count() else None

        return InternshalaJob(
            title=title,
            company=company,
            link=link,
            location=location,
            stipend=stipend,
            duration=duration,
            description=description,
            days_posted=days_posted,
        )

    except Exception as e:
        logger.debug(f"Card parse error: {e}")
        return None


async def fetch_job_description(page: Page, job_url: str) -> str:
    """Navigate to a job detail page and extract the full description."""
    await page.goto(job_url, wait_until="networkidle")
    try:
        desc_el = await page.query_selector("#about_internship, .about-section, .internship_details")
        if desc_el:
            return (await desc_el.inner_text()).strip()
    except Exception as e:
        logger.debug(f"Could not fetch description from {job_url}: {e}")
    return ""


async def _get_next_page_url(page: Page) -> Optional[str]:
    """Return the URL of the next page, or None if on the last page."""
    try:
        next_el = page.locator(_NEXT_PAGE).first
        if await next_el.count():
            href = await next_el.get_attribute("href")
            if href:
                return href if href.startswith("http") else BASE_URL + href
    except Exception:
        pass
    return None
