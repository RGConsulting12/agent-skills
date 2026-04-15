"""Delegation helpers for runtime-managed Phase 2A child runs."""

from __future__ import annotations

from typing import List

from runtime.models import (
    ArtifactCreateInput,
    ChildRunState,
    DelegationRequest,
    DelegationResult,
    ExecutionResult,
    now_iso,
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
        output_manifest={},
        evidence={"child_status": child.status, "last_error": child.last_error},
        submitted_at=now_iso(),
    )


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
    return child, ExecutionResult(
        ok=True,
        summary="child noop success",
        artifacts=artifacts,
    )

