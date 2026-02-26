"""
src/core/agent.py
LangGraph 0.2+ workflow definition.
Each node is a pure async function that updates AgentState.
"""

import json
import asyncio
from typing import cast

from langgraph.graph import StateGraph, END

from src.core.state import AgentState
from src.storage.application_tracker import (
    save_raw_jobs,
    load_raw_jobs,
    save_shortlisted_jobs,
    load_shortlisted_jobs,
    save_preferences_md,
    load_preferences_md,
)
from src.storage.database import (
    init_db,
    get_applied_links,
    insert_application,
    update_application_status,
)
from src.storage.resume_store import (
    save_resume,
    load_resume,
    save_resume_summary,
    load_resume_summary,
    resume_summary_exists,
)
from src.llm.generator import classify_domain, generate_resume_summary, filter_jobs
from src.browser.manager import BrowserManager
from src.platforms.internshala import IntershalaPlatform, build_internshala_url, role_to_slug
from src.utils.config import (
    USER_PROFILE_PATH,
    INTERNSHALA_STATE_PATH,
    LLM_BATCH_SIZE,
    MAX_APPLICATIONS_DEFAULT,
    WARN_THRESHOLD_RATIO,
)
from src.utils.logger import get_logger

logger = get_logger("agent")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_user_profile() -> dict:
    try:
        return json.loads(USER_PROFILE_PATH.read_text())
    except Exception:
        return {}


def _save_user_profile(data: dict) -> None:
    try:
        if USER_PROFILE_PATH.exists():
            existing = json.loads(USER_PROFILE_PATH.read_text())
        else:
            existing = {}
    except Exception:
        existing = {}

    # Merge new data into existing
    existing.update(data)

    USER_PROFILE_PATH.write_text(json.dumps(existing, indent=2))


# ── Nodes ──────────────────────────────────────────────────────────────────────

async def node_load_persisted_data(state: AgentState) -> AgentState:
    """
    Load previously persisted data to support crash recovery.
    Skips stages that were already completed.
    """
    logger.info("[Stage] Loading persisted data...")
    await init_db()

    prefs = state["user_preferences"]
    platform = state.get("platform", "internshala")

    # Load already-applied links for idempotency
    applied = await get_applied_links(platform=platform)

    # Load resume summary if exists (avoid regenerating)
    resume_summary = state.get("resume_summary", "")
    if not resume_summary and resume_summary_exists():
        resume_summary = load_resume_summary()
        logger.info("Loaded existing resume summary.")

    # Load checkpoint files if crash recovery
    scraped = state.get("scraped_jobs") or load_raw_jobs()
    shortlisted = state.get("shortlisted_jobs") or load_shortlisted_jobs()

    return {
        **state,
        "applied_job_links": applied,
        "resume_summary": resume_summary,
        "scraped_jobs": scraped,
        "shortlisted_jobs": shortlisted,
        "application_results": state.get("application_results", []),
        "current_job_index": 0,
        "stage": "data_loaded",
    }


async def node_build_search_url(state: AgentState) -> AgentState:
    """
    Determine domain and build search URL.
    Caches result in user_profile.json to avoid repeated LLM calls.
    """
    logger.info("[Stage] Building search URL...")
    profile = _load_user_profile()

    if profile.get("url"):
        logger.info(f"Using cached search URL: {profile['url']}")
        return {**state, "search_url": profile["url"], "stage": "url_built"}

    prefs = state["user_preferences"]
    role = prefs.get("primary_role", "Software Development")
    listing_type = prefs.get("looking_for", "internship").lower()

    # Try deterministic keyword match first
    from src.platforms.internshala import DOMAIN_SLUG_MAP
    normalized = role.lower().strip()
    slug = None
    for key, val in DOMAIN_SLUG_MAP.items():
        if key in normalized or normalized in key:
            slug = val
            break

    # Fallback to LLM classification
    if not slug:
        logger.info("Deterministic classification failed — using LLM.")
        domain = classify_domain(role)
        slug = role_to_slug(domain)

    url = build_internshala_url(slug, listing_type)
    _save_user_profile({"domain": slug, "url": url, "type": listing_type})
    logger.info(f"Search URL: {url}")

    return {**state, "search_url": url, "stage": "url_built"}


async def node_generate_resume_summary(state: AgentState) -> AgentState:
    """Generate resume summary if not already cached."""
    if state.get("resume_summary"):
        logger.info("[Stage] Resume summary already loaded — skipping.")
        return {**state, "stage": "summary_ready"}

    logger.info("[Stage] Generating resume summary...")
    summary = generate_resume_summary(state["resume_raw"])
    save_resume_summary(summary)

    return {**state, "resume_summary": summary, "stage": "summary_ready"}


async def node_login(state: AgentState) -> AgentState:
    """Handle platform login with state persistence."""
    logger.info("[Stage] Logging into Internshala...")
    platform = IntershalaPlatform()

    async with BrowserManager(state_path=INTERNSHALA_STATE_PATH, headless=False) as bm:
        page = await bm.new_page()
        await platform.login(page)
        await bm.save_state()

    return {**state, "stage": "logged_in"}


async def node_scrape_jobs(state: AgentState) -> AgentState:
    """Scrape jobs from Internshala. Skip if checkpoint data exists."""
    if state.get("scraped_jobs"):
        logger.info(f"[Stage] Using {len(state['scraped_jobs'])} checkpointed scraped jobs.")
        return {**state, "stage": "scraped"}

    logger.info("[Stage] Scraping jobs...")
    platform = IntershalaPlatform()

    async with BrowserManager(state_path=INTERNSHALA_STATE_PATH, headless=False) as bm:
        page = await bm.new_page()
        jobs = await platform.scrape_jobs(page, state["search_url"])

    save_raw_jobs(jobs)
    logger.info(f"Scraped {len(jobs)} jobs. Saved checkpoint.")

    return {**state, "scraped_jobs": jobs, "stage": "scraped"}


async def node_filter_jobs(state: AgentState) -> AgentState:
    """Use LLM to shortlist relevant jobs from scraped list."""
    if state.get("shortlisted_jobs"):
        logger.info(f"[Stage] Using {len(state['shortlisted_jobs'])} checkpointed shortlisted jobs.")
        return {**state, "stage": "filtered"}

    logger.info("[Stage] Filtering jobs with LLM...")
    all_jobs = state["scraped_jobs"]
    preferences_md = load_preferences_md()
    applied_links = state.get("applied_job_links", set())

    # Exclude already-applied jobs before filtering
    candidates = [j for j in all_jobs if j["link"] not in applied_links]
    logger.info(f"{len(candidates)} candidates after excluding already-applied jobs.")

    shortlisted_links: set[str] = set()

    for i in range(0, len(candidates), LLM_BATCH_SIZE):
        batch = candidates[i : i + LLM_BATCH_SIZE]
        try:
            matched_links = filter_jobs(batch, preferences_md)
            shortlisted_links.update(matched_links)
            logger.info(f"  Batch {i // LLM_BATCH_SIZE + 1}: {len(matched_links)} matched.")
        except Exception as e:
            logger.error(f"  Filter batch failed: {e}")

    # Map links back to full job dicts
    link_to_job = {j["link"]: j for j in candidates}
    shortlisted = [link_to_job[link] for link in shortlisted_links if link in link_to_job]

    save_shortlisted_jobs(shortlisted)
    logger.info(f"Shortlisted {len(shortlisted)} jobs. Saved checkpoint.")

    return {**state, "shortlisted_jobs": shortlisted, "stage": "filtered"}


async def node_apply_jobs(state: AgentState) -> AgentState:
    """
    Apply to each shortlisted job.
    Respects max_applications limit with warnings.
    Idempotent — skips already-applied links.
    """
    logger.info("[Stage] Applying to jobs...")
    prefs = state["user_preferences"]
    max_apps = int(prefs.get("max_applications", MAX_APPLICATIONS_DEFAULT))
    warn_at = int(max_apps * WARN_THRESHOLD_RATIO)

    jobs_to_apply = [
        j for j in state["shortlisted_jobs"]
        if j["link"] not in state.get("applied_job_links", set())
    ][:max_apps]

    if not jobs_to_apply:
        logger.info("No new jobs to apply to.")
        return {**state, "stage": "applied"}

    logger.info(f"Will apply to {len(jobs_to_apply)} jobs (max: {max_apps}).")
    results = list(state.get("application_results", []))
    platform = IntershalaPlatform()
    resume_summary = state["resume_summary"]
    preferences_md = load_preferences_md()
    applied_count = 0

    async with BrowserManager(state_path=INTERNSHALA_STATE_PATH, headless=False) as bm:
        page = await bm.new_page()

        for job in jobs_to_apply:
            if applied_count == warn_at:
                logger.warning(
                    f"Reached {warn_at}/{max_apps} applications ({int(WARN_THRESHOLD_RATIO*100)}% of limit)."
                )

            result = await platform.apply(
                page, job, resume_summary, preferences_md,
                automation_mode=state.get("automation_mode", "semi_automated"),
                                          )
            results.append(result)

            # Persist to DB immediately
            await insert_application(
                platform=state.get("platform", "internshala"),
                job_title=job["title"],
                company=job["company"],
                link=job["link"],
                status=result["status"],
                error=result.get("error"),
                raw_questions=result.get("raw_questions"),
            )

            applied_count += 1
            logger.info(f"Progress: {applied_count}/{len(jobs_to_apply)}")

    return {**state, "application_results": results, "stage": "applied"}


# ── Graph construction ─────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    logger.info("Building workflow graph...")
    graph.add_node("load_data", node_load_persisted_data)
    graph.add_node("build_url", node_build_search_url)
    graph.add_node("resume_summary", node_generate_resume_summary)
    graph.add_node("login", node_login)
    graph.add_node("scrape", node_scrape_jobs)
    graph.add_node("filter", node_filter_jobs)
    graph.add_node("apply", node_apply_jobs)

    graph.set_entry_point("load_data")
    graph.add_edge("load_data", "build_url")
    graph.add_edge("build_url", "resume_summary")
    graph.add_edge("resume_summary", "login")
    graph.add_edge("login", "scrape")
    graph.add_edge("scrape", "filter")
    graph.add_edge("filter", "apply")
    graph.add_edge("apply", END)

    return graph.compile()
