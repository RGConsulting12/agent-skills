"""Task lifecycle transitions for Phase 1 runtime."""

from __future__ import annotations

from typing import Dict, Iterable, Set

from runtime.models import Plan, RunState, TaskDefinition, TaskRuntimeState, now_iso


TASK_TERMINAL_STATUSES: Set[str] = {"completed", "failed", "cancelled"}

_ALLOWED: Dict[str, Set[str]] = {
    "pending_approval": {"ready", "blocked", "cancelled"},
    "blocked": {"ready", "cancelled"},
    "ready": {"running", "cancelled"},
    "running": {"completed", "ready", "failed", "cancelled", "delegating"},
    "delegating": {"waiting_review", "ready", "failed", "cancelled"},
    "waiting_review": {"completed", "ready", "failed", "cancelled"},
    "failed": {"cancelled"},
    "completed": set(),
    "cancelled": set(),
}


class TransitionError(ValueError):
    """Raised when a status transition is invalid."""


def dependencies_completed(task_state: TaskRuntimeState, run_state: RunState) -> bool:
    """Check dependency completion status for a runtime task."""
    return all(run_state.tasks[dep].status == "completed" for dep in task_state.depends_on)


def initial_task_status(task: TaskDefinition) -> str:
    """Choose initial status from task approval/dependency requirements."""
    if task.approval_required:
        return "pending_approval"
    if task.depends_on:
        return "blocked"
    return "ready"


def can_transition(
    task_state: TaskRuntimeState, run_state: RunState, target_status: str
) -> tuple[bool, str]:
    """Return transition validity and reason."""
    current = task_state.status
    if target_status == current:
        return True, ""
    if target_status not in _ALLOWED.get(current, set()):
        return False, f"cannot transition {current} -> {target_status}"

    deps_ready = dependencies_completed(task_state, run_state)
    approved = (not task_state.approval.required) or task_state.approval.approved

    if current == "pending_approval" and target_status == "ready" and (not approved or not deps_ready):
        return False, "pending_approval -> ready requires approval and resolved dependencies"
    if current == "pending_approval" and target_status == "blocked" and not approved:
        return False, "pending_approval -> blocked requires approval first"
    if current == "blocked" and target_status == "ready" and (not approved or not deps_ready):
        return False, "blocked -> ready requires approval and resolved dependencies"
    if current == "ready" and target_status == "running" and (not approved or not deps_ready):
        return False, "ready -> running requires approval and resolved dependencies"
    return True, ""


def transition_task(
    run_state: RunState,
    task_id: str,
    target_status: str,
    *,
    set_started: bool = False,
    set_ended: bool = False,
) -> None:
    """Apply a checked transition to a task."""
    task_state = run_state.tasks[task_id]
    valid, reason = can_transition(task_state, run_state, target_status)
    if not valid:
        raise TransitionError(reason)
    task_state.status = target_status
    if set_started and task_state.started_at is None:
        task_state.started_at = now_iso()
    if set_ended:
        task_state.ended_at = now_iso()


def refresh_nonterminal_statuses(plan: Plan, run_state: RunState) -> None:
    """Recompute pending_approval/blocked/ready states after each update."""
    for task in plan.tasks:
        state = run_state.tasks[task.task_id]
        if state.status in TASK_TERMINAL_STATUSES or state.status in {
            "running",
            "delegating",
            "waiting_review",
        }:
            continue
        approved = (not state.approval.required) or state.approval.approved
        deps_ok = dependencies_completed(state, run_state)
        if not approved:
            state.status = "pending_approval"
        elif deps_ok:
            state.status = "ready"
        else:
            state.status = "blocked"


def summarize_tasks(run_state: RunState) -> Dict[str, int]:
    """Build deterministic status counts for run summary."""
    counts: Dict[str, int] = {
        "pending_approval": 0,
        "blocked": 0,
        "ready": 0,
        "running": 0,
        "delegating": 0,
        "waiting_review": 0,
        "completed": 0,
        "failed": 0,
        "cancelled": 0,
    }
    for task_state in run_state.tasks.values():
        counts[task_state.status] += 1
    return counts

