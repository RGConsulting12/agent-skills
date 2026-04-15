"""JSON Schema helpers for runtime structure enforcement."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from jsonschema import Draft202012Validator, RefResolver
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError


class SchemaValidationError(ValueError):
    """Raised when runtime payload fails JSON Schema validation."""


def _schema_dir() -> Path:
    return Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def _plan_validator() -> Draft202012Validator:
    """Build plan validator with local schema references enabled."""
    schema_dir = _schema_dir()
    plan_schema = json.loads((schema_dir / "plan.schema.json").read_text(encoding="utf-8"))
    store: Dict[str, Dict[str, Any]] = {}
    for name in ("task.schema.json", "plan.schema.json"):
        path = schema_dir / name
        store[name] = json.loads(path.read_text(encoding="utf-8"))
    resolver = RefResolver(base_uri=f"file://{schema_dir}/", referrer=plan_schema, store=store)
    return Draft202012Validator(plan_schema, resolver=resolver)


@lru_cache(maxsize=1)
def _artifact_validator() -> Draft202012Validator:
    schema = json.loads((_schema_dir() / "artifact.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


@lru_cache(maxsize=1)
def _run_state_validator() -> Draft202012Validator:
    schema = json.loads((_schema_dir() / "run_state.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _raise_schema_error(prefix: str, err: JsonSchemaValidationError) -> None:
    location = ".".join([str(item) for item in err.path])
    where = f" at {location}" if location else ""
    raise SchemaValidationError(f"{prefix} schema validation failed{where}: {err.message}")


def validate_plan_schema(payload: Dict[str, Any]) -> None:
    """Validate plan payload against JSON Schema."""
    validator = _plan_validator()
    errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
    if errors:
        _raise_schema_error("plan", errors[0])


def validate_artifact_schema(payload: Dict[str, Any]) -> None:
    """Validate a single artifact payload against JSON Schema."""
    validator = _artifact_validator()
    errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
    if errors:
        _raise_schema_error("artifact", errors[0])


def validate_run_state_schema(payload: Dict[str, Any]) -> None:
    """Validate run state payload against JSON Schema."""
    validator = _run_state_validator()
    errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
    if errors:
        _raise_schema_error("run_state", errors[0])

