"""Runner integration tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime.adapters.generic_adapter import GenericAdapter
from runtime.models import ExecutionResult, Plan, TaskDefinition
from runtime.orchestrator.runner import PlanRunner
from runtime.planner.validator import validate_plan_dict
from runtime.observability.logger import TraceLogger
from runtime.workspace.storage import StateStore


def make_plan(tasks: list[dict]) -> Plan:
    payload = {
        "schema_version": "1.0",
        "plan_id": "plan-runner",
        "title": "runner",
        "description": "runner tests",
        "created_at": "2026-04-15T10:00:00Z",
        "created_by": "tester",
        "tasks": tasks,
    }
    return validate_plan_dict(payload)


class FlakyAdapter:
    """Fails first attempt and succeeds second attempt."""

    name = "flaky"

    def __init__(self) -> None:
        self.calls = 0

    def capabilities(self) -> dict:
        return {"execution_kinds": ["noop"]}

    def execute_task(self, *, task: TaskDefinition, run_state, attempt: int, trace_id: str) -> ExecutionResult:
        del task, run_state, trace_id
        self.calls += 1
        if attempt == 1:
            return ExecutionResult(ok=False, summary="failed once", error_code="ONCE", error_message="retry me")
        return ExecutionResult(ok=True, summary="ok")


class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.tmp.name) / "state"
        self.logs_dir = Path(self.tmp.name) / "logs"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def build_runner(self, adapter=None) -> PlanRunner:
        return PlanRunner(
            store=StateStore(str(self.state_dir)),
            logger=TraceLogger(str(self.logs_dir)),
            adapter=adapter or GenericAdapter(),
        )

    def test_scheduler_priority_then_id(self) -> None:
        plan = make_plan(
            [
                {"task_id": "T1", "title": "one", "priority": 1, "execution": {"kind": "noop"}},
                {"task_id": "T2", "title": "two", "priority": 2, "execution": {"kind": "noop"}},
            ]
        )
        runner = self.build_runner()
        runner.init_run(plan, "run1")
        run_state, progressed = runner.step("run1")
        self.assertTrue(progressed)
        self.assertEqual(run_state.tasks["T2"].status, "completed")
        self.assertEqual(run_state.tasks["T1"].status, "ready")

    def test_retry_then_success(self) -> None:
        plan = make_plan(
            [
                {
                    "task_id": "T1",
                    "title": "flaky",
                    "execution": {"kind": "noop"},
                    "retry_policy": {"max_retries": 1},
                }
            ]
        )
        runner = self.build_runner(adapter=FlakyAdapter())
        runner.init_run(plan, "run-retry")
        run_state, _ = runner.step("run-retry")
        self.assertEqual(run_state.tasks["T1"].status, "ready")
        self.assertEqual(run_state.tasks["T1"].attempts, 1)
        run_state, _ = runner.step("run-retry")
        self.assertEqual(run_state.tasks["T1"].status, "completed")
        self.assertEqual(run_state.tasks["T1"].attempts, 2)

    def test_exhausted_retry_marks_failed(self) -> None:
        plan = make_plan(
            [
                {
                    "task_id": "T1",
                    "title": "fail",
                    "execution": {"kind": "shell", "command": "bash -lc 'exit 1'"},
                    "retry_policy": {"max_retries": 1},
                }
            ]
        )
        runner = self.build_runner()
        runner.init_run(plan, "run-fail")
        runner.step("run-fail")
        run_state, _ = runner.step("run-fail")
        self.assertEqual(run_state.tasks["T1"].status, "failed")
        self.assertEqual(run_state.status, "failed")

    def test_run_completes_when_all_tasks_done(self) -> None:
        plan = make_plan([{"task_id": "T1", "title": "one", "execution": {"kind": "noop"}}])
        runner = self.build_runner()
        runner.init_run(plan, "run-complete")
        run_state = runner.run_until_done("run-complete")
        self.assertEqual(run_state.status, "completed")

    def test_waiting_for_approval_produces_no_progress(self) -> None:
        plan = make_plan(
            [
                {
                    "task_id": "T1",
                    "title": "approval",
                    "approval_required": True,
                    "execution": {"kind": "noop"},
                }
            ]
        )
        runner = self.build_runner()
        runner.init_run(plan, "run-approval")
        run_state, progressed = runner.step("run-approval")
        self.assertFalse(progressed)
        self.assertEqual(run_state.tasks["T1"].status, "pending_approval")
        run_state = runner.approve_task("run-approval", "T1", "human")
        self.assertEqual(run_state.tasks["T1"].status, "ready")

    def test_artifacts_persist(self) -> None:
        plan = make_plan(
            [
                {
                    "task_id": "T1",
                    "title": "artifact",
                    "execution": {
                        "kind": "noop",
                        "emit_artifact": {"type": "report", "content": {"value": 1}},
                    },
                }
            ]
        )
        runner = self.build_runner()
        runner.init_run(plan, "run-artifacts")
        run_state = runner.run_until_done("run-artifacts")
        self.assertEqual(len(run_state.artifacts), 1)
        stored = runner.store.load_artifacts("run-artifacts")
        self.assertEqual(stored[0]["type"], "report")

    def test_trace_ordering_is_deterministic(self) -> None:
        plan = make_plan([{"task_id": "T1", "title": "one", "execution": {"kind": "noop"}}])
        runner = self.build_runner()
        runner.init_run(plan, "run-trace")
        runner.run_until_done("run-trace")
        events = TraceLogger(str(self.logs_dir)).read_tail("run-trace", tail=100)
        seqs = [event["seq"] for event in events]
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(len(seqs), len(set(seqs)))

