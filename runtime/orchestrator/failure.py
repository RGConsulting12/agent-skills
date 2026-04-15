"""Failure normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from runtime.models import ExecutionResult


@dataclass
class TaskFailure:
    """Normalized task failure record."""

    code: str
    message: str
    detail: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "message": self.message, "detail": self.detail}


def failure_from_result(result: ExecutionResult) -> TaskFailure:
    """Convert failed execution result to runtime failure payload."""
    return TaskFailure(
        code=result.error_code or "TASK_FAILED",
        message=result.error_message or result.summary,
        detail={
            "summary": result.summary,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": result.duration_ms,
        },
    )


def failure_from_exception(exc: Exception) -> TaskFailure:
    """Convert unexpected exception to structured runtime failure."""
    return TaskFailure(
        code="UNHANDLED_EXCEPTION",
        message=str(exc),
        detail={"type": exc.__class__.__name__},
    )

