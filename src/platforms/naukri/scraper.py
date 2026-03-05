"""
src/platforms/naukri/scraper.py
Naukri URL construction and job listing scraper.
"""

import asyncio
from urllib.parse import quote
from typing import Optional

from playwright.async_api import Page

from src.browser.actions import navigate, human_delay
from src.platforms.naukri import selectors as S
from src.platforms.naukri.schemas import NaukriJob
from src.utils.logger import get_logger

logger = get_logger("naukri.scraper")

BASE_URL = "https://www.naukri.com"


# ── URL Builder ───────────────────────────────────────────────────────────────

def construct_naukri_url(
    job_title: str,
    experience: int,
    role_type: str,
) -> str:
    """
    Build a Naukri search URL from a list of job titles, experience level,
    and role type ('job' or 'internship').

    Uses the primary role + all other preferred roles together so results
    cover the full breadth of what the user is looking for.
    """
    role_type = role_type.lower().strip()
    # titles = [t.strip().lower() for t in job_titles if t.strip()]

    # ── Path segment ─────────────────────────────────────────────────────────
    slug_part = job_title.replace(" ", "-").lower()
    path = f"{slug_part}-internship-jobs" if role_type == "internship" else f"{slug_part}-jobs"

    # ── Query keyword string ──────────────────────────────────────────────────
    keyword_string = job_title.lower().strip()
    if role_type == "internship":
        keyword_string += " internship"
    encoded_keywords = quote(keyword_string)

    # ── Final URL ─────────────────────────────────────────────────────────────
    base = f"{BASE_URL}/{path}"
    if role_type == "internship":
        url = (
            f"{base}"
            f"?k={encoded_keywords}"
            f"&experience={experience}"
            f"&qproductJobSource=2"
            f"&qinternshipFlag=true"
            f"&naukriCampus=true"
        )
    else:
        url = (
            f"{base}"
            f"?k={encoded_keywords}"
            f"&experience={experience}"
            f"&qproductJobSource=2"
            f"&naukriCampus=true"
        )

    logger.debug(f"Constructed Naukri URL: {url}")
    return url


# ── Scraper ───────────────────────────────────────────────────────────────────

async def scrape_jobs(page: Page, search_url: str, max_pages: int = 5) -> list[dict]:
    """
    Scrape Naukri job listings starting at search_url.
    Paginates up to max_pages.
    """
    all_jobs: list[dict] = []
    current_url = search_url

    for page_num in range(1, max_pages + 1):
        logger.info(f"Scraping Naukri page {page_num}: {current_url}")
        await navigate(page, current_url)

        try:
            await page.wait_for_selector(S.JOB_CARD, timeout=15_000)
        except Exception:
            logger.warning(f"No job cards found on page {page_num}. Stopping.")
            break

        cards = await page.query_selector_all(S.JOB_CARD)
        logger.info(f"  Found {len(cards)} cards on page {page_num}")

        for card in cards:
            try:
                job = await _parse_card(card)
                if job:
                    all_jobs.append(job.model_dump())
            except Exception as e:
                logger.debug(f"Card parse error: {e}")

        next_url = await _get_next_page_url(page)
        if not next_url:
            logger.info("No more pages.")
            break
        current_url = next_url
        await human_delay(1.5, 3.0)

    logger.info(f"Naukri total scraped: {len(all_jobs)} jobs")
    return all_jobs


async def _parse_card(card) -> Optional[NaukriJob]:
    title_el = await card.query_selector(S.JOB_TITLE)
    if not title_el:
        return None

    title = (await title_el.inner_text()).strip()
    link = await title_el.get_attribute("href") or ""
    if link and not link.startswith("http"):
        link = BASE_URL + link

    company_el = await card.query_selector(S.JOB_COMPANY)
    company = (await company_el.inner_text()).strip() if company_el else "Unknown"

    exp_el = await card.query_selector(S.JOB_EXPERIENCE)
    experience = (await exp_el.inner_text()).strip() if exp_el else None

    sal_el = await card.query_selector(S.JOB_SALARY)
    salary = (await sal_el.inner_text()).strip() if sal_el else None

    loc_el = await card.query_selector(S.JOB_LOCATION)
    location = (await loc_el.inner_text()).strip() if loc_el else None

    posted_el = await card.query_selector(S.JOB_POSTED)
    starts_in = (await posted_el.inner_text()).strip() if posted_el else None

    return NaukriJob(
        title=title,
        company=company,
        link=link,
        location=location,
        salary_or_stipend=salary,
        experience_or_duration=experience,
        starts_in=starts_in,
        description=None,   # not available on listing cards
    )


async def fetch_job_description(page: Page, job_url: str) -> str:
    """Navigate to job detail page and extract description."""
    await navigate(page, job_url)
    try:
        el = await page.query_selector(S.JOB_DESCRIPTION)
        if el:
            return (await el.inner_text()).strip()
    except Exception as e:
        logger.debug(f"Description fetch failed for {job_url}: {e}")
    return ""


async def _get_next_page_url(page: Page) -> Optional[str]:
    try:
        next_el = await page.query_selector(S.PAGINATION_NEXT)
        if next_el:
            href = await next_el.get_attribute("href")
            if href:
                return href if href.startswith("http") else BASE_URL + href
    except Exception:
        pass
    return None