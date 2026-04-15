"""Persistent storage helpers for typed runtime state."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List


class StateStore:
    """File-backed state store with atomic writes."""

    def __init__(self, state_dir: str = ".agent-runtime/state") -> None:
        self.state_root = Path(state_dir)
        self.state_root.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        run_path = self.state_root / run_id
        run_path.mkdir(parents=True, exist_ok=True)
        return run_path

    def plan_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "plan.json"

    def run_state_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "run_state.json"

    def artifacts_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "artifacts.json"

    @staticmethod
    def atomic_write_json(path: Path, payload: Any) -> None:
        """Write JSON atomically by writing temp file and renaming."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(tmp_path, path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    @staticmethod
    def read_json(path: Path) -> Any:
        if not path.exists():
            raise FileNotFoundError(str(path))
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save_plan(self, run_id: str, plan_data: Dict[str, Any]) -> None:
        self.atomic_write_json(self.plan_path(run_id), plan_data)

    def load_plan(self, run_id: str) -> Dict[str, Any]:
        return dict(self.read_json(self.plan_path(run_id)))

    def save_run_state(self, run_id: str, run_state_data: Dict[str, Any]) -> None:
        self.atomic_write_json(self.run_state_path(run_id), run_state_data)

    def load_run_state(self, run_id: str) -> Dict[str, Any]:
        return dict(self.read_json(self.run_state_path(run_id)))

    def save_artifacts(self, run_id: str, artifacts: List[Dict[str, Any]]) -> None:
        self.atomic_write_json(self.artifacts_path(run_id), artifacts)

    def load_artifacts(self, run_id: str) -> List[Dict[str, Any]]:
        path = self.artifacts_path(run_id)
        if not path.exists():
            return []
        return list(self.read_json(path))

