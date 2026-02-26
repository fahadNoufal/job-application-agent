"""
src/core/state.py
Typed state shared across all LangGraph nodes.
"""

from typing import Optional, TypedDict


class AgentState(TypedDict):
    # ── User inputs ────────────────────────────────────────────────────────────
    user_preferences: dict          # raw structured preferences from CLI
    resume_raw: str                 # full resume text (NOT sent to LLM directly)
    resume_summary: str             # LLM-condensed resume (used for answer generation)

    # ── Workflow data ──────────────────────────────────────────────────────────
    search_url: str
    scraped_jobs: list[dict]
    shortlisted_jobs: list[dict]
    applied_job_links: set[str]     # links already in DB (idempotency)
    current_job_index: int
    application_results: list[dict]

    # ── Control ────────────────────────────────────────────────────────────────
    stage: str                      # last completed stage (for crash recovery)
    error: Optional[str]
    platform: str                   # active platform name
    automation_mode: str            # "fully_automated" | "semi_automated"
