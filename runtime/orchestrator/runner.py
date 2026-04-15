"""Plan runner for Phase 2A runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from runtime.adapters.host_adapter import HostAdapter
from runtime.delegation.manager import DelegationManager
from runtime.delegation.review import apply_review_decision
from runtime.models import (
    ActionApproval,
    DelegationRecord,
    DelegationRequest,
    Plan,
    RunState,
    TaskApproval,
    TaskRuntimeState,
    now_iso,
)
from runtime.observability.logger import TraceLogger
from runtime.observability.trace import make_event, new_trace_id, next_event_seq, next_span_id
from runtime.policy.engine import PolicyActionError, PolicyEngine
from runtime.orchestrator.failure import failure_from_exception, failure_from_result
from runtime.orchestrator.retry import backoff_seconds, should_retry
from runtime.planner.dependency_graph import has_live_nonterminal_tasks, select_next_task
from runtime.workspace.artifacts import create_artifact, persist_artifacts
from runtime.workspace.storage import StateStore
from runtime.workspace.transitions import (
    initial_task_status,
    refresh_nonterminal_statuses,
    summarize_tasks,
    transition_task,
)


class PlanRunner:
    """Executes typed plans using a host adapter."""

    def __init__(self, store: StateStore, logger: TraceLogger, adapter: HostAdapter) -> None:
        self.store = store
        self.logger = logger
        self.adapter = adapter
        self.policy = PolicyEngine()
        self.delegation_manager = DelegationManager()


@dataclass
class DelegationOutcome:
    """Outcome of inline child-run execution for delegation."""

    success: bool
    error_code: str | None = None
    error_message: str | None = None
    missing_outputs: List[str] | None = None

    def _emit_event(self, run_state: RunState, event_name: str, payload: dict | None = None) -> None:
        trace_id = run_state.metadata.setdefault("trace_id", new_trace_id())
        seq = next_event_seq(run_state.metadata)
        span_id = next_span_id(run_state.metadata)
        event = make_event(
            seq=seq,
            run_id=run_state.run_id,
            trace_id=trace_id,
            span_id=span_id,
            event=event_name,
            ts=now_iso(),
            payload=payload,
        )
        self.logger.log(run_state.run_id, event)
        # Persist sequence metadata eagerly to reduce duplicate seq risk on crash.
        self.store.save_run_state(run_state.run_id, run_state.to_dict())

    def init_run(self, plan: Plan, run_id: str) -> RunState:
        """Create initial typed run state."""
        task_states = {}
        for task in plan.tasks:
            task_states[task.task_id] = TaskRuntimeState(
                task_id=task.task_id,
                status=initial_task_status(task),
                attempts=0,
                max_retries=task.retry_policy.max_retries,
                last_error=None,
                approval=TaskApproval(required=task.approval_required),
                depends_on=list(task.depends_on),
                produced_artifacts=[],
            )
        run_state = RunState(
            schema_version="1.0",
            run_id=run_id,
            plan_id=plan.plan_id,
            status="initialized",
            created_at=now_iso(),
            started_at=None,
            ended_at=None,
            tasks=task_states,
            artifacts=[],
            summary={},
            metadata={"event_seq": 0, "span_counter": 0, "trace_id": new_trace_id()},
        )
        refresh_nonterminal_statuses(plan, run_state)
        run_state.summary = summarize_tasks(run_state)
        self.store.save_plan(run_id, plan.to_dict())
        self.store.save_artifacts(run_id, [])
        self._emit_event(run_state, "run_initialized", {"status": run_state.status})
        self.store.save_run_state(run_id, run_state.to_dict())
        return run_state

    def load_plan(self, run_id: str) -> Plan:
        """Load plan snapshot for run."""
        return Plan.from_dict(self.store.load_plan(run_id))

    def load_run_state(self, run_id: str) -> RunState:
        """Load run state."""
        return RunState.from_dict(self.store.load_run_state(run_id))

    def approve_task(self, run_id: str, task_id: str, approved_by: str) -> RunState:
        """Approve a task-level gate."""
        plan = self.load_plan(run_id)
        run_state = self.load_run_state(run_id)
        if task_id not in run_state.tasks:
            raise ValueError(f"unknown task_id '{task_id}'")
        task_state = run_state.tasks[task_id]
        if not task_state.approval.required:
            raise ValueError(f"task '{task_id}' does not require approval")
        if task_state.status in {"completed", "failed", "cancelled"}:
            raise ValueError(f"task '{task_id}' is terminal ({task_state.status})")
        # Idempotent behavior: repeated approval is accepted as no-op.
        if task_state.approval.approved:
            self._emit_event(
                run_state,
                "task_approval_idempotent",
                {"task_id": task_id, "approved_by": task_state.approval.approved_by},
            )
            self.store.save_run_state(run_id, run_state.to_dict())
            return run_state
        task_state.approval.approved = True
        task_state.approval.approved_by = approved_by
        task_state.approval.approved_at = now_iso()
        refresh_nonterminal_statuses(plan, run_state)
        run_state.summary = summarize_tasks(run_state)
        self._emit_event(run_state, "task_approved", {"task_id": task_id, "approved_by": approved_by})
        self.store.save_run_state(run_id, run_state.to_dict())
        return run_state

    def _update_run_status(self, plan: Plan, run_state: RunState, previous_status: str) -> None:
        states = [state.status for state in run_state.tasks.values()]
        if states and all(status == "completed" for status in states):
            run_state.status = "completed"
            run_state.ended_at = run_state.ended_at or now_iso()
        elif any(status in {"ready", "running"} for status in states):
            run_state.status = "running"
            run_state.ended_at = None
        elif any(status == "failed" for status in states):
            run_state.status = "failed"
            run_state.ended_at = run_state.ended_at or now_iso()
        elif not has_live_nonterminal_tasks(plan, run_state):
            run_state.status = "running"
            run_state.ended_at = None
        else:
            run_state.status = "running"
            run_state.ended_at = None
        if run_state.status != previous_status and run_state.status in {"completed", "failed"}:
            self._emit_event(run_state, f"run_{run_state.status}", {"status": run_state.status})

    def step(self, run_id: str) -> Tuple[RunState, bool]:
        """Execute a single schedulable task attempt."""
        plan = self.load_plan(run_id)
        run_state = self.load_run_state(run_id)
        if run_state.status in {"completed", "failed", "cancelled"}:
            return run_state, False

        previous_status = run_state.status
        if run_state.status == "initialized":
            run_state.status = "running"
            run_state.started_at = now_iso()

        refresh_nonterminal_statuses(plan, run_state)
        next_task = select_next_task(plan, run_state)
        if next_task is None:
            pending = sorted(task_id for task_id, task in run_state.tasks.items() if task.status == "pending_approval")
            if pending:
                self._emit_event(
                    run_state,
                    "task_waiting_approval",
                    {"task_id": pending[0], "status": "pending_approval"},
                )
            self._update_run_status(plan, run_state, previous_status)
            run_state.summary = summarize_tasks(run_state)
            self.store.save_run_state(run_id, run_state.to_dict())
            return run_state, False

        task_state = run_state.tasks[next_task.task_id]
        self._emit_event(
            run_state,
            "task_selected",
            {"task_id": next_task.task_id, "attempt": task_state.attempts + 1, "status": task_state.status},
        )
        transition_task(run_state, next_task.task_id, "running", set_started=True)
        task_state.attempts += 1
        run_state.current_task_id = next_task.task_id
        self._emit_event(
            run_state,
            "task_started",
            {"task_id": next_task.task_id, "attempt": task_state.attempts, "status": "running"},
        )

        artifacts = []
        try:
            result = self.adapter.execute_task(
                task=next_task,
                run_state=run_state,
                attempt=task_state.attempts,
                trace_id=str(run_state.metadata["trace_id"]),
            )
        except Exception as exc:  # pragma: no cover - defensive catch for adapter errors
            failure = failure_from_exception(exc)
            result = None
        else:
            failure = None

        if result is not None and result.ok:
            for payload in result.artifacts:
                artifacts.append(create_artifact(run_id, next_task.task_id, payload))
            persist_artifacts(self.store, run_state, next_task.task_id, artifacts)
            for artifact in artifacts:
                self._emit_event(
                    run_state,
                    "artifact_created",
                    {
                        "task_id": next_task.task_id,
                        "artifact_id": artifact.artifact_id,
                        "artifact_type": artifact.type,
                    },
                )
            task_state.last_error = None
            transition_task(run_state, next_task.task_id, "completed", set_ended=True)
            self._emit_event(
                run_state,
                "task_completed",
                {"task_id": next_task.task_id, "attempt": task_state.attempts, "status": "completed"},
            )
        else:
            if failure is None:
                failure = failure_from_result(result)  # type: ignore[arg-type]
            task_state.last_error = failure.to_dict()
            if should_retry(task_state.attempts, task_state.max_retries):
                transition_task(run_state, next_task.task_id, "ready")
                backoff = backoff_seconds(
                    next_task.retry_policy.backoff_base_seconds,
                    next_task.retry_policy.backoff_factor,
                    task_state.attempts,
                )
                self._emit_event(
                    run_state,
                    "task_retry_scheduled",
                    {
                        "task_id": next_task.task_id,
                        "attempt": task_state.attempts,
                        "backoff_seconds": backoff,
                    },
                )
            else:
                transition_task(run_state, next_task.task_id, "failed", set_ended=True)
                self._emit_event(
                    run_state,
                    "task_failed",
                    {
                        "task_id": next_task.task_id,
                        "attempt": task_state.attempts,
                        "error_code": failure.code,
                        "error_message": failure.message,
                    },
                )

        run_state.current_task_id = None
        refresh_nonterminal_statuses(plan, run_state)
        self._update_run_status(plan, run_state, previous_status)
        run_state.summary = summarize_tasks(run_state)
        self.store.save_run_state(run_id, run_state.to_dict())
        return run_state, True

    def run_until_done(self, run_id: str, max_steps: int | None = None) -> RunState:
        """Execute until terminal status, max steps, or no schedulable progress."""
        steps = 0
        while True:
            run_state, progressed = self.step(run_id)
            steps += 1
            if run_state.status in {"completed", "failed", "cancelled"}:
                return run_state
            if max_steps is not None and steps >= max_steps:
                return run_state
            if not progressed:
                return run_state

