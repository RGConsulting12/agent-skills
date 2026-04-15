"""Task transition rule tests."""

from __future__ import annotations

import unittest

from runtime.models import RunState, TaskApproval, TaskRuntimeState, now_iso
from runtime.workspace.transitions import TransitionError, refresh_nonterminal_statuses, transition_task


def build_run_state() -> RunState:
    return RunState(
        schema_version="1.0",
        run_id="run-transitions",
        plan_id="plan",
        status="running",
        created_at=now_iso(),
        started_at=now_iso(),
        ended_at=None,
        tasks={
            "T1": TaskRuntimeState(
                task_id="T1",
                status="completed",
                attempts=1,
                max_retries=0,
                last_error=None,
                approval=TaskApproval(required=False, approved=False),
                depends_on=[],
            ),
            "T2": TaskRuntimeState(
                task_id="T2",
                status="pending_approval",
                attempts=0,
                max_retries=0,
                last_error=None,
                approval=TaskApproval(required=True, approved=False),
                depends_on=["T1"],
            ),
            "T3": TaskRuntimeState(
                task_id="T3",
                status="blocked",
                attempts=0,
                max_retries=0,
                last_error=None,
                approval=TaskApproval(required=False, approved=False),
                depends_on=["T2"],
            ),
        },
        artifacts=[],
        summary={},
        metadata={},
    )


class TransitionTests(unittest.TestCase):
    def test_pending_approval_to_ready_requires_approval(self) -> None:
        run_state = build_run_state()
        with self.assertRaises(TransitionError):
            transition_task(run_state, "T2", "ready")

    def test_blocked_to_ready_requires_dependencies(self) -> None:
        run_state = build_run_state()
        with self.assertRaises(TransitionError):
            transition_task(run_state, "T3", "ready")

    def test_ready_to_completed_is_invalid(self) -> None:
        run_state = build_run_state()
        run_state.tasks["T2"].approval.approved = True
        refresh_nonterminal_statuses(
            type("PlanStub", (), {"tasks": []})(),  # not used for this assertion path
            run_state,
        )
        run_state.tasks["T2"].status = "ready"
        with self.assertRaises(TransitionError):
            transition_task(run_state, "T2", "completed")

    def test_completed_is_terminal(self) -> None:
        run_state = build_run_state()
        with self.assertRaises(TransitionError):
            transition_task(run_state, "T1", "running")

