"""Dependency graph helpers for deterministic task scheduling."""

from __future__ import annotations

from typing import Dict, Iterable, List, Sequence

from runtime.models import Plan, RunState, TaskDefinition


def assert_acyclic(task_dicts: Sequence[dict]) -> None:
    """Raise ValueError when dependency cycle exists."""
    graph = {task["task_id"]: list(task.get("depends_on", [])) for task in task_dicts}
    visiting = set()
    visited = set()

    def visit(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            raise ValueError(f"dependency cycle detected at '{node}'")
        visiting.add(node)
        for dep in graph.get(node, []):
            visit(dep)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def dependencies_satisfied(task: TaskDefinition, run_state: RunState) -> bool:
    """True when all dependency tasks are completed."""
    for dep in task.depends_on:
        dep_state = run_state.tasks.get(dep)
        if dep_state is None or dep_state.status != "completed":
            return False
    return True


def task_index(plan: Plan) -> Dict[str, TaskDefinition]:
    """Return task index keyed by task_id."""
    return {task.task_id: task for task in plan.tasks}


def runnable_tasks(plan: Plan, run_state: RunState) -> List[TaskDefinition]:
    """Return ready tasks ordered deterministically by priority then task_id."""
    index = task_index(plan)
    candidates: List[TaskDefinition] = []
    for task_id, runtime_task in run_state.tasks.items():
        if runtime_task.status != "ready":
            continue
        task = index[task_id]
        if dependencies_satisfied(task, run_state):
            candidates.append(task)
    candidates.sort(key=lambda item: (-item.priority, item.task_id))
    return candidates


def select_next_task(plan: Plan, run_state: RunState) -> TaskDefinition | None:
    """Choose the next deterministic runnable task."""
    candidates = runnable_tasks(plan, run_state)
    return candidates[0] if candidates else None


def terminal_dependency_blocked(task: TaskDefinition, run_state: RunState) -> bool:
    """True when a task can never run because a dependency failed/cancelled."""
    for dep in task.depends_on:
        dep_status = run_state.tasks[dep].status
        if dep_status in {"failed", "cancelled"}:
            return True
    return False


def has_live_nonterminal_tasks(plan: Plan, run_state: RunState) -> bool:
    """True when non-terminal tasks can still make progress."""
    index = task_index(plan)
    for task in plan.tasks:
        state = run_state.tasks[task.task_id]
        if state.status in {"completed", "failed", "cancelled"}:
            continue
        if state.status in {"ready", "running", "pending_approval"}:
            return True
        if state.status == "blocked" and not terminal_dependency_blocked(index[task.task_id], run_state):
            return True
    return False

