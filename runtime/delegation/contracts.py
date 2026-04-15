"""Delegation contract helpers for Phase 2A."""

from __future__ import annotations

import uuid
from typing import List

from runtime.models import DelegationRecord, DelegationRequest, DelegationReview, now_iso


def new_delegation_id() -> str:
    """Generate a deterministic-length delegation identifier."""
    return f"dlg-{uuid.uuid4().hex[:12]}"


def new_child_run_id(parent_run_id: str, delegation_id: str) -> str:
    """Generate child run id tied to parent/delegation identifiers."""
    suffix = delegation_id.replace("dlg-", "")
    return f"{parent_run_id}--child-{suffix}"


def new_operation_id() -> str:
    """Generate operation id for journaled state transitions."""
    return f"op-{uuid.uuid4().hex[:12]}"


def build_delegation_request(
    *,
    objective: str,
    input_artifact_ids: List[str],
    copy_in_paths: List[str],
    tool_allowlist: List[str],
    path_allowlist: List[str],
    path_denylist: List[str],
    max_steps: int,
    timeout_seconds: int,
    expected_artifact_types: List[str],
) -> DelegationRequest:
    """Construct typed delegation request from task execution config."""
    return DelegationRequest(
        objective=objective,
        input_artifact_ids=list(input_artifact_ids),
        copy_in_paths=list(copy_in_paths),
        tool_allowlist=list(tool_allowlist),
        path_allowlist=list(path_allowlist),
        path_denylist=list(path_denylist),
        max_steps=max_steps,
        timeout_seconds=timeout_seconds,
        expected_artifact_types=list(expected_artifact_types),
        review_required=True,
    )


def build_delegation_record(
    *,
    parent_run_id: str,
    parent_task_id: str,
    request: DelegationRequest,
    workspace_dir: str,
) -> DelegationRecord:
    """Create a fresh delegation record with child_run_id and lineage depth 1."""
    delegation_id = new_delegation_id()
    created = now_iso()
    return DelegationRecord(
        delegation_id=delegation_id,
        parent_run_id=parent_run_id,
        parent_task_id=parent_task_id,
        lineage_depth=1,
        child_run_id=new_child_run_id(parent_run_id, delegation_id),
        status="created",
        request=request,
        result=None,
        review=DelegationReview(decision=None, reviewed_by=None, reviewed_at=None, notes=None),
        workspace_dir=workspace_dir,
        artifacts_copied_back=[],
        created_at=created,
        updated_at=created,
    )

