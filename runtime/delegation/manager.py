"""Delegation manager for runtime-managed Phase 2A child runs."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Dict, List

from runtime.models import (
    ArtifactCreateInput,
    ChildRunState,
    DelegationRecord,
    DelegationRequest,
    DelegationResult,
    ExecutionResult,
    Plan,
    RunState,
    TaskDefinition,
    now_iso,
)


def _extract_task_id(task: TaskDefinition) -> str:
    return task.execution.delegation.get("child_task_id", "CHILD_TASK")


def _extract_command(task: TaskDefinition) -> str:
    return str(task.execution.delegation.get("child_command", "")).strip()


def build_delegation_request(
    run_state: RunState,
    task: TaskDefinition,
    delegation_id: str,
    child_run_id: str,
) -> DelegationRequest:
    """Build typed delegation request from parent task config."""
    cfg = task.execution.delegation
    return DelegationRequest(
        delegation_id=delegation_id,
        parent_run_id=run_state.run_id,
        parent_task_id=task.task_id,
        lineage_depth=1,
        child_run_id=child_run_id,
        objective=str(cfg["objective"]),
        input_artifact_ids=list(cfg.get("input_artifact_ids", [])),
        copy_in_paths=list(cfg.get("copy_in_paths", [])),
        tool_allowlist=list(cfg["tool_allowlist"]),
        path_allowlist=list(cfg["path_allowlist"]),
        path_denylist=list(cfg.get("path_denylist", [])),
        max_steps=int(cfg["max_steps"]),
        timeout_seconds=int(cfg["timeout_seconds"]),
        expected_artifact_types=list(cfg["expected_artifact_types"]),
        review_required=True,
        created_at=now_iso(),
    )


def child_run_from_request(task: TaskDefinition, request: DelegationRequest) -> ChildRunState:
    """Construct minimal child run state for inline delegation execution."""
    return ChildRunState(
        child_run_id=request.child_run_id,
        parent_run_id=request.parent_run_id,
        delegation_id=request.delegation_id,
        status="running",
        step_count=0,
        max_steps=request.max_steps,
        started_at=now_iso(),
        ended_at=None,
        failure_code=None,
        summary=None,
        task_id=_extract_task_id(task),
        command=_extract_command(task),
        timeout_seconds=request.timeout_seconds,
        artifacts=[],
    )


def run_child_inline(task: TaskDefinition, request: DelegationRequest) -> tuple[ChildRunState, ExecutionResult]:
    """Execute child run inline with minimal model (not detached/background)."""
    child = child_run_from_request(task, request)
    child.step_count += 1
    if child.step_count > child.max_steps:
        child.status = "failed"
        child.failure_code = "CHILD_MAX_STEPS_EXHAUSTED"
        child.ended_at = now_iso()
        result = ExecutionResult(
            ok=False,
            summary="child max steps exhausted",
            error_code=child.failure_code,
            error_message=child.failure_code,
        )
        return child, result

    # Child run model execution: supports noop/shell via encoded child kind.
    kind = str(task.execution.delegation.get("child_kind", "noop"))
    if kind == "noop":
        artifacts: List[ArtifactCreateInput] = []
        for artifact_type in request.expected_artifact_types:
            artifacts.append(
                ArtifactCreateInput(
                    type=artifact_type,
                    status="draft",
                    content={
                        "summary": f"child produced {artifact_type}",
                        "child_run_id": child.child_run_id,
                    },
                    metadata={"provisional": True},
                )
            )
        child.status = "completed"
        child.ended_at = now_iso()
        child.summary = "child noop success"
        child.artifacts = [asdict(item) for item in artifacts]
        result = ExecutionResult(ok=True, summary=child.summary, artifacts=artifacts)
        return child, result

    if kind == "shell":
        import subprocess
        import time

        started = time.monotonic()
        command = child.command
        if not command:
            child.status = "failed"
            child.failure_code = "CHILD_INVALID_COMMAND"
            child.ended_at = now_iso()
            return child, ExecutionResult(
                ok=False,
                summary="child invalid command",
                error_code=child.failure_code,
                error_message="missing child command",
            )
        try:
            completed = subprocess.run(
                command,
                cwd=".",
                capture_output=True,
                text=True,
                timeout=child.timeout_seconds,
                shell=True,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            child.status = "failed"
            child.failure_code = "CHILD_TIMEOUT"
            child.ended_at = now_iso()
            return child, ExecutionResult(
                ok=False,
                summary="child timeout",
                stdout=exc.stdout,
                stderr=exc.stderr,
                error_code=child.failure_code,
                error_message=child.failure_code,
                duration_ms=int((time.monotonic() - started) * 1000),
            )

        duration_ms = int((time.monotonic() - started) * 1000)
        if completed.returncode != 0:
            child.status = "failed"
            child.failure_code = "CHILD_TERMINAL_FAILURE"
            child.ended_at = now_iso()
            return child, ExecutionResult(
                ok=False,
                summary="child shell failed",
                stdout=completed.stdout,
                stderr=completed.stderr,
                error_code=child.failure_code,
                error_message=f"exit code {completed.returncode}",
                duration_ms=duration_ms,
            )
        artifacts = []
        for artifact_type in request.expected_artifact_types:
            artifacts.append(
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
            )
        child.status = "completed"
        child.ended_at = now_iso()
        child.summary = "child shell success"
        child.artifacts = [asdict(item) for item in artifacts]
        return child, ExecutionResult(
            ok=True,
            summary=child.summary,
            artifacts=artifacts,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_ms=duration_ms,
        )

    child.status = "failed"
    child.failure_code = "CHILD_UNSUPPORTED_KIND"
    child.ended_at = now_iso()
    return child, ExecutionResult(
        ok=False,
        summary="child unsupported kind",
        error_code=child.failure_code,
        error_message=child.failure_code,
    )


def build_delegation_record(request: DelegationRequest, workspace_dir: str) -> DelegationRecord:
    """Create initial delegation record."""
    return DelegationRecord(
        delegation_id=request.delegation_id,
        parent_run_id=request.parent_run_id,
        parent_task_id=request.parent_task_id,
        lineage_depth=1,
        child_run_id=request.child_run_id,
        status="created",
        request=request,
        result=None,
        review_decision=None,
        reviewed_by=None,
        reviewed_at=None,
        review_notes=None,
        workspace_dir=workspace_dir,
        artifacts_copied_back=[],
        created_at=request.created_at,
        updated_at=request.created_at,
    )


def build_review_result(
    request: DelegationRequest,
    child: ChildRunState,
    produced_artifact_ids: List[str],
) -> DelegationResult:
    """Build review-submitted result payload from successful child run."""
    return DelegationResult(
        status="submitted_for_review",
        summary=child.summary or "child completed",
        produced_artifact_ids=produced_artifact_ids,
        output_manifest={
            "child_run_id": child.child_run_id,
            "artifact_count": len(produced_artifact_ids),
        },
        evidence={"child_status": child.status, "failure_code": child.failure_code},
        submitted_at=now_iso(),
    )

