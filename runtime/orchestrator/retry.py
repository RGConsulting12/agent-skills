"""Retry helpers."""

from __future__ import annotations


def should_retry(current_attempt: int, max_retries: int) -> bool:
    """Return True when another attempt is allowed."""
    return current_attempt <= max_retries


def backoff_seconds(base_seconds: int, factor: float, current_attempt: int) -> float:
    """Calculate deterministic backoff for the next retry."""
    if base_seconds <= 0:
        return 0.0
    exponent = max(current_attempt - 1, 0)
    return float(base_seconds) * (float(factor) ** exponent)

