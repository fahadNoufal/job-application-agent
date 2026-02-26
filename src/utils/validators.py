"""
src/utils/validators.py
Input validation helpers used during CLI collection.
"""

from typing import Optional


def validate_positive_int(value: str, field: str, max_val: int = 9999) -> int:
    try:
        n = int(value.strip())
        if n < 0:
            raise ValueError
        if n > max_val:
            raise ValueError(f"{field} cannot exceed {max_val}")
        return n
    except ValueError as e:
        raise ValueError(f"Invalid value for {field}: '{value}' — expected a non-negative integer.") from e


def validate_non_empty(value: str, field: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field} cannot be empty.")
    return stripped


def validate_choice(value: str, choices: list[str], field: str) -> str:
    v = value.strip().lower()
    choices_lower = {c.lower(): c for c in choices}
    if v not in choices_lower:
        raise ValueError(
            f"Invalid choice for {field}: '{value}'. Must be one of: {', '.join(choices)}"
        )
    return choices_lower[v]
