"""
src/utils/logger.py
Structured logging: file per run + rich console output.
Logs filename and line number for each message.
"""

import logging
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

from src.utils.config import LOGS_DIR

console = Console()

# Track which loggers have been initialized
_initialized_loggers = set()


def get_logger(name: str = "agent") -> logging.Logger:
    """
    Returns a logger with Rich console + file logging.
    Automatically includes filename and line number.
    Safe to call multiple times for the same logger name.
    """
    logger = logging.getLogger(name)

    if name in _initialized_loggers:
        return logger

    logger.setLevel(logging.DEBUG)

    # ── Console handler (INFO+) ──────────────────────────────────────────────
    console_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=True,     # Shows filename in console
        markup=True,
        rich_tracebacks=True,
    )
    console_handler.setLevel(logging.INFO)

    # ── File handler (DEBUG+) ───────────────────────────────────────────────
    log_file = LOGS_DIR / f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_run.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s"
        )
    )

    # Add handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    # Mark logger as initialized
    _initialized_loggers.add(name)

    return logger