"""Phase 2A delegation flow tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.adapters.generic_adapter import GenericAdapter
from runtime.models import ChildRunState, ExecutionResult, now_iso
from runtime.observability.logger import TraceLogger
from runtime.orchestrator.runner import PlanRunner
from runtime.planner.validator import validate_plan_dict
from runtime.workspace.storage import StateStore


def phase2a_plan() -> dict:
    return {
        "schema_version": "1.0",
        "plan_id": "plan-p2a",
        "title": "Phase 2A delegation",
        "created_at": "2026-04-16T10:00:00Z",
        "created_by": "tester",
        "tasks": [
            {
                "task_id": "T1",
                "title": "Delegate artifact production",
                "execution": {
                    "kind": "delegate",
                    "delegation": {
                        "objective": "produce delegated report",
                        "copy_in_paths": [],
                        "tool_allowlist": ["noop", "shell"],
                        "path_allowlist": ["/workspace/runtime/examples"],
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


class DelegationFlowTests(unittest.TestCase):
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

    def test_delegate_then_review_accept(self) -> None:
        plan = validate_plan_dict(phase2a_plan())
        self.runner.init_run(plan, "run-p2a")
        run_state, progressed = self.runner.step("run-p2a")
        self.assertTrue(progressed)
        self.assertEqual(run_state.tasks["T1"].status, "waiting_review")
        self.assertEqual(run_state.summary["waiting_review"], 1)
        delegation_id = run_state.tasks["T1"].active_delegation_id
        self.assertIsNotNone(delegation_id)

        draft_artifacts = [
            a
            for a in self.runner.store.load_artifacts("run-p2a")
            if a.get("producer_delegation_id") == delegation_id
        ]
        self.assertTrue(draft_artifacts)
        self.assertTrue(all(a["status"] == "draft" for a in draft_artifacts))

        self.runner.approve_action(
            "run-p2a",
            category="delegation_accept",
            target_id=delegation_id,
            approved_by="security",
        )
        self.runner.review_delegation(
            "run-p2a",
            delegation_id,
            decision="accepted",
            reviewed_by="reviewer",
            notes="ok",
        )
        run_state = self.runner.load_run_state("run-p2a")
        self.assertEqual(run_state.tasks["T1"].status, "completed")
        final_artifacts = [
            a
            for a in self.runner.store.load_artifacts("run-p2a")
            if a.get("producer_delegation_id") == delegation_id
        ]
        self.assertTrue(all(a["status"] == "final" for a in final_artifacts))

    def test_missing_required_outputs_fails_attempt(self) -> None:
        plan = validate_plan_dict(phase2a_plan())
        self.runner.init_run(plan, "run-missing")

        def fake_child(_task, request, *, child_run_id: str, parent_run_id: str):
            child = ChildRunState(
                child_run_id=child_run_id,
                parent_run_id=parent_run_id,
                parent_task_id="T1",
                status="completed",
                created_at=now_iso(),
                started_at=now_iso(),
                ended_at=now_iso(),
                max_steps=request.max_steps,
                steps_executed=1,
                timeout_seconds=request.timeout_seconds,
                tasks={},
                artifacts=[],
                last_error=None,
            )
            # Successful child run with no outputs should trigger
            # DELEGATION_MISSING_OUTPUTS in parent bookkeeping.
            return child, ExecutionResult(ok=True, summary="child success", artifacts=[])

        with patch("runtime.delegation.service.run_child_inline", side_effect=fake_child):
            run_state, _ = self.runner.step("run-missing")
        self.assertEqual(run_state.tasks["T1"].status, "ready")
        self.assertEqual(run_state.tasks["T1"].delegation_attempts, 1)
        self.assertIn("DELEGATION_MISSING_OUTPUTS", run_state.tasks["T1"].last_error["code"])

    def test_active_delegation_reentry_rejected(self) -> None:
        plan = validate_plan_dict(phase2a_plan())
        self.runner.init_run(plan, "run-reentry")
        run_state, _ = self.runner.step("run-reentry")
        delegation_id = run_state.tasks["T1"].active_delegation_id
        with self.assertRaises(ValueError):
            self.runner.delegation_service.start_delegation(
                plan=plan,
                run_state=run_state,
                task=plan.tasks[0],
                trace_emitter=lambda _event, _payload=None: None,
            )
        self.assertIsNotNone(delegation_id)

    def test_reject_exhaustion_deterministic(self) -> None:
        payload = phase2a_plan()
        payload["tasks"][0]["execution"]["delegation"]["max_delegation_attempts"] = 1
        plan = validate_plan_dict(payload)
        self.runner.init_run(plan, "run-exhaust")
        run_state, _ = self.runner.step("run-exhaust")
        delegation_id = run_state.tasks["T1"].active_delegation_id
        self.runner.review_delegation(
            "run-exhaust",
            delegation_id,
            decision="rejected",
            reviewed_by="reviewer",
            notes="nope",
        )
        run_state = self.runner.load_run_state("run-exhaust")
        self.assertEqual(run_state.tasks["T1"].status, "failed")
        self.assertEqual(run_state.delegations[delegation_id].status, "exhausted")
