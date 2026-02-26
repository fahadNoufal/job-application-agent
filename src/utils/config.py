"""
src/utils/config.py
Central configuration. Loads .env and exposes typed settings.
Auto-generates an encryption key on first run.
"""

import os
import base64
from pathlib import Path
from dotenv import load_dotenv
from cryptography.fernet import Fernet

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"
CONFIGS_DIR = ROOT / "configs"

RESUMES_DIR = DATA_DIR / "resumes"
USER_PROFILE_PATH = DATA_DIR / "user_profile.json"
RAW_JOBS_PATH = DATA_DIR / "raw_jobs.json"
SHORTLISTED_JOBS_PATH = DATA_DIR / "shortlisted_jobs.json"
APPLICATIONS_DB_PATH = DATA_DIR / "applications.db"
PREFERENCES_PATH = DATA_DIR / "preferences.md"
RESUME_RAW_PATH = RESUMES_DIR / "resume.md"
RESUME_SUMMARY_PATH = RESUMES_DIR / "resume_summary.md"

INTERNSHALA_STATE_PATH = CONFIGS_DIR / "internshala_state.enc"

# ── Ensure directories exist ──────────────────────────────────────────────────
for d in [DATA_DIR, LOGS_DIR, CONFIGS_DIR, RESUMES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Load .env ─────────────────────────────────────────────────────────────────
load_dotenv(ROOT / ".env")

GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL: str = "gemini-2.5-flash-lite"

# ── Encryption ────────────────────────────────────────────────────────────────
_ENV_PATH = ROOT / ".env"


def _load_or_create_fernet() -> Fernet:
    """Load encryption key from .env or generate one and persist it."""
    key_str = os.environ.get("ENCRYPTION_KEY", "").strip()
    if key_str:
        try:
            return Fernet(key_str.encode())
        except Exception:
            pass

    # Generate a new key
    key = Fernet.generate_key()
    key_str = key.decode()

    # Write into .env (create if absent)
    env_path = _ENV_PATH
    if env_path.exists():
        content = env_path.read_text()
        if "ENCRYPTION_KEY=" in content:
            lines = [
                f"ENCRYPTION_KEY={key_str}" if l.startswith("ENCRYPTION_KEY=") else l
                for l in content.splitlines()
            ]
            env_path.write_text("\n".join(lines) + "\n")
        else:
            with env_path.open("a") as f:
                f.write(f"\nENCRYPTION_KEY={key_str}\n")
    else:
        env_path.write_text(f"GEMINI_API_KEY=\nENCRYPTION_KEY={key_str}\n")

    os.environ["ENCRYPTION_KEY"] = key_str
    return Fernet(key)


FERNET: Fernet = _load_or_create_fernet()


def encrypt(data: str) -> bytes:
    return FERNET.encrypt(data.encode())


def decrypt(data: bytes) -> str:
    return FERNET.decrypt(data).decode()


# ── Application limits ────────────────────────────────────────────────────────
MAX_APPLICATIONS_DEFAULT = 20
WARN_THRESHOLD_RATIO = 0.75      # warn at 75 % of user-set max
LLM_BATCH_SIZE = 10              # jobs per LLM filter call
LLM_RETRY_LIMIT = 3

# ── Human-like timing (seconds) ───────────────────────────────────────────────
TYPING_DELAY_MIN = 0.04
TYPING_DELAY_MAX = 0.12
ACTION_DELAY_MIN = 0.5
ACTION_DELAY_MAX = 2.0
PAGE_LOAD_WAIT = 3.0
