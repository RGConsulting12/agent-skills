"""Phase 2A workspace and policy tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.adapters.generic_adapter import GenericAdapter
from runtime.observability.logger import TraceLogger
from runtime.orchestrator.runner import PlanRunner
from runtime.planner.validator import validate_plan_dict
from runtime.workspace.storage import StateStore


def base_plan() -> dict:
    return {
        "schema_version": "1.0",
        "plan_id": "plan-ws",
        "title": "ws",
        "created_at": "2026-04-16T10:00:00Z",
        "created_by": "tester",
        "tasks": [
            {
                "task_id": "T1",
                "title": "delegate",
                "execution": {
                    "kind": "delegate",
                    "delegation": {
                        "objective": "produce delegated report",
                        "copy_in_paths": ["runtime/examples/sample-plan.json"],
                        "tool_allowlist": ["noop"],
                        "path_allowlist": ["runtime/examples"],
                        "path_denylist": [],
                        "max_steps": 2,
                        "timeout_seconds": 60,
                        "expected_artifact_types": ["report"],
                        "max_delegation_attempts": 2,
                        "review_required": True,
                    },
                },
            }
        ],
    }


class WorkspacePolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.tmp.name) / "state"
        self.logs_dir = Path(self.tmp.name) / "logs"
        self.runner = PlanRunner(
            store=StateStore(str(self.state_dir)),
            logger=TraceLogger(str(self.logs_dir)),
            adapter=GenericAdapter(),
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_copy_in_allowlist_enforced(self) -> None:
        payload = base_plan()
        payload["tasks"][0]["execution"]["delegation"]["copy_in_paths"] = ["/workspace/runtime/models.py"]
        plan = validate_plan_dict(payload)
        self.runner.init_run(plan, "run-pol")
        run_state, _ = self.runner.step("run-pol")
        self.assertEqual(run_state.tasks["T1"].status, "ready")
        self.assertEqual(run_state.tasks["T1"].last_error["code"], "DELEGATION_POLICY_DENIED")

    def test_action_approval_separate_from_task_approval(self) -> None:
        plan = validate_plan_dict(base_plan())
        self.runner.init_run(plan, "run-appr")
        run_state, _ = self.runner.step("run-appr")
        delegation_id = run_state.tasks["T1"].active_delegation_id
        with self.assertRaises(ValueError):
            self.runner.review_delegation(
                "run-appr",
                delegation_id,
                decision="accepted",
                reviewed_by="reviewer",
            )
        self.runner.approve_action(
            "run-appr",
            category="delegation_accept",
            target_id=delegation_id,
            approved_by="security",
        )
        self.runner.review_delegation(
            "run-appr",
            delegation_id,
            decision="accepted",
            reviewed_by="reviewer",
        )
        run_state = self.runner.load_run_state("run-appr")
        self.assertEqual(run_state.tasks["T1"].status, "completed")
