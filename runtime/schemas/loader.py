"""Schema loading and validation utilities for runtime."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from jsonschema.validators import RefResolver


class SchemaValidationError(ValueError):
    """Raised when a payload fails JSON schema validation."""


class SchemaRegistry:
    """Caches and applies JSON schema validators from runtime/schemas."""

    def __init__(self, schema_dir: str | None = None) -> None:
        base_dir = Path(schema_dir) if schema_dir else Path(__file__).resolve().parent
        self.schema_dir = base_dir
        self._schemas = {
            "plan": self._load("plan.schema.json"),
            "task": self._load("task.schema.json"),
            "artifact": self._load("artifact.schema.json"),
            "run_state": self._load("run_state.schema.json"),
            "delegation": self._load("delegation.schema.json"),
        }
        resolver = RefResolver(base_uri=self.schema_dir.as_uri() + "/", referrer=self._schemas["run_state"])
        self._validators = {
            "plan": Draft202012Validator(self._schemas["plan"], resolver=resolver),
            "task": Draft202012Validator(self._schemas["task"]),
            "artifact": Draft202012Validator(self._schemas["artifact"]),
            "run_state": Draft202012Validator(self._schemas["run_state"], resolver=resolver),
            "delegation": Draft202012Validator(self._schemas["delegation"]),
        }

    def _load(self, filename: str) -> Dict[str, Any]:
        path = self.schema_dir / filename
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def validate(self, schema_name: str, payload: Any) -> None:
        """Validate payload against a named schema and raise SchemaValidationError on failure."""
        validator = self._validators[schema_name]
        errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
        if not errors:
            return
        first = errors[0]
        raise SchemaValidationError(self._format_error(first))

    @staticmethod
    def _format_error(error: ValidationError) -> str:
        if error.path:
            path = ".".join(str(part) for part in error.path)
            return f"{path}: {error.message}"
        return error.message


_REGISTRY = SchemaRegistry()


def schema_registry() -> SchemaRegistry:
    """Return shared schema registry instance."""
    return _REGISTRY


def validate_plan(payload: Any) -> None:
    """Validate plan payload against plan schema."""
    _REGISTRY.validate("plan", payload)


def validate_artifact(payload: Any) -> None:
    """Validate artifact payload against artifact schema."""
    _REGISTRY.validate("artifact", payload)


def validate_run_state(payload: Any) -> None:
    """Validate run-state payload against run_state schema."""
    _REGISTRY.validate("run_state", payload)


def validate_delegation(payload: Any) -> None:
    """Validate delegation payload against delegation schema."""
    _REGISTRY.validate("delegation", payload)


def validate_task(payload: Any) -> None:
    """Validate task payload against task schema."""
    _REGISTRY.validate("task", payload)

