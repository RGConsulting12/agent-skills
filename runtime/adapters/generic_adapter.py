"""Minimal host-agnostic adapter for noop/shell execution."""

from __future__ import annotations

import subprocess
import time
from typing import Any, Mapping

from runtime.models import ArtifactCreateInput, ExecutionResult, RunState, TaskDefinition


class GenericAdapter:
    """Adapter implementation supporting noop and shell task kinds."""

    name = "generic"

    def capabilities(self) -> Mapping[str, Any]:
        return {"execution_kinds": ["noop", "shell"]}

    def execute_task(
        self,
        *,
        task: TaskDefinition,
        run_state: RunState,
        attempt: int,
        trace_id: str,
    ) -> ExecutionResult:
        del run_state, attempt, trace_id
        if task.execution.kind == "noop":
            artifacts = []
            if task.execution.emit_artifact:
                artifacts.append(
                    ArtifactCreateInput(
                        type=task.execution.emit_artifact.get("type", "report"),
                        status=task.execution.emit_artifact.get("status", "final"),
                        path=task.execution.emit_artifact.get("path"),
                        content=task.execution.emit_artifact.get("content"),
                        metadata=dict(task.execution.emit_artifact.get("metadata", {})),
                    )
                )
            return ExecutionResult(ok=True, summary=f"{task.task_id} noop success", artifacts=artifacts)

        if task.execution.kind != "shell":
            return ExecutionResult(
                ok=False,
                summary=f"{task.task_id} unsupported execution kind",
                error_code="UNSUPPORTED_KIND",
                error_message=f"Unsupported kind: {task.execution.kind}",
            )

        started = time.monotonic()
        env = None
        if task.execution.env:
            env = dict(task.execution.env)
        try:
            completed = subprocess.run(
                task.execution.command,
                cwd=task.execution.cwd or ".",
                env=env,
                capture_output=True,
                text=True,
                timeout=task.execution.timeout_seconds,
                shell=True,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            return ExecutionResult(
                ok=False,
                summary=f"{task.task_id} shell timeout",
                stdout=exc.stdout,
                stderr=exc.stderr,
                error_code="TIMEOUT",
                error_message=f"Command timed out after {task.execution.timeout_seconds}s",
                duration_ms=duration_ms,
            )

        duration_ms = int((time.monotonic() - started) * 1000)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        artifacts = [
            ArtifactCreateInput(
                type="log",
                status="final",
                content={
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": completed.returncode,
                },
            )
        ]
        if task.execution.emit_artifact:
            artifacts.append(
                ArtifactCreateInput(
                    type=task.execution.emit_artifact.get("type", "report"),
                    status=task.execution.emit_artifact.get("status", "final"),
                    path=task.execution.emit_artifact.get("path"),
                    content=task.execution.emit_artifact.get("content"),
                    metadata=dict(task.execution.emit_artifact.get("metadata", {})),
                )
            )
        if completed.returncode == 0:
            return ExecutionResult(
                ok=True,
                summary=f"{task.task_id} shell success",
                artifacts=artifacts,
                stdout=stdout,
                stderr=stderr,
                duration_ms=duration_ms,
            )
        return ExecutionResult(
            ok=False,
            summary=f"{task.task_id} shell failed",
            artifacts=artifacts,
            stdout=stdout,
            stderr=stderr,
            error_code="EXIT_NON_ZERO",
            error_message=f"exit code {completed.returncode}",
            duration_ms=duration_ms,
        )

