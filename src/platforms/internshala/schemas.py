"""
src/platforms/internshala/schemas.py
Pydantic schemas for Internshala scraped data and form questions.
"""

from typing import Optional
from pydantic import BaseModel, HttpUrl


class InternshalaJob(BaseModel):
    title: str
    company: str
    link: str
    location: Optional[str] = None
    stipend: Optional[str] = None
    duration: Optional[str] = None
    days_posted: Optional[str] = None
    description: Optional[str] = None
    experience: Optional[str] = None     # for jobs (not internships)
    platform: str = "internshala"


class FormQuestion(BaseModel):
    question_id: str
    label: str
    type: str           # text | textarea | radio | checkbox | select | availability | file
    options: list[str] = []
    required: bool = True
    selector: Optional[str] = None     # runtime selector for filling


class ApplicationAnswer(BaseModel):
    question_id: str
    answer: str | list[str]
