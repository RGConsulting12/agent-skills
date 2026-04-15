"""Validation tests for plan schema and semantics."""

from __future__ import annotations

import copy
import unittest

from runtime.planner.validator import PlanValidationError, validate_plan_dict


def sample_plan() -> dict:
    return {
        "schema_version": "1.0",
        "plan_id": "plan-test",
        "title": "Validation Test Plan",
        "description": "test",
        "created_at": "2026-04-15T10:00:00Z",
        "created_by": "tester",
        "tasks": [
            {
                "task_id": "T1",
                "title": "one",
                "depends_on": [],
                "approval_required": False,
                "execution": {"kind": "noop"},
            },
            {
                "task_id": "T2",
                "title": "two",
                "depends_on": ["T1"],
                "approval_required": False,
                "execution": {"kind": "shell", "command": "echo hi"},
                "retry_policy": {"max_retries": 1},
            },
        ],
    }


class ValidatorTests(unittest.TestCase):
    def test_valid_plan_is_accepted(self) -> None:
        plan = validate_plan_dict(sample_plan())
        self.assertEqual(plan.plan_id, "plan-test")
        self.assertEqual(len(plan.tasks), 2)

    def test_missing_required_field_is_rejected(self) -> None:
        payload = sample_plan()
        del payload["plan_id"]
        with self.assertRaises(PlanValidationError):
            validate_plan_dict(payload)

    def test_unknown_dependency_is_rejected(self) -> None:
        payload = sample_plan()
        payload["tasks"][1]["depends_on"] = ["missing"]
        with self.assertRaises(PlanValidationError):
            validate_plan_dict(payload)

    def test_duplicate_task_id_is_rejected(self) -> None:
        payload = sample_plan()
        payload["tasks"][1]["task_id"] = "T1"
        with self.assertRaises(PlanValidationError):
            validate_plan_dict(payload)

    def test_cycle_is_rejected(self) -> None:
        payload = sample_plan()
        payload["tasks"].append(
            {
                "task_id": "T3",
                "title": "three",
                "depends_on": ["T2"],
                "execution": {"kind": "noop"},
            }
        )
        payload["tasks"][0]["depends_on"] = ["T3"]
        with self.assertRaises((PlanValidationError, ValueError)):
            validate_plan_dict(payload)

    def test_shell_requires_command(self) -> None:
        payload = sample_plan()
        payload["tasks"][1]["execution"] = {"kind": "shell"}
        with self.assertRaises(PlanValidationError):
            validate_plan_dict(payload)

    def test_retry_policy_bounds(self) -> None:
        payload = copy.deepcopy(sample_plan())
        payload["tasks"][1]["retry_policy"]["max_retries"] = -1
        with self.assertRaises(PlanValidationError):
            validate_plan_dict(payload)

