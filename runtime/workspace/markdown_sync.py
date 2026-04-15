"""One-way markdown rendering from typed run state."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Dict

from runtime.models import Plan, RunState


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", suffix=".md", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def render_plan_markdown(plan: Plan, run_state: RunState, output_dir: str = ".") -> Path:
    """Render plan.md from typed state."""
    path = Path(output_dir) / "tasks" / "plan.md"
    lines = [
        f"# Plan: {plan.title}",
        "",
        f"- plan_id: `{plan.plan_id}`",
        f"- run_id: `{run_state.run_id}`",
        f"- status: `{run_state.status}`",
        "",
        "## Tasks",
        "",
    ]
    for task in plan.tasks:
        state = run_state.tasks[task.task_id]
        approval_actor = state.approval.approved_by or "n/a"
        approval_ts = state.approval.approved_at or "n/a"
        if state.last_error:
            err_code = state.last_error.get("code", "UNKNOWN")
            err_message = state.last_error.get("message", "")
            last_error = f"{err_code}: {err_message}".strip()
        else:
            last_error = "none"
        produced = ", ".join(state.produced_artifacts) if state.produced_artifacts else "none"
        lines.extend(
            [
                f"### {task.task_id} — {task.title}",
                f"- status: `{state.status}`",
                f"- priority: `{task.priority}`",
                f"- depends_on: `{', '.join(task.depends_on) if task.depends_on else 'none'}`",
                f"- approval_required: `{task.approval_required}`",
                f"- approved_by: `{approval_actor}`",
                f"- approved_at: `{approval_ts}`",
                f"- attempts: `{state.attempts}` / retries `{state.max_retries}`",
                f"- last_error: `{last_error}`",
                f"- produced_artifacts: `{produced}`",
                "",
            ]
        )
    _atomic_write_text(path, "\n".join(lines).rstrip() + "\n")
    return path


def render_todo_markdown(plan: Plan, run_state: RunState, output_dir: str = ".") -> Path:
    """Render todo.md from typed state."""
    path = Path(output_dir) / "tasks" / "todo.md"
    lines = [
        f"# Todo: {plan.title}",
        "",
    ]
    for task in sorted(plan.tasks, key=lambda item: (-item.priority, item.task_id)):
        state = run_state.tasks[task.task_id]
        box = "x" if state.status == "completed" else " "
        approval_note = ""
        if state.approval.required:
            if state.approval.approved:
                approval_note = (
                    f", approved by {state.approval.approved_by or 'unknown'}"
                    f" at {state.approval.approved_at or 'unknown'}"
                )
            else:
                approval_note = ", approval pending"
        if state.last_error:
            err_code = state.last_error.get("code", "UNKNOWN")
            err_message = state.last_error.get("message", "")
            error_note = f", error={err_code}: {err_message}".strip()
        else:
            error_note = ""
        artifacts_note = (
            f", artifacts={','.join(state.produced_artifacts)}" if state.produced_artifacts else ""
        )
        lines.append(
            f"- [{box}] `{task.task_id}` {task.title} ({state.status}{approval_note}{error_note}{artifacts_note})"
        )
    lines.append("")
    _atomic_write_text(path, "\n".join(lines))
    return path

