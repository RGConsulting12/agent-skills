"""Typed models for the Phase 1 runtime."""

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

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionConfig":
        return cls(
            kind=str(data["kind"]),
            command=data.get("command"),
            cwd=data.get("cwd"),
            env=dict(data.get("env", {})),
            timeout_seconds=int(data.get("timeout_seconds", 300)),
            emit_artifact=data.get("emit_artifact"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "command": self.command,
            "cwd": self.cwd,
            "env": self.env,
            "timeout_seconds": self.timeout_seconds,
            "emit_artifact": self.emit_artifact,
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
    current_task_id: Optional[str] = None
    summary: Dict[str, Any] = field(default_factory=dict)
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
            "current_task_id": self.current_task_id,
            "summary": self.summary,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunState":
        tasks = {
            key: TaskRuntimeState.from_dict(value)
            for key, value in dict(data.get("tasks", {})).items()
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
            current_task_id=data.get("current_task_id"),
            summary=dict(data.get("summary", {})),
            metadata=dict(data.get("metadata", {})),
        )


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
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
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
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class ArtifactCreateInput:
    """Adapter-provided artifact payload input."""

    type: str
    status: str = "final"
    path: Optional[str] = None
    content: Any = None
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

