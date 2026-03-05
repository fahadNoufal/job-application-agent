"""
src/core/agent.py
LangGraph 0.2+ workflow.

Runs platforms sequentially in the order the user selected them.
Each platform gets its own scrape → filter → apply cycle.
Shared state (resume, preferences, applied links) persists across platforms.
"""

import json

from langgraph.graph import StateGraph, END

from src.core.state import AgentState
from src.storage.application_tracker import (
    load_preferences_md,
)
from src.storage.database import (
    init_db,
    get_applied_links,
    insert_application,
)
from src.storage.resume_store import (
    save_resume_summary,
    load_resume_summary,
    resume_summary_exists,
)
from src.llm.generator import generate_resume_summary, filter_jobs
from src.browser.manager import BrowserManager
from src.platforms.internshala import IntershalaPlatform
from src.platforms.naukri import NaukriPlatform
from src.platforms.naukri import STATE_PATH as NAUKRI_STATE_PATH
from src.utils.config import (
    INTERNSHALA_STATE_PATH,
    LLM_BATCH_SIZE,
    MAX_APPLICATIONS_DEFAULT,
    WARN_THRESHOLD_RATIO,
    DATA_DIR,
)
from src.utils.logger import get_logger

logger = get_logger("agent")


# ── Platform registry ──────────────────────────────────────────────────────────

PLATFORM_CLASSES = {
    "internshala": IntershalaPlatform,
    "naukri": NaukriPlatform,
}

PLATFORM_STATE_PATHS = {
    "internshala": INTERNSHALA_STATE_PATH,
    "naukri": NAUKRI_STATE_PATH,
}


def _get_platform(name: str):
    cls = PLATFORM_CLASSES.get(name)
    if not cls:
        raise ValueError(f"Unknown platform: '{name}'. Available: {list(PLATFORM_CLASSES)}")
    return cls()


# ── Profile helpers ────────────────────────────────────────────────────────────

def _platform_profile_path(platform: str):
    return DATA_DIR / f"user_profile_{platform}.json"


def _load_platform_profile(platform: str) -> dict:
    path = _platform_profile_path(platform)
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _save_platform_profile(platform: str, data: dict) -> None:
    _platform_profile_path(platform).write_text(json.dumps(data, indent=2))


def _platform_raw_jobs_path(platform: str):
    return DATA_DIR / f"raw_jobs_{platform}.json"


def _platform_shortlisted_path(platform: str):
    return DATA_DIR / f"shortlisted_jobs_{platform}.json"

# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_load_json(path):
    if not path.exists():
        return []

    content = path.read_text().strip()

    if not content:
        return []

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return []
    
# ── Nodes ──────────────────────────────────────────────────────────────────────

async def node_load_persisted_data(state: AgentState) -> AgentState:
    """Initialise DB, load resume summary, seed applied links."""
    logger.info("[Stage] Loading persisted data...")
    await init_db()

    resume_summary = state.get("resume_summary", "")
    if not resume_summary and resume_summary_exists():
        resume_summary = load_resume_summary()
        logger.info("Loaded existing resume summary.")

    return {
        **state,
        "resume_summary": resume_summary,
        "application_results": state.get("application_results", []),
        "stage": "data_loaded",
    }


async def node_generate_resume_summary(state: AgentState) -> AgentState:
    """Generate and cache resume summary (runs once, shared across all platforms)."""
    if state.get("resume_summary"):
        logger.info("[Stage] Resume summary already loaded — skipping.")
        return {**state, "stage": "summary_ready"}

    logger.info("[Stage] Generating resume summary...")
    summary = generate_resume_summary(state["resume_raw"])
    save_resume_summary(summary)
    return {**state, "resume_summary": summary, "stage": "summary_ready"}


async def node_run_platforms(state: AgentState) -> AgentState:
    """
    Sequential multi-platform loop.
    For each selected platform: login → scrape → filter → apply.
    Applied links accumulate across platforms to ensure global idempotency.
    """
    platforms = state.get("platforms", ["internshala"])
    all_results = list(state.get("application_results", []))
    # Global set of applied links — grows as we finish each platform
    applied_links: set[str] = await get_applied_links()

    for platform_name in platforms:
        logger.info(f"\n{'═' * 50}")
        logger.info(f"  Platform: {platform_name.upper()}")
        logger.info(f"{'═' * 50}")

        state = await _run_single_platform(
            state=state,
            platform_name=platform_name,
            applied_links=applied_links,
            all_results=all_results,
        )

        # Merge newly applied links into the global set for the next platform
        applied_links = await get_applied_links()

    return {**state, "application_results": all_results, "stage": "all_platforms_done"}


async def _run_single_platform(
    state: AgentState,
    platform_name: str,
    applied_links: set[str],
    all_results: list,
) -> AgentState:
    """Run the full scrape → filter → apply cycle for one platform."""
    platform = _get_platform(platform_name)
    state_path = PLATFORM_STATE_PATHS[platform_name]
    prefs = state["user_preferences"]

    # ── 1. Login ───────────────────────────────────────────────────────────────
    logger.info(f"[{platform_name}] Stage 1/5: login")
    async with BrowserManager(state_path=state_path, headless=False) as bm:
        page = await bm.new_page()
        await platform.login(page)
        await bm.save_state()

    # ── 2. Build search URL (cached per platform) ─────────────────────────────
    logger.info(f"[{platform_name}] Stage 2/5: build_url")
    profile = _load_platform_profile(platform_name)
    if profile.get("urls"):
        search_urls = profile["urls"]
        logger.info(f"Using cached URLs for {platform_name}: {search_urls}")
    else:
        search_urls = platform.build_search_url(prefs)
        _save_platform_profile(platform_name, {"urls": search_urls})
        logger.info(f"Built {len(search_urls)} URL(s) for {platform_name}: {search_urls}")

    # ── 3. Scrape (with checkpoint) ────────────────────────────────────────────
    logger.info(f"[{platform_name}] Stage 3/5: scrape")
    raw_path = _platform_raw_jobs_path(platform_name)
    if raw_path.exists():
        scraped_jobs = json.loads(raw_path.read_text())
        logger.info(f"Loaded {len(scraped_jobs)} checkpointed jobs for {platform_name}.")
    else:
        scraped_jobs = []
        async with BrowserManager(state_path=state_path, headless=False) as bm:
            page = await bm.new_page()
            for url in search_urls:
                jobs = await platform.scrape_jobs(page, url)
                scraped_jobs.extend(jobs)
                logger.info(f"  Scraped {len(jobs)} jobs from: {url}")
        # Deduplicate by link across both URL results
        seen_links: set[str] = set()
        deduped = []
        for job in scraped_jobs:
            if job["link"] not in seen_links:
                seen_links.add(job["link"])
                deduped.append(job)
        scraped_jobs = deduped
        raw_path.write_text(json.dumps(scraped_jobs, indent=2))
        logger.info(f"Scraped {len(scraped_jobs)} total unique jobs from {platform_name}.")

    # ── 4. Filter (with checkpoint) ────────────────────────────────────────────
    logger.info(f"[{platform_name}] Stage 4/5: filter")
    short_path = _platform_shortlisted_path(platform_name)
    if short_path.exists():
        shortlisted = _safe_load_json(short_path)
        logger.info(f"Loaded {len(shortlisted)} checkpointed shortlisted jobs for {platform_name}.")
    else:
        preferences_md = load_preferences_md()
        candidates = [j for j in scraped_jobs if j["link"] not in applied_links]
        logger.info(f"{len(candidates)} candidates after dedup.")

        shortlisted_links: set[str] = set()
        for i in range(0, len(candidates), LLM_BATCH_SIZE):
            batch = candidates[i: i + LLM_BATCH_SIZE]
            try:
                matched = filter_jobs(batch, preferences_md)
                shortlisted_links.update(matched)
                logger.info(f"  Batch {i // LLM_BATCH_SIZE + 1}: {len(matched)} matched.")
            except Exception as e:
                logger.error(f"  Filter batch error: {e}")

        link_map = {j["link"]: j for j in candidates}
        shortlisted = [link_map[lnk] for lnk in shortlisted_links if lnk in link_map]
        short_path.write_text(json.dumps(shortlisted, indent=2))
        logger.info(f"Shortlisted {len(shortlisted)} jobs for {platform_name}.")

    # ── 5. Apply ───────────────────────────────────────────────────────────────
    logger.info(f"[{platform_name}] Stage 5/5: apply")
    max_apps = int(prefs.get("max_applications", MAX_APPLICATIONS_DEFAULT))
    warn_at = int(max_apps * WARN_THRESHOLD_RATIO)
    automation_mode = state.get("automation_mode", "semi_automated")
    preferences_md = load_preferences_md()
    resume_summary = state["resume_summary"]

    jobs_to_apply = [
        j for j in shortlisted if j["link"] not in applied_links
    ][:max_apps]

    if not jobs_to_apply:
        logger.info(f"No new jobs to apply to on {platform_name}.")
        return state

    logger.info(f"Applying to {len(jobs_to_apply)} jobs on {platform_name}.")
    applied_count = 0

    async with BrowserManager(state_path=state_path, headless=False) as bm:
        page = await bm.new_page()

        for job in jobs_to_apply:
            if applied_count == warn_at:
                logger.warning(
                    f"{platform_name}: reached {warn_at}/{max_apps} "
                    f"({int(WARN_THRESHOLD_RATIO * 100)}% of limit)."
                )

            result = await platform.apply(
                page, job, resume_summary, preferences_md,
                automation_mode=automation_mode,
            )
            all_results.append(result)

            # Persist to DB
            await insert_application(
                platform=platform_name,
                job_title=job["title"],
                company=job["company"],
                link=job["link"],
                status=result["status"],
                error=result.get("error"),
                raw_questions=result.get("raw_questions"),
            )

            applied_count += 1
            logger.info(
                f"  [{platform_name}] {applied_count}/{len(jobs_to_apply)} — "
                f"{result['status']}: {job['title']} @ {job['company']}"
            )

    return state


# ── Graph construction ─────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("load_data", node_load_persisted_data)
    graph.add_node("resume_summary", node_generate_resume_summary)
    graph.add_node("run_platforms", node_run_platforms)

    graph.set_entry_point("load_data")
    graph.add_edge("load_data", "resume_summary")
    graph.add_edge("resume_summary", "run_platforms")
    graph.add_edge("run_platforms", END)

    return graph.compile()