"""
src/platforms/naukri/schemas.py
Pydantic models for Naukri scraped data.
"""

from typing import Optional
from pydantic import BaseModel


class NaukriJob(BaseModel):
    title: str
    company: str
    link: str
    location: Optional[str] = None
    salary_or_stipend: Optional[str] = None
    experience_or_duration: Optional[str] = None
    starts_in: Optional[str] = None
    description: Optional[str] = None
    platform: str = "naukri"


class ChatMessage(BaseModel):
    """A single turn in the Naukri chatbot conversation."""
    role: str            # "bot" | "user"
    question: str        # bot's question text
    options: list[str]   # available options (empty for free-text)
    answer: str          # answer given (or empty if bot message only)