"""Artifact lifecycle helpers."""

from __future__ import annotations

import uuid
from typing import List

from runtime.models import Artifact, ArtifactCreateInput, RunState, now_iso
from runtime.workspace.storage import StateStore


def create_artifact(
    run_id: str,
    task_id: str,
    payload: ArtifactCreateInput,
    *,
    created_at: str | None = None,
    producer_delegation_id: str | None = None,
    producer_child_run_id: str | None = None,
    lineage_depth: int | None = None,
    status_override: str | None = None,
) -> Artifact:
    """Create a typed artifact from adapter payload."""
    return Artifact(
        artifact_id=f"art-{uuid.uuid4().hex[:12]}",
        run_id=run_id,
        producer_task_id=task_id,
        producer_delegation_id=producer_delegation_id,
        producer_child_run_id=producer_child_run_id,
        lineage_depth=lineage_depth,
        type=payload.type,
        status=status_override or payload.status,
        path=payload.path,
        content=payload.content,
        created_at=created_at or now_iso(),
        metadata=payload.metadata,
    )


def persist_artifacts(
    store: StateStore, run_state: RunState, task_id: str, artifacts: List[Artifact]
) -> None:
    """Persist artifacts and attach them to task and run indexes."""
    if not artifacts:
        return
    serialized = [item.to_dict() for item in artifacts]
    existing = store.load_artifacts(run_state.run_id)
    existing.extend(serialized)
    store.save_artifacts(run_state.run_id, existing)

    task_state = run_state.tasks[task_id]
    for artifact in artifacts:
        run_state.artifacts.append(artifact.artifact_id)
        task_state.produced_artifacts.append(artifact.artifact_id)

