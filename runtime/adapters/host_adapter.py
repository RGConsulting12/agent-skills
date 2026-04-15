"""Host adapter interface for task execution."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from runtime.models import ExecutionResult, RunState, TaskDefinition


class HostAdapter(Protocol):
    """Host-agnostic adapter API used by the runner."""

    name: str

    def capabilities(self) -> Mapping[str, Any]:
        """Return supported execution capabilities."""

    def execute_task(
        self,
        *,
        task: TaskDefinition,
        run_state: RunState,
        attempt: int,
        trace_id: str,
    ) -> ExecutionResult:
        """Execute one task attempt and return normalized result."""

