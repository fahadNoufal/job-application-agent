# 🤖 Autonomous Job Application Agent

An agentic system that automates the end-to-end job/internship application process using LangGraph, Playwright, and Gemini 1.5 Flash.

---

## Features

- ✅ CLI-driven setup with encrypted local storage
- ✅ LLM-powered domain classification and job filtering
- ✅ Automated form filling with contextual answer generation
- ✅ Idempotent — never re-applies to the same job
- ✅ Crash-recoverable — resumes from last checkpoint
- ✅ Human-like browser automation (randomized timing)
- ✅ SQLite application tracker with optional CSV export
- ✅ Platform-isolated architecture (Internshala active; LinkedIn/Wellfound extensible)

---

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo>
cd job-application-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and add your Gemini API key:
# GEMINI_API_KEY=your_key_here
# ENCRYPTION_KEY is auto-generated on first run
```

### 3. Run

```bash
python -m src.main
```

---

## Project Structure

```
src/
├── main.py                     # CLI entry point
├── core/
│   ├── agent.py                # LangGraph workflow (nodes + graph)
│   └── state.py                # Shared AgentState TypedDict
├── platforms/
│   ├── base.py                 # Abstract platform interface
│   └── internshala/
│       ├── __init__.py         # Platform implementation + URL builder
│       ├── scraper.py          # Job listing scraper
│       ├── applier.py          # Form-filling application logic
│       ├── selectors.py        # All CSS selectors (update here if site changes)
│       └── schemas.py          # Pydantic data models
├── browser/
│   ├── manager.py              # Playwright context + encrypted state
│   └── actions.py              # Human-like interaction helpers
├── llm/
│   ├── generator.py            # All Gemini API calls
│   ├── prompts.py              # All prompt templates
│   └── parsers.py              # JSON parsing + retry logic
├── storage/
│   ├── database.py             # Async SQLite (applications.db)
│   ├── resume_store.py         # Encrypted resume read/write
│   └── application_tracker.py # JSON checkpoint files
└── utils/
    ├── config.py               # Paths, env vars, encryption, constants
    ├── logger.py               # Rich console + file logging
    └── validators.py           # Input validation helpers
```

---

## Workflow (LangGraph)

```
load_data → build_url → resume_summary → login → scrape → filter → apply
```

Each stage checkpoints its output. If the process crashes, it resumes from the last completed stage automatically.

---

## Adding a New Platform

1. Create `src/platforms/<platform>/` directory
2. Implement `scraper.py`, `applier.py`, `selectors.py`, `schemas.py`
3. Create `__init__.py` extending `BasePlatform`
4. Register in `src/core/agent.py`

---

## Security

- Resume and browser session files are AES-encrypted with Fernet
- Sensitive files are excluded from Git via `.gitignore`
- Resume content is never logged

---

## Notes

- **Selectors**: If Internshala updates its UI, edit `src/platforms/internshala/selectors.py`
- **Rate limiting**: Default max is 20 applications/run; recommended 10–15
- **Gemini model**: Uses `gemini-1.5-flash` (fast and cost-effective)
- **LangGraph version**: Requires `>=0.2.0`
