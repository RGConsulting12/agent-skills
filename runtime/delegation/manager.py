"""Delegation manager for runtime-managed Phase 2A child runs."""

from __future__ import annotations

import subprocess
import time
from typing import List

from runtime.models import (
    ArtifactCreateInput,
    ChildRunState,
    DelegationRecord,
    DelegationRequest,
    DelegationResult,
    ExecutionResult,
    now_iso,
)
class DelegationManager:
    """Runtime-managed delegation record helpers."""

    @staticmethod
    def start_delegation(
        *,
        run_state,
        task,
        trace_emitter,
    ) -> None:
        """Guardrail used by tests/runner for active delegation rejection.

        The full creation flow is handled in runner to keep orchestration centralized.
        This method enforces the invariant: one active delegation per parent task.
        """
        task_state = run_state.tasks[task.task_id]
        if task_state.active_delegation_id:
            raise ValueError(
                f"task '{task.task_id}' already has active delegation "
                f"'{task_state.active_delegation_id}'"
            )
        trace_emitter(
            "delegation_start_guard_passed",
            {"task_id": task.task_id},
        )


def build_review_result(
    request: DelegationRequest,
    child: ChildRunState,
    produced_artifact_ids: List[str],
) -> DelegationResult:
    """Build review-submitted result payload from successful child run."""
    return DelegationResult(
        status="submitted_for_review",
        summary="child completed",
        produced_artifact_ids=produced_artifact_ids,
        output_manifest={
            "child_run_id": child.child_run_id,
            "artifact_count": len(produced_artifact_ids),
        },
        evidence={"child_status": child.status, "last_error": child.last_error},
        submitted_at=now_iso(),
    )


def _child_task_id(task) -> str:
    return str((task.execution.delegation or {}).get("child_task_id", "CHILD_TASK"))


def _child_kind(task) -> str:
    return str((task.execution.delegation or {}).get("child_kind", "noop"))


def _child_command(task) -> str:
    return str((task.execution.delegation or {}).get("child_command", "")).strip()


def _child_omit_expected_outputs(task) -> bool:
    return bool((task.execution.delegation or {}).get("child_omit_expected_outputs", False))


def run_child_inline(task, request: DelegationRequest, *, child_run_id: str, parent_run_id: str) -> tuple[ChildRunState, ExecutionResult]:
    """Execute a minimal child run model inline (no detached workers)."""
    child = ChildRunState(
        child_run_id=child_run_id,
        parent_run_id=parent_run_id,
        parent_task_id=task.task_id,
        status="running",
        created_at=now_iso(),
        started_at=now_iso(),
        ended_at=None,
        max_steps=request.max_steps,
        steps_executed=0,
        timeout_seconds=request.timeout_seconds,
        tasks={},
        artifacts=[],
        last_error=None,
    )

    # Step accounting for deterministic max-step exhaustion
    child.steps_executed += 1
    if child.steps_executed > child.max_steps:
        child.status = "failed"
        child.ended_at = now_iso()
        child.last_error = {"code": "CHILD_MAX_STEP_EXHAUSTION", "message": "child max steps exceeded"}
        return child, ExecutionResult(
            ok=False,
            summary="child max steps exceeded",
            error_code="CHILD_MAX_STEP_EXHAUSTION",
            error_message="child max steps exceeded",
        )

    kind = _child_kind(task)
    if kind == "noop":
        if _child_omit_expected_outputs(task):
            artifacts = []
        else:
            artifacts = [
                ArtifactCreateInput(
                    type=artifact_type,
                    status="draft",
                    content={"summary": f"child produced {artifact_type}", "child_run_id": child.child_run_id},
                    metadata={"provisional": True},
                )
                for artifact_type in request.expected_artifact_types
            ]
        child.status = "completed"
        child.ended_at = now_iso()
        return child, ExecutionResult(ok=True, summary="child noop success", artifacts=artifacts)

    if kind == "shell":
        command = _child_command(task)
        if not command:
            child.status = "failed"
            child.ended_at = now_iso()
            child.last_error = {"code": "CHILD_TERMINAL_FAILURE", "message": "missing child command"}
            return child, ExecutionResult(
                ok=False,
                summary="child command missing",
                error_code="CHILD_TERMINAL_FAILURE",
                error_message="missing child command",
            )
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=".",
                capture_output=True,
                text=True,
                timeout=request.timeout_seconds,
                shell=True,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            child.status = "failed"
            child.ended_at = now_iso()
            child.last_error = {"code": "CHILD_TIMEOUT", "message": "child timed out"}
            return child, ExecutionResult(
                ok=False,
                summary="child timeout",
                stdout=exc.stdout,
                stderr=exc.stderr,
                error_code="CHILD_TIMEOUT",
                error_message="child timed out",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        duration_ms = int((time.monotonic() - started) * 1000)
        if completed.returncode != 0:
            child.status = "failed"
            child.ended_at = now_iso()
            child.last_error = {
                "code": "CHILD_TERMINAL_FAILURE",
                "message": f"exit code {completed.returncode}",
            }
            return child, ExecutionResult(
                ok=False,
                summary="child shell failed",
                stdout=completed.stdout,
                stderr=completed.stderr,
                error_code="CHILD_TERMINAL_FAILURE",
                error_message=f"exit code {completed.returncode}",
                duration_ms=duration_ms,
            )
        if _child_omit_expected_outputs(task):
            artifacts = []
        else:
            artifacts = [
                ArtifactCreateInput(
                    type=artifact_type,
                    status="draft",
                    content={
                        "stdout": completed.stdout,
                        "stderr": completed.stderr,
                        "child_run_id": child.child_run_id,
                    },
                    metadata={"provisional": True},
                )
                for artifact_type in request.expected_artifact_types
            ]
        child.status = "completed"
        child.ended_at = now_iso()
        return child, ExecutionResult(
            ok=True,
            summary="child shell success",
            artifacts=artifacts,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_ms=duration_ms,
        )

    child.status = "failed"
    child.ended_at = now_iso()
    child.last_error = {"code": "CHILD_TERMINAL_FAILURE", "message": f"unsupported child kind: {kind}"}
    return child, ExecutionResult(
        ok=False,
        summary="unsupported child kind",
        error_code="CHILD_TERMINAL_FAILURE",
        error_message=f"unsupported child kind: {kind}",
    )

