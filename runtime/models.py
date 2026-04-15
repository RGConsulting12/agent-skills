"""Typed models for the runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def now_iso() -> str:
    """Return an ISO8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RetryPolicy:
    """Retry settings for task execution."""

    max_retries: int = 0
    backoff_base_seconds: int = 1
    backoff_factor: float = 2.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RetryPolicy":
        return cls(
            max_retries=int(data.get("max_retries", 0)),
            backoff_base_seconds=int(data.get("backoff_base_seconds", 1)),
            backoff_factor=float(data.get("backoff_factor", 2.0)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_retries": self.max_retries,
            "backoff_base_seconds": self.backoff_base_seconds,
            "backoff_factor": self.backoff_factor,
        }


@dataclass
class ExecutionConfig:
    """Execution details for a task."""

    kind: str
    command: Optional[str] = None
    cwd: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 300
    emit_artifact: Optional[Dict[str, Any]] = None
    delegation: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionConfig":
        return cls(
            kind=str(data["kind"]),
            command=data.get("command"),
            cwd=data.get("cwd"),
            env=dict(data.get("env", {})),
            timeout_seconds=int(data.get("timeout_seconds", 300)),
            emit_artifact=data.get("emit_artifact"),
            delegation=data.get("delegation"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "command": self.command,
            "cwd": self.cwd,
            "env": self.env,
            "timeout_seconds": self.timeout_seconds,
            "emit_artifact": self.emit_artifact,
            "delegation": self.delegation,
        }


@dataclass
class TaskDefinition:
    """Plan-time task definition."""

    task_id: str
    title: str
    description: str = ""
    depends_on: List[str] = field(default_factory=list)
    priority: int = 0
    approval_required: bool = False
    execution: ExecutionConfig = field(default_factory=lambda: ExecutionConfig(kind="noop"))
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    expected_artifacts: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskDefinition":
        return cls(
            task_id=str(data["task_id"]),
            title=str(data["title"]),
            description=str(data.get("description", "")),
            depends_on=list(data.get("depends_on", [])),
            priority=int(data.get("priority", 0)),
            approval_required=bool(data.get("approval_required", False)),
            execution=ExecutionConfig.from_dict(data["execution"]),
            retry_policy=RetryPolicy.from_dict(data.get("retry_policy", {})),
            expected_artifacts=list(data.get("expected_artifacts", [])),
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "depends_on": self.depends_on,
            "priority": self.priority,
            "approval_required": self.approval_required,
            "execution": self.execution.to_dict(),
            "retry_policy": self.retry_policy.to_dict(),
            "expected_artifacts": self.expected_artifacts,
            "metadata": self.metadata,
        }


@dataclass
class Plan:
    """Validated machine-readable plan."""

    schema_version: str
    plan_id: str
    title: str
    description: str
    created_at: str
    created_by: str
    tasks: List[TaskDefinition]
    metadata: Dict[str, Any] = field(default_factory=dict)
    policy: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Plan":
        return cls(
            schema_version=str(data["schema_version"]),
            plan_id=str(data["plan_id"]),
            title=str(data["title"]),
            description=str(data.get("description", "")),
            created_at=str(data["created_at"]),
            created_by=str(data["created_by"]),
            tasks=[TaskDefinition.from_dict(item) for item in data["tasks"]],
            metadata=dict(data.get("metadata", {})),
            policy=dict(data.get("policy", {})) if data.get("policy") else None,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "title": self.title,
            "description": self.description,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "tasks": [task.to_dict() for task in self.tasks],
            "metadata": self.metadata,
            "policy": self.policy,
        }


@dataclass
class TaskApproval:
    """Approval state for a runtime task."""

    required: bool
    approved: bool = False
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "required": self.required,
            "approved": self.approved,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskApproval":
        return cls(
            required=bool(data.get("required", False)),
            approved=bool(data.get("approved", False)),
            approved_by=data.get("approved_by"),
            approved_at=data.get("approved_at"),
        )


@dataclass
class TaskRuntimeState:
    """Task runtime state tracked during execution."""

    task_id: str
    status: str
    attempts: int
    max_retries: int
    last_error: Optional[Dict[str, Any]]
    approval: TaskApproval
    depends_on: List[str]
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    produced_artifacts: List[str] = field(default_factory=list)
    delegation_attempts: int = 0
    max_delegation_attempts: int = 0
    delegation_ids: List[str] = field(default_factory=list)
    active_delegation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "attempts": self.attempts,
            "max_retries": self.max_retries,
            "last_error": self.last_error,
            "approval": self.approval.to_dict(),
            "depends_on": self.depends_on,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "produced_artifacts": self.produced_artifacts,
            "delegation_attempts": self.delegation_attempts,
            "max_delegation_attempts": self.max_delegation_attempts,
            "delegation_ids": self.delegation_ids,
            "active_delegation_id": self.active_delegation_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskRuntimeState":
        return cls(
            task_id=str(data["task_id"]),
            status=str(data["status"]),
            attempts=int(data.get("attempts", 0)),
            max_retries=int(data.get("max_retries", 0)),
            last_error=data.get("last_error"),
            approval=TaskApproval.from_dict(dict(data.get("approval", {}))),
            depends_on=list(data.get("depends_on", [])),
            started_at=data.get("started_at"),
            ended_at=data.get("ended_at"),
            produced_artifacts=list(data.get("produced_artifacts", [])),
            delegation_attempts=int(data.get("delegation_attempts", 0)),
            max_delegation_attempts=int(data.get("max_delegation_attempts", 0)),
            delegation_ids=list(data.get("delegation_ids", [])),
            active_delegation_id=data.get("active_delegation_id"),
        )


@dataclass
class ChildTaskRuntimeState:
    """Child-run task state for runtime-managed delegation."""

    task_id: str
    status: str
    attempts: int
    max_retries: int
    last_error: Optional[Dict[str, Any]]
    depends_on: List[str]
    produced_artifacts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "attempts": self.attempts,
            "max_retries": self.max_retries,
            "last_error": self.last_error,
            "depends_on": self.depends_on,
            "produced_artifacts": self.produced_artifacts,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChildTaskRuntimeState":
        return cls(
            task_id=str(data["task_id"]),
            status=str(data["status"]),
            attempts=int(data.get("attempts", 0)),
            max_retries=int(data.get("max_retries", 0)),
            last_error=data.get("last_error"),
            depends_on=list(data.get("depends_on", [])),
            produced_artifacts=list(data.get("produced_artifacts", [])),
        )


@dataclass
class ChildRunState:
    """Minimal child-run model for delegation execution state."""

    child_run_id: str
    parent_run_id: str
    parent_task_id: str
    status: str
    created_at: str
    started_at: Optional[str]
    ended_at: Optional[str]
    max_steps: int
    steps_executed: int
    timeout_seconds: int
    tasks: Dict[str, ChildTaskRuntimeState]
    artifacts: List[str]
    last_error: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "child_run_id": self.child_run_id,
            "parent_run_id": self.parent_run_id,
            "parent_task_id": self.parent_task_id,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "max_steps": self.max_steps,
            "steps_executed": self.steps_executed,
            "timeout_seconds": self.timeout_seconds,
            "tasks": {key: value.to_dict() for key, value in self.tasks.items()},
            "artifacts": self.artifacts,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChildRunState":
        tasks = {
            key: ChildTaskRuntimeState.from_dict(value)
            for key, value in dict(data.get("tasks", {})).items()
        }
        return cls(
            child_run_id=str(data["child_run_id"]),
            parent_run_id=str(data["parent_run_id"]),
            parent_task_id=str(data["parent_task_id"]),
            status=str(data["status"]),
            created_at=str(data["created_at"]),
            started_at=data.get("started_at"),
            ended_at=data.get("ended_at"),
            max_steps=int(data.get("max_steps", 0)),
            steps_executed=int(data.get("steps_executed", 0)),
            timeout_seconds=int(data.get("timeout_seconds", 0)),
            tasks=tasks,
            artifacts=list(data.get("artifacts", [])),
            last_error=data.get("last_error"),
        )


@dataclass
class DelegationRequest:
    """Parent-to-child delegation request contract."""

    objective: str
    input_artifact_ids: List[str] = field(default_factory=list)
    copy_in_paths: List[str] = field(default_factory=list)
    tool_allowlist: List[str] = field(default_factory=list)
    path_allowlist: List[str] = field(default_factory=list)
    path_denylist: List[str] = field(default_factory=list)
    max_steps: int = 1
    timeout_seconds: int = 60
    expected_artifact_types: List[str] = field(default_factory=list)
    review_required: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "objective": self.objective,
            "input_artifact_ids": self.input_artifact_ids,
            "copy_in_paths": self.copy_in_paths,
            "tool_allowlist": self.tool_allowlist,
            "path_allowlist": self.path_allowlist,
            "path_denylist": self.path_denylist,
            "max_steps": self.max_steps,
            "timeout_seconds": self.timeout_seconds,
            "expected_artifact_types": self.expected_artifact_types,
            "review_required": self.review_required,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DelegationRequest":
        return cls(
            objective=str(data["objective"]),
            input_artifact_ids=list(data.get("input_artifact_ids", [])),
            copy_in_paths=list(data.get("copy_in_paths", [])),
            tool_allowlist=list(data.get("tool_allowlist", [])),
            path_allowlist=list(data.get("path_allowlist", [])),
            path_denylist=list(data.get("path_denylist", [])),
            max_steps=int(data.get("max_steps", 1)),
            timeout_seconds=int(data.get("timeout_seconds", 60)),
            expected_artifact_types=list(data.get("expected_artifact_types", [])),
            review_required=bool(data.get("review_required", True)),
        )


@dataclass
class DelegationResult:
    """Child result contract."""

    status: str
    summary: str
    produced_artifact_ids: List[str] = field(default_factory=list)
    output_manifest: Dict[str, Any] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)
    submitted_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "produced_artifact_ids": self.produced_artifact_ids,
            "output_manifest": self.output_manifest,
            "evidence": self.evidence,
            "submitted_at": self.submitted_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DelegationResult":
        return cls(
            status=str(data["status"]),
            summary=str(data.get("summary", "")),
            produced_artifact_ids=list(data.get("produced_artifact_ids", [])),
            output_manifest=dict(data.get("output_manifest", {})),
            evidence=dict(data.get("evidence", {})),
            submitted_at=data.get("submitted_at"),
        )


@dataclass
class DelegationReview:
    """Review decision for a submitted delegation."""

    decision: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DelegationReview":
        return cls(
            decision=data.get("decision"),
            reviewed_by=data.get("reviewed_by"),
            reviewed_at=data.get("reviewed_at"),
            notes=data.get("notes"),
        )


@dataclass
class DelegationRecord:
    """Delegation runtime record linked to a parent task and child run."""

    delegation_id: str
    parent_run_id: str
    parent_task_id: str
    lineage_depth: int
    child_run_id: str
    status: str
    request: DelegationRequest
    result: Optional[DelegationResult]
    review: DelegationReview
    workspace_dir: str
    artifacts_copied_back: List[str]
    created_at: str
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "delegation_id": self.delegation_id,
            "parent_run_id": self.parent_run_id,
            "parent_task_id": self.parent_task_id,
            "lineage_depth": self.lineage_depth,
            "child_run_id": self.child_run_id,
            "status": self.status,
            "request": self.request.to_dict(),
            "result": self.result.to_dict() if self.result else None,
            "review": self.review.to_dict(),
            "workspace_dir": self.workspace_dir,
            "artifacts_copied_back": self.artifacts_copied_back,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DelegationRecord":
        result_payload = data.get("result")
        return cls(
            delegation_id=str(data["delegation_id"]),
            parent_run_id=str(data["parent_run_id"]),
            parent_task_id=str(data["parent_task_id"]),
            lineage_depth=int(data["lineage_depth"]),
            child_run_id=str(data["child_run_id"]),
            status=str(data["status"]),
            request=DelegationRequest.from_dict(dict(data["request"])),
            result=DelegationResult.from_dict(dict(result_payload)) if result_payload else None,
            review=DelegationReview.from_dict(dict(data.get("review", {}))),
            workspace_dir=str(data.get("workspace_dir", "")),
            artifacts_copied_back=list(data.get("artifacts_copied_back", [])),
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
        )


@dataclass
class ActionApproval:
    """Approval record for policy action categories."""

    category: str
    target_id: str
    approved: bool
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "target_id": self.target_id,
            "approved": self.approved,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActionApproval":
        return cls(
            category=str(data["category"]),
            target_id=str(data["target_id"]),
            approved=bool(data.get("approved", False)),
            approved_by=data.get("approved_by"),
            approved_at=data.get("approved_at"),
        )


@dataclass
class RunState:
    """Top-level runtime state."""

    schema_version: str
    run_id: str
    plan_id: str
    status: str
    created_at: str
    started_at: Optional[str]
    ended_at: Optional[str]
    tasks: Dict[str, TaskRuntimeState]
    artifacts: List[str]
    delegations: Dict[str, DelegationRecord] = field(default_factory=dict)
    child_runs: Dict[str, ChildRunState] = field(default_factory=dict)
    action_approvals: Dict[str, ActionApproval] = field(default_factory=dict)
    current_task_id: Optional[str] = None
    summary: Dict[str, Any] = field(default_factory=dict)
    pending: Dict[str, Any] = field(default_factory=dict)
    reconciliation: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "plan_id": self.plan_id,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "tasks": {key: value.to_dict() for key, value in self.tasks.items()},
            "artifacts": self.artifacts,
            "delegations": {key: value.to_dict() for key, value in self.delegations.items()},
            "child_runs": {key: value.to_dict() for key, value in self.child_runs.items()},
            "action_approvals": {
                key: value.to_dict() for key, value in self.action_approvals.items()
            },
            "current_task_id": self.current_task_id,
            "summary": self.summary,
            "pending": self.pending,
            "reconciliation": self.reconciliation,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunState":
        tasks = {
            key: TaskRuntimeState.from_dict(value)
            for key, value in dict(data.get("tasks", {})).items()
        }
        delegations = {
            key: DelegationRecord.from_dict(value)
            for key, value in dict(data.get("delegations", {})).items()
        }
        child_runs = {
            key: ChildRunState.from_dict(value)
            for key, value in dict(data.get("child_runs", {})).items()
        }
        action_approvals = {
            key: ActionApproval.from_dict(value)
            for key, value in dict(data.get("action_approvals", {})).items()
        }
        return cls(
            schema_version=str(data["schema_version"]),
            run_id=str(data["run_id"]),
            plan_id=str(data["plan_id"]),
            status=str(data["status"]),
            created_at=str(data["created_at"]),
            started_at=data.get("started_at"),
            ended_at=data.get("ended_at"),
            tasks=tasks,
            artifacts=list(data.get("artifacts", [])),
            delegations=delegations,
            child_runs=child_runs,
            action_approvals=action_approvals,
            current_task_id=data.get("current_task_id"),
            summary=dict(data.get("summary", {})),
            pending=dict(data.get("pending", {})),
            reconciliation=dict(data.get("reconciliation", {})),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class JournalEntry:
    """Append-only operation journal entry."""

    op_id: str
    run_id: str
    entity_kind: str
    entity_id: str
    operation: str
    phase: str
    state_before: Optional[Dict[str, Any]]
    state_after: Optional[Dict[str, Any]]
    reason_code: Optional[str] = None
    trace: Dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "op_id": self.op_id,
            "run_id": self.run_id,
            "entity_kind": self.entity_kind,
            "entity_id": self.entity_id,
            "operation": self.operation,
            "phase": self.phase,
            "state_before": self.state_before,
            "state_after": self.state_after,
            "reason_code": self.reason_code,
            "trace": self.trace,
            "ts": self.ts,
        }


@dataclass
class Artifact:
    """Typed artifact emitted by a task."""

    artifact_id: str
    run_id: str
    producer_task_id: str
    type: str
    status: str
    path: Optional[str]
    content: Any
    created_at: str
    producer_delegation_id: Optional[str] = None
    producer_child_run_id: Optional[str] = None
    lineage_depth: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "artifact_id": self.artifact_id,
            "run_id": self.run_id,
            "producer_task_id": self.producer_task_id,
            "type": self.type,
            "status": self.status,
            "path": self.path,
            "content": self.content,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }
        if self.producer_delegation_id is not None:
            data["producer_delegation_id"] = self.producer_delegation_id
        if self.producer_child_run_id is not None:
            data["producer_child_run_id"] = self.producer_child_run_id
        if self.lineage_depth is not None:
            data["lineage_depth"] = self.lineage_depth
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Artifact":
        return cls(
            artifact_id=str(data["artifact_id"]),
            run_id=str(data["run_id"]),
            producer_task_id=str(data["producer_task_id"]),
            type=str(data["type"]),
            status=str(data["status"]),
            path=data.get("path"),
            content=data.get("content"),
            created_at=str(data["created_at"]),
            producer_delegation_id=data.get("producer_delegation_id"),
            producer_child_run_id=data.get("producer_child_run_id"),
            lineage_depth=data.get("lineage_depth"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class ArtifactCreateInput:
    """Adapter-provided artifact payload input."""

    type: str
    status: str = "final"
    path: Optional[str] = None
    content: Any = None
    producer_delegation_id: Optional[str] = None
    producer_child_run_id: Optional[str] = None
    lineage_depth: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """Normalized adapter execution output."""

    ok: bool
    summary: str
    artifacts: List[ArtifactCreateInput] = field(default_factory=list)
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    duration_ms: int = 0

