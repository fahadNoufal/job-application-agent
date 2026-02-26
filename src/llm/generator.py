"""
src/llm/generator.py
All Gemini API interactions. Single responsibility: call LLM, retry on bad output.
"""

import json
from google import genai

from src.utils.config import GEMINI_API_KEY, GEMINI_MODEL, LLM_RETRY_LIMIT
from src.utils.logger import get_logger
from src.llm.prompts import (
    DOMAIN_CLASSIFICATION_PROMPT,
    RESUME_SUMMARY_PROMPT,
    JOB_FILTER_PROMPT,
    APPLICATION_ANSWER_PROMPT,
    STRICT_JSON_RETRY_PROMPT,
)
from src.llm.parsers import (
    parse_json_safe,
    validate_link_list,
    validate_answer_list,
)

logger = get_logger("llm")

client = genai.Client(api_key=GEMINI_API_KEY,vertexai=False)


def _call(prompt: str) -> str:
    """Raw LLM call. Returns text response."""
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt    
    )
    return response.text.strip()


def _call_with_json_retry(
    prompt: str,
    validator_fn,
    schema_description: str,
    task_description: str,
    expected_type: type = list,
    **validator_kwargs,
) -> any:
    """
    Call LLM and retry up to LLM_RETRY_LIMIT times if JSON validation fails.
    """
    last_error = None
    current_prompt = prompt

    for attempt in range(1, LLM_RETRY_LIMIT + 1):
        try:
            raw = _call(current_prompt)
            parsed = parse_json_safe(raw, expected_type=expected_type)
            return validator_fn(parsed, **validator_kwargs)
        except ValueError as e:
            last_error = e
            logger.warning(f"LLM JSON validation failed (attempt {attempt}/{LLM_RETRY_LIMIT}): {e}")
            current_prompt = STRICT_JSON_RETRY_PROMPT.format(
                original_task=task_description,
                schema_description=schema_description,
            )

    raise RuntimeError(
        f"LLM failed to produce valid JSON after {LLM_RETRY_LIMIT} attempts. "
        f"Last error: {last_error}"
    )


# ── Public API ────────────────────────────────────────────────────────────────

def classify_domain(role: str) -> str:
    """Classify a job role into one of the allowed Internshala domains."""
    prompt = DOMAIN_CLASSIFICATION_PROMPT.format(role=role)
    result = _call(prompt).strip().strip('"').strip("'")
    logger.debug(f"Domain classification for '{role}': {result}")
    return result


def generate_resume_summary(resume_text: str) -> str:
    """Generate a concise resume summary for use in application prompts."""
    prompt = RESUME_SUMMARY_PROMPT.format(resume=resume_text)
    summary = _call(prompt)
    logger.info("Resume summary generated.")
    return summary


def filter_jobs(jobs_batch: list[dict], preferences_md: str) -> list[str]:
    """
    Given a batch of jobs and user preferences, return list of matching job links.
    """
    prompt = JOB_FILTER_PROMPT.format(
        preferences=preferences_md,
        jobs_json=json.dumps(jobs_batch, indent=2),
    )
    
    return _call_with_json_retry(
        prompt=prompt,
        validator_fn=validate_link_list,
        schema_description='Array of URL strings e.g. ["https://..."]',
        task_description="Return matching job links as a JSON array of strings.",
    )


def generate_answers(
    questions: list[dict],
    resume_summary: str,
    preferences_md: str,
    job_title: str,
    company: str,
    description: str,
) -> list[dict]:
    """
    Generate form answers for a given job's application questions.
    """
    prompt = APPLICATION_ANSWER_PROMPT.format(
        resume_summary=resume_summary,
        job_title=job_title,
        company=company,
        description=description,
        preferences_md=preferences_md,
        questions_json=json.dumps(questions, indent=2),
    )
    return _call_with_json_retry(        
        prompt=prompt,
        validator_fn=validate_answer_list,
        schema_description='Array of {question_id, answer} objects',
        task_description="Generate answers for each application question as a JSON array.",
        expected_count=len(questions),
    )
