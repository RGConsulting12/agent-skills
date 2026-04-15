"""Runtime-managed Phase 2A delegation service."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Tuple

from runtime.delegation.contracts import build_delegation_record, build_delegation_request
from runtime.delegation.manager import build_review_result, run_child_inline
from runtime.delegation.workspace import DelegationWorkspace
from runtime.delegation.review import apply_review
from runtime.models import DelegationRecord, DelegationResult, Plan, RunState, TaskDefinition, now_iso
from runtime.policy.engine import PolicyEngine, PolicyError
from runtime.workspace.artifacts import create_artifact, persist_artifacts
from runtime.workspace.storage import StateStore


class DelegationService:
    """Coordinates inline child runs and review-state delegation lifecycle."""

    def __init__(
        self,
        *,
        store: StateStore,
        policy: PolicyEngine,
        workspace: DelegationWorkspace | None = None,
        repo_root: str = "/workspace",
    ) -> None:
        self.store = store
        self.policy = policy
        self.workspace = workspace or DelegationWorkspace()
        self.repo_root = repo_root

    def start_delegation(
        self,
        *,
        plan: Plan,
        run_state: RunState,
        task: TaskDefinition,
        trace_emitter: Callable[[str, Dict[str, object] | None], None],
    ) -> Tuple[RunState, bool]:
        """Start and execute one delegation attempt inline.

        Returns updated run_state and True when delegation was started/executed.
        """
        task_state = run_state.tasks[task.task_id]
        if task_state.active_delegation_id is not None:
            raise ValueError(f"task '{task.task_id}' already has active delegation")
        cfg = task.execution.delegation or {}
        max_attempts = int(cfg.get("max_delegation_attempts", 0))
        if max_attempts < 1:
            raise ValueError(f"task '{task.task_id}' missing max_delegation_attempts")

        # Attempt count increments when a new delegation is created.
        task_state.delegation_attempts += 1
        task_state.max_delegation_attempts = max_attempts

        request = build_delegation_request(
            objective=str(cfg["objective"]),
            input_artifact_ids=list(cfg.get("input_artifact_ids", [])),
            copy_in_paths=list(cfg.get("copy_in_paths", [])),
            tool_allowlist=list(cfg["tool_allowlist"]),
            path_allowlist=list(cfg["path_allowlist"]),
            path_denylist=list(cfg.get("path_denylist", [])),
            max_steps=int(cfg["max_steps"]),
            timeout_seconds=int(cfg["timeout_seconds"]),
            expected_artifact_types=list(cfg["expected_artifact_types"]),
        )

        record = build_delegation_record(
            parent_run_id=run_state.run_id,
            parent_task_id=task.task_id,
            request=request,
            workspace_dir="",
        )

        if record.lineage_depth != 1:
            raise ValueError("nested delegation is not supported in Phase 2A")

        task_state.active_delegation_id = record.delegation_id
        task_state.delegation_ids.append(record.delegation_id)
        task_state.status = "delegating"

        trace_emitter(
            "delegation_created",
            {
                "task_id": task.task_id,
                "delegation_id": record.delegation_id,
                "child_run_id": record.child_run_id,
                "attempt": task_state.delegation_attempts,
            },
        )

        try:
            self.policy.enforce_tool_allowlist(request.tool_allowlist, "noop")
            self.policy.enforce_path_rules(
                repo_root=self.repo_root_path,
                path_allowlist=request.path_allowlist,
                path_denylist=request.path_denylist,
                requested_paths=request.copy_in_paths,
            )
            ws = self.workspace.prepare(
                run_id=run_state.run_id,
                delegation=record,
                repo_root=self.repo_root,
                policy=self.policy,
                context_payload={
                    "plan_id": plan.plan_id,
                    "task_id": task.task_id,
                    "objective": request.objective,
                },
            )
            record.workspace_dir = ws["root"]
            record.status = "running"
            record.updated_at = now_iso()
            trace_emitter(
                "delegation_workspace_prepared",
                {
                    "delegation_id": record.delegation_id,
                    "copied_paths": ws.get("copied_paths", []),
                },
            )
        except (PolicyError, ValueError) as exc:
            task_state.status = "ready"
            task_state.active_delegation_id = None
            task_state.last_error = {
                "code": "DELEGATION_POLICY_DENIED",
                "message": str(exc),
                "detail": {"attempt": task_state.delegation_attempts},
            }
            trace_emitter(
                "policy_check_failed",
                {"delegation_id": record.delegation_id, "task_id": task.task_id, "message": str(exc)},
            )
            return run_state, True

        child_run, exec_result = run_child_inline(
            task,
            request,
            child_run_id=record.child_run_id,
            parent_run_id=run_state.run_id,
        )
        run_state.child_runs[record.child_run_id] = child_run
        trace_emitter(
            "delegation_child_finished",
            {
                "delegation_id": record.delegation_id,
                "child_run_id": record.child_run_id,
                "child_status": child_run.status,
                "error_code": exec_result.error_code,
            },
        )

        if not exec_result.ok:
            self._apply_delegation_failure(
                run_state=run_state,
                task=task,
                record=record,
                task_state=task_state,
                error_code=exec_result.error_code or "DELEGATION_CHILD_FAILED",
                error_message=exec_result.error_message or exec_result.summary,
                trace_emitter=trace_emitter,
            )
            return run_state, True

        created_artifacts = []
        for payload in exec_result.artifacts:
            created_artifacts.append(
                create_artifact(
                    run_state.run_id,
                    task.task_id,
                    payload,
                    producer_delegation_id=record.delegation_id,
                    producer_child_run_id=record.child_run_id,
                    lineage_depth=1,
                    status_override="draft",
                )
            )
        persist_artifacts(self.store, run_state, task.task_id, created_artifacts)
        record.artifacts_copied_back = [item.artifact_id for item in created_artifacts]
        missing_outputs = self._missing_outputs(
            expected=request.expected_artifact_types,
            produced=[item.type for item in created_artifacts],
        )
        if missing_outputs:
            self._apply_delegation_failure(
                run_state=run_state,
                task=task,
                record=record,
                task_state=task_state,
                error_code="DELEGATION_MISSING_OUTPUTS",
                error_message=f"missing outputs: {', '.join(missing_outputs)}",
                trace_emitter=trace_emitter,
            )
            return run_state, True

        record.result = build_review_result(
            request=request,
            child=child_run,
            produced_artifact_ids=record.artifacts_copied_back,
        )
        record.status = "submitted_for_review"
        record.updated_at = now_iso()
        run_state.delegations[record.delegation_id] = record
        task_state.status = "waiting_review"
        trace_emitter(
            "delegation_submitted_for_review",
            {"delegation_id": record.delegation_id, "task_id": task.task_id},
        )
        self.store.save_delegation(run_state.run_id, record.to_dict())
        return run_state, True

    @property
    def repo_root_path(self):
        return Path(self.repo_root).resolve()

    def apply_review_decision(
        self,
        *,
        run_state: RunState,
        delegation: DelegationRecord,
        decision: str,
        reviewed_by: str,
        notes: str | None,
        parent_task_state,
    ) -> DelegationRecord:
        """Apply accepted/rejected review and resume/finalize parent task state.

        Phase 2A acceptance finalizes delegation-produced draft artifacts only.
        No patch application is performed.
        """
        apply_review(delegation, decision=decision, reviewed_by=reviewed_by, notes=notes)
        if decision == "accepted":
            artifacts = self.store.load_artifacts(run_state.run_id)
            for artifact in artifacts:
                if artifact.get("producer_delegation_id") == delegation.delegation_id:
                    artifact["status"] = "final"
                    metadata = dict(artifact.get("metadata", {}))
                    metadata["provisional"] = False
                    artifact["metadata"] = metadata
            self.store.save_artifacts(run_state.run_id, artifacts)
            parent_task_state.status = "completed"
            parent_task_state.active_delegation_id = None
            parent_task_state.last_error = None
        else:
            exhausted = parent_task_state.delegation_attempts >= parent_task_state.max_delegation_attempts
            if exhausted:
                delegation.status = "exhausted"
                parent_task_state.status = "failed"
                parent_task_state.last_error = {
                    "code": "DELEGATION_REJECTED_EXHAUSTED",
                    "message": "delegation review rejected and attempts exhausted",
                    "detail": {"attempts": parent_task_state.delegation_attempts},
                }
            else:
                parent_task_state.status = "ready"
                parent_task_state.last_error = {
                    "code": "DELEGATION_REJECTED",
                    "message": "delegation review rejected",
                    "detail": {"attempts": parent_task_state.delegation_attempts},
                }
            parent_task_state.active_delegation_id = None
        delegation.updated_at = now_iso()
        self.store.save_delegation(run_state.run_id, delegation.to_dict())
        return delegation

    def _apply_delegation_failure(
        self,
        *,
        run_state: RunState,
        task: TaskDefinition,
        record: DelegationRecord,
        task_state,
        error_code: str,
        error_message: str,
        trace_emitter: Callable[[str, Dict[str, object] | None], None],
    ) -> None:
        record.status = "failed"
        record.result = DelegationResult(
            status="failed",
            summary=error_message,
            produced_artifact_ids=list(record.artifacts_copied_back),
            output_manifest={},
            evidence={"error_code": error_code},
            submitted_at=now_iso(),
        )
        record.updated_at = now_iso()
        run_state.delegations[record.delegation_id] = record
        self.store.save_delegation(run_state.run_id, record.to_dict())
        exhausted = task_state.delegation_attempts >= task_state.max_delegation_attempts
        if exhausted:
            record.status = "exhausted"
            record.updated_at = now_iso()
            run_state.delegations[record.delegation_id] = record
            task_state.status = "failed"
            task_state.last_error = {
                "code": f"{error_code}_EXHAUSTED",
                "message": error_message,
                "detail": {"attempts": task_state.delegation_attempts},
            }
            self.store.save_delegation(run_state.run_id, record.to_dict())
            trace_emitter(
                "delegation_failed",
                {
                    "delegation_id": record.delegation_id,
                    "task_id": task.task_id,
                    "error_code": f"{error_code}_EXHAUSTED",
                },
            )
        else:
            task_state.status = "ready"
            task_state.last_error = {
                "code": error_code,
                "message": error_message,
                "detail": {"attempts": task_state.delegation_attempts},
            }
            trace_emitter(
                "delegation_failed",
                {"delegation_id": record.delegation_id, "task_id": task.task_id, "error_code": error_code},
            )
        task_state.active_delegation_id = None

    @staticmethod
    def _missing_outputs(*, expected: List[str], produced: List[str]) -> List[str]:
        missing = []
        produced_set = set(produced)
        for item in expected:
            if item not in produced_set:
                missing.append(item)
        return missing

