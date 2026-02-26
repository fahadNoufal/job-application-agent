"""
src/llm/parsers.py
Safe JSON parsing with retry support.
"""

import json
import re
from typing import Any

from src.utils.logger import get_logger

logger = get_logger("parsers")


def _strip_code_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers if present."""
    text = text.strip()
    # Remove ```json or ``` at start
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    # Remove ``` at end
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_json_safe(text: str, expected_type: type = list) -> Any:
    """
    Try to parse JSON from LLM output.
    Returns parsed object or raises ValueError.
    """
    cleaned = _strip_code_fences(text)
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        # Try to extract first JSON array or object
        if expected_type is list:
            match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        else:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)

        if match:
            try:
                result = json.loads(match.group(0))
            except json.JSONDecodeError:
                raise ValueError(f"Could not parse JSON from LLM output: {e}\nRaw: {text[:300]}")
        else:
            raise ValueError(f"No JSON found in LLM output: {e}\nRaw: {text[:300]}")

    if not isinstance(result, expected_type):
        raise ValueError(
            f"Expected {expected_type.__name__}, got {type(result).__name__}. Raw: {text[:300]}"
        )

    return result


def validate_link_list(parsed: list) -> list[str]:
    """Ensure parsed list contains only string URLs."""
    print(parsed)
    valid = []
    for item in parsed:
        if isinstance(item, str) and item.startswith("http"):
            valid.append(item)
        else:
            logger.warning(f"Non-URL item in link list, skipping: {item}")
    return valid


def validate_answer_list(parsed: list, expected_count: int) -> list[dict]:
    """Ensure answers list matches expected question count."""
    if len(parsed) != expected_count:
        raise ValueError(
            f"Answer count mismatch: got {len(parsed)}, expected {expected_count}"
        )
    for item in parsed:
        if "question_id" not in item or "answer" not in item:
            raise ValueError(f"Answer item missing required keys: {item}")
    return parsed
