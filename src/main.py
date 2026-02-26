"""
src/main.py
CLI entry point. Collects user inputs, persists them, then runs the LangGraph agent.
"""

import asyncio
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm

from src.utils.config import (
    USER_PROFILE_PATH,
    PREFERENCES_PATH,
    MAX_APPLICATIONS_DEFAULT,
)
from src.utils.logger import get_logger
from src.storage.resume_store import save_resume, load_resume
from src.storage.application_tracker import save_preferences_md
from src.core.agent import build_graph
from src.core.state import AgentState

console = Console()
logger = get_logger("main")


# ── CLI Input Collection ───────────────────────────────────────────────────────

def collect_inputs() -> dict:
    console.print(Panel.fit(
        "[bold cyan]🤖 Autonomous Job Application Agent[/bold cyan]\n"
        "Complete the setup below. Your data is encrypted locally.",
        border_style="cyan",
    ))

    prefs = {}

    # 1. Type of listing
    looking_for = Prompt.ask(
        "Looking for",
        choices=["internship", "job", "both"],
        default="internship",
    )
    prefs["looking_for"] = looking_for

    # 2. Primary role
    prefs["primary_role"] = Prompt.ask("Primary preferred job role")

    # 3. Other roles
    other = Prompt.ask("Other preferred roles (comma-separated, or ENTER to skip)", default="")
    prefs["other_roles"] = [r.strip() for r in other.split(",") if r.strip()]

    # 4. Experience
    prefs["experience_years"] = IntPrompt.ask("Years of experience (0 if fresher)", default=0)

    # 5. Remote / Onsite
    work_mode = Prompt.ask("Work preference", choices=["remote", "onsite", "both"], default="both")
    prefs["work_mode"] = work_mode

    # 6. Locations
    if work_mode in ("onsite", "both"):
        locations = Prompt.ask("Preferred locations (comma-separated, include country)")
        prefs["preferred_locations"] = [l.strip() for l in locations.split(",") if l.strip()]
    else:
        prefs["preferred_locations"] = []

    # 7. Salary
    prefs["min_monthly_salary"] = IntPrompt.ask("Minimum monthly salary/stipend (0 to skip)", default=0)
    prefs["min_yearly_salary"] = IntPrompt.ask("Minimum yearly salary (0 to skip)", default=0)

    # 8. Resume (multi-line until END)
    console.print("\n[yellow]Paste your resume below. Type [bold]END[/bold] on a new line when done:[/yellow]")
    resume_lines = []
    while True:
        line = input()
        if line.strip().upper() == "END":
            break
        resume_lines.append(line)
    resume_text = "\n".join(resume_lines)

    # 9. Additional preferences
    prefs["additional_preferences"] = Prompt.ask(
        "Any additional preferences or notes (or ENTER to skip)", default=""
    )

    # 10. Platforms
    console.print("Available platforms: [bold]internshala[/bold] (LinkedIn, Wellfound — coming soon)")
    prefs["platforms"] = ["internshala"]

    # 11. Max applications
    prefs["max_applications"] = IntPrompt.ask(
        f"Max applications per platform (1–{MAX_APPLICATIONS_DEFAULT})",
        default=10,
    )
    prefs["max_applications"] = min(max(1, prefs["max_applications"]), MAX_APPLICATIONS_DEFAULT)
    
    # 12. Automation mode
    console.print("\n[bold]Automation Mode[/bold]")
    console.print("  [cyan]fully_automated[/cyan]  — agent applies to all shortlisted jobs without interruption")
    console.print("  [cyan]semi_automated[/cyan]   — agent fills each form, then pauses for your review before submitting\n")
    automation_mode = Prompt.ask(
        "Choose mode",
        choices=["fully_automated", "semi_automated"],
        default="semi_automated",
    )
    prefs["automation_mode"] = automation_mode
    
    
    return prefs, resume_text


def load_or_collect_inputs() -> tuple[dict, str]:
    """Load saved preferences if they exist, otherwise collect from CLI."""
    profile_exists = USER_PROFILE_PATH.exists()
    prefs_exist = PREFERENCES_PATH.exists()

    if profile_exists and prefs_exist:
        use_saved = Confirm.ask(
            "Found saved preferences from a previous run. Use them?",
            default=True,
        )
        if use_saved:
            try:
                prefs = json.loads(USER_PROFILE_PATH.read_text())
                prefs.pop("url", None)  # <-- remove URL automatically
            except Exception:
                prefs = json.loads(USER_PROFILE_PATH.read_text())
            # Resume is encrypted — load from file
            try:
                resume = load_resume()
                console.print("[green]✓ Loaded saved preferences and resume.[/green]")
                return prefs, resume
            except FileNotFoundError:
                console.print("[yellow]Resume file not found. Please re-enter your resume.[/yellow]")

    return collect_inputs()


# ── Main ───────────────────────────────────────────────────────────────────────

async def main():
    prefs, resume_text = load_or_collect_inputs()
    
    # Persist inputs
    save_resume(resume_text)
    save_preferences_md(prefs)

    # Save prefs as JSON profile (for reuse)
    USER_PROFILE_PATH.write_text(json.dumps(prefs, indent=2))
    logger.info("Preferences saved.")

    # Build initial state
    initial_state: AgentState = {
        "user_preferences": prefs,
        "resume_raw": resume_text,
        "resume_summary": "",
        "search_url": "",
        "scraped_jobs": [],
        "shortlisted_jobs": [],
        "applied_job_links": set(),
        "current_job_index": 0,
        "application_results": [],
        "stage": "init",
        "error": None,
        "platform": "internshala",
    }

    console.print("\n[bold green]Starting agent workflow...[/bold green]\n")

    graph = build_graph()
    final_state = await graph.ainvoke(initial_state)

    # ── Summary ────────────────────────────────────────────────────────────────
    results = final_state.get("application_results", [])
    applied = [r for r in results if r["status"] == "applied"]
    skipped = [r for r in results if r["status"] == "skipped"]
    failed  = [r for r in results if r["status"] not in ("applied", "skipped")]

    console.print(Panel.fit(
        f"[bold]Run Complete[/bold]\n\n"
        f"✅ Applied:  {len(applied)}\n"
        f"⏭  Skipped:  {len(skipped)}\n"
        f"❌ Failed:   {len(failed)}\n"
        f"📋 Results saved to applications.db",
        border_style="green" if not failed else "yellow",
    ))

    if failed:
        console.print("\n[red]Failed applications:[/red]")
        for r in failed:
            console.print(f"  • {r['title']} @ {r['company']} — {r['error']}")

    # Optional CSV export
    export = Confirm.ask("\nExport results to CSV?", default=False)
    if export:
        from src.storage.database import export_to_csv
        from src.utils.config import DATA_DIR
        csv_path = str(DATA_DIR / "applications_export.csv")
        await export_to_csv(csv_path)
        console.print(f"[green]Exported to {csv_path}[/green]")


if __name__ == "__main__":
    asyncio.run(main())
