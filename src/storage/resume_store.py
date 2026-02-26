"""
src/storage/resume_store.py
Encrypted read/write for resume files.
"""

from pathlib import Path
from src.utils.config import (
    RESUME_RAW_PATH,
    RESUME_SUMMARY_PATH,
    encrypt,
    decrypt,
)


def save_resume(raw_text: str) -> None:
    """Encrypt and persist the raw resume."""
    RESUME_RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESUME_RAW_PATH.write_bytes(encrypt(raw_text))


def load_resume() -> str:
    """Decrypt and return the raw resume."""
    if not RESUME_RAW_PATH.exists():
        raise FileNotFoundError("Resume not found. Run the CLI setup first.")
    return decrypt(RESUME_RAW_PATH.read_bytes())


def save_resume_summary(summary: str) -> None:
    RESUME_SUMMARY_PATH.write_bytes(encrypt(summary))


def load_resume_summary() -> str:
    if not RESUME_SUMMARY_PATH.exists():
        raise FileNotFoundError("Resume summary not found. It will be generated on first run.")
    return decrypt(RESUME_SUMMARY_PATH.read_bytes())


def resume_summary_exists() -> bool:
    return RESUME_SUMMARY_PATH.exists()
