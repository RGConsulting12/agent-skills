"""Generic adapter behavior tests."""

from __future__ import annotations

import unittest

from runtime.adapters.generic_adapter import GenericAdapter
from runtime.models import ExecutionConfig, Plan, RetryPolicy, RunState, TaskDefinition, TaskRuntimeState, TaskApproval, now_iso


def build_run_state() -> RunState:
    return RunState(
        schema_version="1.0",
        run_id="run-adapter",
        plan_id="plan",
        status="running",
        created_at=now_iso(),
        started_at=now_iso(),
        ended_at=None,
        tasks={},
        artifacts=[],
    )


class AdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = GenericAdapter()
        self.run_state = build_run_state()

    def test_noop_success_and_artifact(self) -> None:
        task = TaskDefinition(
            task_id="T1",
            title="noop",
            execution=ExecutionConfig(kind="noop", emit_artifact={"type": "report", "content": {"ok": True}}),
            retry_policy=RetryPolicy(),
        )
        result = self.adapter.execute_task(task=task, run_state=self.run_state, attempt=1, trace_id="trace")
        self.assertTrue(result.ok)
        self.assertEqual(result.artifacts[0].type, "report")

    def test_shell_success(self) -> None:
        task = TaskDefinition(
            task_id="T1",
            title="shell",
            execution=ExecutionConfig(kind="shell", command="echo hello"),
            retry_policy=RetryPolicy(),
        )
        result = self.adapter.execute_task(task=task, run_state=self.run_state, attempt=1, trace_id="trace")
        self.assertTrue(result.ok)
        self.assertIn("hello", result.stdout or "")

    def test_shell_failure(self) -> None:
        task = TaskDefinition(
            task_id="T1",
            title="shell",
            execution=ExecutionConfig(kind="shell", command="bash -lc 'exit 7'"),
            retry_policy=RetryPolicy(),
        )
        result = self.adapter.execute_task(task=task, run_state=self.run_state, attempt=1, trace_id="trace")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "EXIT_NON_ZERO")

