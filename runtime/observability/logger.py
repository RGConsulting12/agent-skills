"""JSONL logger for runtime trace events."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


class TraceLogger:
    """Append-only JSONL event logger."""

    def __init__(self, logs_dir: str = ".agent-runtime/logs", *, max_field_size: int = 4000) -> None:
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.max_field_size = max_field_size

    def path_for(self, run_id: str) -> Path:
        return self.logs_dir / f"{run_id}.jsonl"

    def _sanitize(self, event: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = dict(event)
        for field in ("stdout", "stderr"):
            value = sanitized.get(field)
            if isinstance(value, str) and len(value) > self.max_field_size:
                sanitized[field] = value[: self.max_field_size] + "...[truncated]"
        return sanitized

    def log(self, run_id: str, event: Dict[str, Any]) -> None:
        path = self.path_for(run_id)
        sanitized = self._sanitize(event)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sanitized, sort_keys=True))
            handle.write("\n")

    def read_tail(self, run_id: str, tail: int = 20) -> List[Dict[str, Any]]:
        path = self.path_for(run_id)
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-tail:]]

