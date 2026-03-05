# 🤖 Autonomous Job Application Agent

An end-to-end agentic system that logs in to job platforms, scrapes listings, filters them using an LLM, and automatically fills and submits applications; with a semi-automated review mode so you stay in control.

Built with LangGraph, Playwright, and Gemini 2.5 Flash.

---

## Features

- ✅ CLI-driven setup with encrypted local storage
- ✅ Multi-platform — Apply on multiple platforms in one command
- ✅ LLM-powered domain classification and job filtering
- ✅ Automated form filling with contextual answer generation from the data you provide
- ✅ Idempotent — never re-applies to the same job
- ✅ Crash-recoverable — resumes from last checkpoint
- ✅ Human-like browser automation (randomized timing)
- ✅ SQLite application tracker with optional CSV export
- ✅ Semi-automated mode — agent fills every form, you review and press Enter to submit or s to skip
- ✅ Platform-isolated architecture (Internshala & Naukri active; LinkedIn/Wellfound )
- ✅ Encrypted storage — resume, session cookies, and summaries are AES-encrypted at rest

---

## How It Works

```
Onboarding (CLI)
      │
      ▼
┌─────────────────────────────────────────────────┐
│              LangGraph Workflow                  │
│                                                 │
│  load_data → resume_summary → run_platforms     │
│                                     │           │
│              ┌──────────────────────┤           │
│              │   For each platform: │           │
│              │                      │           │
│              │  1. login            │           │
│              │  2. build_url        │           │
│              │  3. scrape           │           │
│              │  4. LLM filter       │           │
│              │  5. apply            │           │
│              └──────────────────────┘           │
└─────────────────────────────────────────────────┘
      │
      ▼
  Summary + applications.db
```

Platforms run one after the other. Applied links accumulate globally so the same job is never applied to twice even if it appears on both platforms.

---

## Project Structure

```
job-application-agent/
├── src/
│   ├── main.py                           # CLI entry point
│   ├── core/
│   │   ├── agent.py                      # LangGraph nodes + graph
│   │   └── state.py                      # AgentState TypedDict
│   ├── platforms/
│   │   ├── base.py                       # Abstract BasePlatform
│   │   ├── internshala/
│   │   │   ├── __init__.py               # Platform class + URL builder + domain slug map
│   │   │   ├── scraper.py                # Job listing scraper
│   │   │   ├── applier.py                # Form filling + submission
│   │   │   ├── selectors.py              # All CSS selectors
│   │   │   └── schemas.py                # Pydantic models
│   │   └── naukri/
│   │       ├── __init__.py               # Platform class + URL builder
│   │       ├── scraper.py                # Job listing scraper + URL constructor
│   │       ├── applier.py                # 3-case apply flow + chatbot loop
│   │       ├── selectors.py              # All CSS selectors
│   │       └── schemas.py                # Pydantic models + ChatMessage
│   ├── browser/
│   │   ├── manager.py                    # Playwright context + encrypted state persistence
│   │   └── actions.py                    # Human-like interaction helpers
│   ├── llm/
│   │   ├── generator.py                  # All Gemini API calls
│   │   ├── prompts.py                    # All prompt templates
│   │   └── parsers.py                    # JSON parsing + retry logic
│   ├── storage/
│   │   ├── database.py                   # Async SQLite — applications + external_links
│   │   ├── resume_store.py               # Encrypted resume read/write
│   │   └── application_tracker.py        # JSON checkpoints + preferences.md
│   └── utils/
│       ├── config.py                     # Paths, env vars, Fernet encryption, constants
│       ├── logger.py                     # Rich console + per-run log file
│       └── validators.py                 # CLI input validation
├── data/
│   ├── resumes/                          # Encrypted resume + summary
│   ├── applications.db                   # SQLite — all results
│   ├── preferences.md                    # Markdown preferences (read by LLM filter)
│   ├── raw_jobs_<platform>.json          # Scrape checkpoint per platform
│   ├── shortlisted_jobs_<platform>.json  # Filter checkpoint per platform
│   └── user_profile_<platform>.json      # Cached search URLs per platform
├── configs/
│   ├── internshala_state.enc             # Encrypted browser session
│   └── naukri_state.enc                  # Encrypted browser session
├── logs/
│   └── YYYY-MM-DD_HH-MM-SS_run.log
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
├── PLATFORM_INTEGRATION.md              # Full guide for adding new platforms
└── README.md
```

---

## Setup

### Prerequisites

- Python 3.11+
- A [Gemini API key](https://aistudio.google.com/app/apikey) (free tier works)

### 1. Clone the repository

```bash
git clone https://github.com/your-username/job-application-agent.git
cd job-application-agent
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and add your Gemini API key:

```
GEMINI_API_KEY=your_key_here
ENCRYPTION_KEY=               # leave blank — auto-generated on first run
```

---

## Running the Agent

```bash
python -m src.main
```

On first run you will be prompted for:

| # | Question |
|---|---|
| 1 | Looking for: `internship` / `job` / `both` |
| 2 | Primary preferred job role |
| 3 | Other preferred roles (comma-separated) |
| 4 | Years of experience (0 if fresher) |
| 5 | Work preference: `remote` / `onsite` / `both` |
| 6 | Preferred locations (if onsite/both) |
| 7 | Minimum monthly salary / stipend |
| 8 | Minimum yearly salary |
| 9 | Full resume (paste, type `END` on a new line to finish) |
| 10 | Additional preferences or notes |
| 11 | Platform: `1` Internshala / `2` Naukri / `3` Both |
| 12 | Max applications per platform (1–20) |
| 13 | Automation mode: `semi_automated` / `fully_automated` |

On subsequent runs, saved preferences are offered — press Enter to reuse them.

**To reset and re-run from scratch:**

```bash
rm data/user_profile_*.json data/raw_jobs_*.json data/shortlisted_jobs_*.json
```

---

## Automation Modes

### Semi-automated (recommended)

The agent fills every form completely, then pauses before submitting:

```
────────────────────────────────────────────────────────────
📋  Ready to apply: Data Scientist Intern @ Acme Corp
🔗  https://internshala.com/internship/detail/...
────────────────────────────────────────────────────────────
Review the filled form in the browser window.
  [ENTER]   → Submit application
  [s+ENTER] → Skip this application

Your choice:
```

The browser window stays open so you can review and edit answers before submitting.

### Fully automated

The agent applies to every shortlisted job without pausing. A warning is logged at 75% of your max application limit.

---

## Supported Platforms

### Internshala

- Scrapes job and internship listings from category-based search pages
- Handles standard application forms (text, radio, checkbox, select, availability)
- Domain slug derived from `primary_role` using a keyword map, with LLM fallback for unrecognised roles

### Naukri

- Builds search URL from all job titles (primary role + other preferred roles combined)
- Handles three application flows automatically:

| Flow | Trigger | What happens |
|---|---|---|
| **Instant apply** | `#apply-button` → success message | Applied immediately |
| **Chatbot Q&A** | `#apply-button` → chatbot appears, or `#walkin-button` | LLM answers each question with full conversation history for consistency |
| **External redirect** | `#company-site-button` | New tab URL captured and saved to `external_links` table for manual follow-up |

---

## Data & Storage

### `applications.db` (SQLite)

**`applications` table** — every job the agent attempted:

| Column | Description |
|---|---|
| `platform` | `internshala` or `naukri` |
| `job_title` | Role title |
| `company` | Company name |
| `link` | Job URL (unique) |
| `status` | `applied` / `skipped` / `external` / `failed` / `already_applied` |
| `applied_at` | UTC timestamp |
| `error` | Error message if status is `failed` |
| `raw_questions` | JSON array of form questions seen |

**`external_links` table** — jobs that redirect to company websites:

| Column | Description |
|---|---|
| `original_link` | Naukri job page URL |
| `external_link` | Company website URL captured after redirect |
| `saved_at` | UTC timestamp |

### CSV export

At the end of each run you are offered a CSV export of the `applications` table:

```
Export results to CSV? [y/N]:
```

Output: `data/applications_export.csv`

### Checkpoint files

Each platform saves checkpoints during a run so a crash doesn't restart everything:

| File | Saved after |
|---|---|
| `data/raw_jobs_<platform>.json` | Scrape complete |
| `data/shortlisted_jobs_<platform>.json` | LLM filter complete |

Delete these files to force a fresh scrape and filter on the next run.

---

## Security

- Resume, resume summary, and browser session files are **AES-128 encrypted** (Fernet)
- The encryption key is auto-generated on first run and stored in `.env`
- `.gitignore` excludes `.env`, `data/`, `configs/`, and all `*_state.enc` files
- Resume content is never written to log files

---

## Adding a New Platform

The full guide with complete code templates, multi-step form handling, infinite scroll, file uploads, and common pitfalls is in [`PLATFORM_INTEGRATION.md`](./PLATFORM_INTEGRATION.md).

Here is the short version:

### 1. Create the directory

```bash
mkdir src/platforms/
touch src/platforms//__init__.py
touch src/platforms//scraper.py
touch src/platforms//applier.py
touch src/platforms//selectors.py
touch src/platforms//schemas.py
```

### 2. Implement `BasePlatform`

Your `__init__.py` must extend `BasePlatform` and implement all four methods:

```python
from src.platforms.base import BasePlatform

STATE_PATH = CONFIGS_DIR / "_state.enc"

class YourPlatform(BasePlatform):

    async def login(self, page: Page) -> None:
        # Open the site, let user log in manually,
        # then save encrypted session to STATE_PATH
        ...

    def build_search_url(self, preferences: dict) -> list[str]:
        # Return [one_url] for job or internship
        # Return [job_url, internship_url] when looking_for == "both"
        ...

    async def scrape_jobs(self, page: Page, search_url: str) -> list[dict]:
        # Navigate, extract job cards, return list of dicts
        ...

    async def apply(self, page, job, resume_summary, preferences_md, automation_mode) -> dict:
        # Fill and submit the form
        # Return: {"link", "title", "company", "status", "error", "raw_questions"}
        ...
```

### 3. Register in `agent.py`

```python
# src/core/agent.py

from src.platforms. import YourPlatform
from src.platforms. import STATE_PATH as YOUR_PLATFORM_STATE_PATH

PLATFORM_CLASSES = {
    "internshala": IntershalaPlatform,
    "naukri": NaukriPlatform,
    "": YourPlatform,            # ← add
}

PLATFORM_STATE_PATHS = {
    "internshala": INTERNSHALA_STATE_PATH,
    "naukri": NAUKRI_STATE_PATH,
    "": YOUR_PLATFORM_STATE_PATH, # ← add
}
```

### 4. Expose in the CLI

```python
# src/main.py

console.print("  [cyan]4[/cyan] — YourPlatform")

platform_map = {
    "1": ["internshala"],
    "2": ["naukri"],
    "3": ["internshala", "naukri"],
    "4": [""],                   # ← add
}
```

The scrape → filter → apply loop in `_run_single_platform` runs automatically for every registered platform — no other changes needed.

---

## Troubleshooting

**Agent searches wrong domain on Internshala**
The search URL is cached. Delete the cache and re-run:
```bash
rm data/user_profile_internshala.json
```

**`No apply or walkin button found` on Naukri**
The job has an `Apply on company site` button with a different selector. Check `src/platforms/naukri/selectors.py` and verify `COMPANY_SITE_BTN` matches the live site. The captured external URLs are saved to `external_links` in the DB.

**Log lines printing twice**
`logger.py` is missing `logger.propagate = False`. See `CHANGES.md` for the one-line fix.

**Login session expired mid-run**
Delete the encrypted state file for the affected platform and re-run — you will be prompted to log in again:
```bash
rm configs/internshala_state.enc
rm configs/naukri_state.enc
```

**Selectors stopped working after a site update**
Each `selectors.py` has a `# Last verified: YYYY-MM-DD` comment at the top. Open the site in Chrome DevTools, confirm current selectors, and update the file. No other code needs to change.

**CAPTCHA or rate limit triggered**
Increase delays in `src/utils/config.py`:
```python
ACTION_DELAY_MIN = 1.5    # default 0.5
ACTION_DELAY_MAX = 4.0    # default 2.0
```
Also consider reducing `max_pages` in the scraper and running fewer applications per session.

**LLM keeps failing JSON validation**
The system retries up to 3 times with a stricter prompt on each attempt. If it still fails, check `GEMINI_API_KEY` in `.env` and verify you haven't hit the free tier rate limit.