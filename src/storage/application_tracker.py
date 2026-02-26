"""
src/storage/application_tracker.py
Manages JSON checkpoint files for crash recovery.
"""

import json
from typing import Any

from src.utils.config import (
    RAW_JOBS_PATH,
    SHORTLISTED_JOBS_PATH,
    PREFERENCES_PATH,
)


def save_json(path, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_json(path, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_raw_jobs(jobs: list[dict]) -> None:
    save_json(RAW_JOBS_PATH, jobs)


def load_raw_jobs() -> list[dict]:
    return load_json(RAW_JOBS_PATH, default=[])


def save_shortlisted_jobs(jobs: list[dict]) -> None:
    save_json(SHORTLISTED_JOBS_PATH, jobs)


def load_shortlisted_jobs() -> list[dict]:
    return load_json(SHORTLISTED_JOBS_PATH, default=[])


def save_preferences_md(preferences: dict) -> None:
    """Write a Markdown-formatted preferences file for LLM consumption."""
    lines = ["# User Job Preferences\n"]
    for key, value in preferences.items():
        label = key.replace("_", " ").title()
        lines.append(f"**{label}:** {value}\n")
    PREFERENCES_PATH.write_text("\n".join(lines), encoding="utf-8")


def load_preferences_md() -> str:
    if not PREFERENCES_PATH.exists():
        return ""
    return PREFERENCES_PATH.read_text(encoding="utf-8")
