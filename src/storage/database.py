"""
src/storage/database.py
Async SQLite wrapper. Creates tables and provides CRUD for applications.
"""

import json
import aiosqlite
from datetime import datetime
from typing import Optional

from src.utils.config import APPLICATIONS_DB_PATH

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS applications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT NOT NULL,
    job_title       TEXT NOT NULL,
    company         TEXT NOT NULL,
    link            TEXT NOT NULL UNIQUE,
    status          TEXT NOT NULL DEFAULT 'applied',
    applied_at      TEXT NOT NULL,
    error           TEXT,
    raw_questions   TEXT
);
"""


async def init_db() -> None:
    """Create tables if they do not exist."""
    async with aiosqlite.connect(APPLICATIONS_DB_PATH) as db:
        await db.execute(CREATE_TABLE_SQL)
        await db.commit()


async def get_applied_links(platform: Optional[str] = None) -> set[str]:
    """Return set of job links already applied to (optionally filtered by platform)."""
    async with aiosqlite.connect(APPLICATIONS_DB_PATH) as db:
        if platform:
            cursor = await db.execute(
                "SELECT link FROM applications WHERE platform = ?", (platform,)
            )
        else:
            cursor = await db.execute("SELECT link FROM applications")
        rows = await cursor.fetchall()
        return {row[0] for row in rows}


async def insert_application(
    *,
    platform: str,
    job_title: str,
    company: str,
    link: str,
    status: str = "applied",
    error: Optional[str] = None,
    raw_questions: Optional[list] = None,
) -> None:
    """Insert a new application record. Silently ignores duplicate links."""
    async with aiosqlite.connect(APPLICATIONS_DB_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO applications
                (platform, job_title, company, link, status, applied_at, error, raw_questions)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                platform,
                job_title,
                company,
                link,
                status,
                datetime.utcnow().isoformat(),
                error,
                json.dumps(raw_questions) if raw_questions else None,
            ),
        )
        await db.commit()


async def update_application_status(link: str, status: str, error: Optional[str] = None) -> None:
    async with aiosqlite.connect(APPLICATIONS_DB_PATH) as db:
        await db.execute(
            "UPDATE applications SET status = ?, error = ? WHERE link = ?",
            (status, error, link),
        )
        await db.commit()


async def export_to_csv(path: str) -> None:
    """Optional CSV export of all applications."""
    import csv
    async with aiosqlite.connect(APPLICATIONS_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM applications ORDER BY applied_at DESC")
        rows = await cursor.fetchall()

    with open(path, "w", newline="", encoding="utf-8") as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows([dict(r) for r in rows])
