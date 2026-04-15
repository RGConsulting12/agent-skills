"""Phase 2B reconciliation determinism and idempotency tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.adapters.generic_adapter import GenericAdapter
from runtime.models import ActionApproval, DelegationRecord, TaskRuntimeState, TaskApproval
from runtime.observability.logger import TraceLogger
from runtime.orchestrator.runner import PlanRunner
from runtime.planner.validator import validate_plan_dict
from runtime.workspace.storage import StateStore


def _plan_payload() -> dict:
    return {
        "schema_version": "1.0",
        "plan_id": "plan-p2b-rec",
        "title": "p2b reconcile",
        "created_at": "2026-04-15T10:00:00Z",
        "created_by": "tester",
        "tasks": [
            {
                "task_id": "T1",
                "title": "delegate",
                "execution": {
                    "kind": "delegate",
                    "delegation": {
                        "objective": "make report",
                        "copy_in_paths": [],
                        "tool_allowlist": ["noop", "shell"],
                        "path_allowlist": ["runtime/examples"],
                        "path_denylist": [],
                        "max_steps": 1,
                        "timeout_seconds": 30,
                        "expected_artifact_types": ["report"],
                        "max_delegation_attempts": 2,
                        "review_required": True,
                    },
                },
            }
        ],
    }


class ReconcileTests(unittest.TestCase):
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

    def test_reconcile_repairs_missing_delegation_index(self) -> None:
        plan = validate_plan_dict(_plan_payload())
        self.runner.init_run(plan, "run-rec-1")
        run_state, _ = self.runner.step("run-rec-1")
        delegation_id = run_state.tasks["T1"].active_delegation_id
        self.assertIsNotNone(delegation_id)

        # Corrupt run_state: remove delegation map + task pointer data.
        stored = self.runner.store.load_run_state("run-rec-1")
        stored["delegations"] = {}
        stored["tasks"]["T1"]["delegation_ids"] = []
        stored["tasks"]["T1"]["active_delegation_id"] = None
        self.runner.store.save_run_state("run-rec-1", stored)

        repaired, result = self.runner.reconcile("run-rec-1")
        self.assertGreater(int(result.get("repairs_applied", 0)), 0)
        self.assertIn(delegation_id, repaired.delegations)
        self.assertIn(delegation_id, repaired.tasks["T1"].delegation_ids)
        self.assertEqual(repaired.tasks["T1"].active_delegation_id, delegation_id)

    def test_reconcile_is_idempotent(self) -> None:
        plan = validate_plan_dict(_plan_payload())
        self.runner.init_run(plan, "run-rec-2")
        self.runner.step("run-rec-2")
        _, first = self.runner.reconcile("run-rec-2")
        _, second = self.runner.reconcile("run-rec-2")
        self.assertEqual(int(second.get("repairs_applied", 0)), 0)
        self.assertGreaterEqual(len(second.get("warnings", [])), 0)
        # First may be zero or more depending on current state, but second must be stable.
        self.assertGreaterEqual(int(first.get("repairs_applied", 0)), 0)

    def test_reconcile_multi_active_picks_lexicographic(self) -> None:
        plan = validate_plan_dict(_plan_payload())
        self.runner.init_run(plan, "run-rec-3")
        run_state = self.runner.load_run_state("run-rec-3")
        task_state = run_state.tasks["T1"]
        task_state.status = "waiting_review"

        base_req = {
            "objective": "x",
            "input_artifact_ids": [],
            "copy_in_paths": [],
            "tool_allowlist": ["noop"],
            "path_allowlist": ["runtime/examples"],
            "path_denylist": [],
            "max_steps": 1,
            "timeout_seconds": 10,
            "expected_artifact_types": ["report"],
            "review_required": True,
        }
        d1 = {
            "delegation_id": "dlg-bbbbbbbbbbbb",
            "parent_run_id": "run-rec-3",
            "parent_task_id": "T1",
            "lineage_depth": 1,
            "child_run_id": "run-rec-3--child-bbbbbbbbbbbb",
            "status": "running",
            "request": base_req,
            "result": None,
            "review": {"decision": None, "reviewed_by": None, "reviewed_at": None, "notes": None},
            "workspace_dir": "",
            "artifacts_copied_back": [],
            "created_at": "2026-04-15T10:00:00Z",
            "updated_at": "2026-04-15T10:00:00Z",
        }
        d2 = dict(d1)
        d2["delegation_id"] = "dlg-aaaaaaaaaaaa"
        d2["child_run_id"] = "run-rec-3--child-aaaaaaaaaaaa"

        self.runner.store.save_delegation("run-rec-3", d1)
        self.runner.store.save_delegation("run-rec-3", d2)
        run_state.tasks["T1"].delegation_ids = [d1["delegation_id"], d2["delegation_id"]]
        run_state.tasks["T1"].active_delegation_id = d1["delegation_id"]
        run_state.delegations = {
            d1["delegation_id"]: DelegationRecord.from_dict(d1),
            d2["delegation_id"]: DelegationRecord.from_dict(d2),
        }
        self.runner.store.save_run_state("run-rec-3", run_state.to_dict())

        repaired, result = self.runner.reconcile("run-rec-3")
        self.assertEqual(repaired.tasks["T1"].active_delegation_id, "dlg-aaaaaaaaaaaa")
        self.assertTrue(
            any(
                "multiple active delegation candidates" in item
                for item in result.get("warnings", [])
            )
        )

