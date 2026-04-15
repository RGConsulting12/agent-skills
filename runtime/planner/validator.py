"""Plan validation for Phase 1 runtime."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable

from runtime.models import Plan
from runtime.planner.dependency_graph import assert_acyclic
from runtime.schemas.loader import SchemaValidationError, validate_plan


class PlanValidationError(ValueError):
    """Raised when a plan is invalid."""


def _parse_datetime(value: str, field_name: str) -> None:
    """Validate ISO timestamp format."""
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PlanValidationError(f"{field_name} must be ISO8601 date-time") from exc


def _require_fields(data: Dict[str, Any], fields: Iterable[str], scope: str) -> None:
    for field in fields:
        if field not in data:
            raise PlanValidationError(f"missing required field '{field}' in {scope}")


def _validate_task(task: Dict[str, Any], index: int) -> None:
    scope = f"task[{index}]"
    _require_fields(task, ("task_id", "title", "execution"), scope)
    if not isinstance(task["task_id"], str) or not task["task_id"]:
        raise PlanValidationError(f"{scope}.task_id must be a non-empty string")
    if not isinstance(task["title"], str) or not task["title"]:
        raise PlanValidationError(f"{scope}.title must be a non-empty string")

    depends_on = task.get("depends_on", [])
    if not isinstance(depends_on, list) or not all(isinstance(item, str) for item in depends_on):
        raise PlanValidationError(f"{scope}.depends_on must be a list of strings")

    execution = task["execution"]
    if not isinstance(execution, dict):
        raise PlanValidationError(f"{scope}.execution must be an object")
    _require_fields(execution, ("kind",), f"{scope}.execution")
    if execution["kind"] not in {"noop", "shell", "delegate"}:
        raise PlanValidationError(f"{scope}.execution.kind must be noop, shell, or delegate")
    if execution["kind"] == "shell":
        command = execution.get("command")
        if not isinstance(command, str) or not command.strip():
            raise PlanValidationError(f"{scope}.execution.command must be set for shell tasks")
    if execution["kind"] == "delegate":
        delegation = execution.get("delegation")
        if not isinstance(delegation, dict):
            raise PlanValidationError(f"{scope}.execution.delegation must be an object")
        max_attempts = delegation.get("max_delegation_attempts")
        if not isinstance(max_attempts, int) or max_attempts < 1:
            raise PlanValidationError(
                f"{scope}.execution.delegation.max_delegation_attempts must be >= 1"
            )
    timeout = execution.get("timeout_seconds", 300)
    if not isinstance(timeout, int) or timeout < 1:
        raise PlanValidationError(f"{scope}.execution.timeout_seconds must be an integer >= 1")

    retry_policy = task.get("retry_policy", {})
    if not isinstance(retry_policy, dict):
        raise PlanValidationError(f"{scope}.retry_policy must be an object")
    max_retries = retry_policy.get("max_retries", 0)
    base = retry_policy.get("backoff_base_seconds", 1)
    factor = retry_policy.get("backoff_factor", 2.0)
    if not isinstance(max_retries, int) or max_retries < 0:
        raise PlanValidationError(f"{scope}.retry_policy.max_retries must be >= 0")
    if not isinstance(base, int) or base < 0:
        raise PlanValidationError(f"{scope}.retry_policy.backoff_base_seconds must be >= 0")
    if not isinstance(factor, (int, float)) or factor < 1:
        raise PlanValidationError(f"{scope}.retry_policy.backoff_factor must be >= 1")


def validate_plan_dict(plan_data: Dict[str, Any]) -> Plan:
    """Validate plan data and return typed plan.

    Validation has two layers:
    1. JSON Schema for structural and basic field constraints.
    2. Python semantic checks for cross-field rules.
    """
    try:
        validate_plan(plan_data)
    except SchemaValidationError:
        # Keep schema failures distinct so tests and callers can prove schema execution.
        raise

    _require_fields(
        plan_data,
        ("schema_version", "plan_id", "title", "created_at", "created_by", "tasks"),
        "plan",
    )
    if plan_data["schema_version"] != "1.0":
        raise PlanValidationError("schema_version must equal 1.0")
    if not isinstance(plan_data["tasks"], list) or not plan_data["tasks"]:
        raise PlanValidationError("tasks must be a non-empty array")

    _parse_datetime(str(plan_data["created_at"]), "created_at")

    task_ids = set()
    for index, task in enumerate(plan_data["tasks"]):
        if not isinstance(task, dict):
            raise PlanValidationError(f"task[{index}] must be an object")
        _validate_task(task, index)
        task_id = task["task_id"]
        if task_id in task_ids:
            raise PlanValidationError(f"duplicate task_id '{task_id}'")
        task_ids.add(task_id)

    for task in plan_data["tasks"]:
        for dependency in task.get("depends_on", []):
            if dependency not in task_ids:
                raise PlanValidationError(
                    f"task '{task['task_id']}' depends on unknown task '{dependency}'"
                )

    assert_acyclic(plan_data["tasks"])
    return Plan.from_dict(plan_data)


def load_and_validate_plan(plan_path: str) -> Plan:
    """Load plan JSON and validate it."""
    data = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    return validate_plan_dict(data)

