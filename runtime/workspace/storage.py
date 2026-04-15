"""Persistent storage helpers for typed runtime state."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from runtime.schemas.loader import (
    validate_artifact,
    validate_delegation,
    validate_journal_entry,
    validate_run_state,
)


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

    def journal_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "ops.jsonl"

    def delegations_dir(self, run_id: str) -> Path:
        path = self.run_dir(run_id) / "delegations"
        path.mkdir(parents=True, exist_ok=True)
        return path

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
        validate_run_state(run_state_data)
        self.atomic_write_json(self.run_state_path(run_id), run_state_data)

    def load_run_state(self, run_id: str) -> Dict[str, Any]:
        data = dict(self.read_json(self.run_state_path(run_id)))
        validate_run_state(data)
        return data

    def save_artifacts(self, run_id: str, artifacts: List[Dict[str, Any]]) -> None:
        for artifact in artifacts:
            validate_artifact(artifact)
        self.atomic_write_json(self.artifacts_path(run_id), artifacts)

    def load_artifacts(self, run_id: str) -> List[Dict[str, Any]]:
        path = self.artifacts_path(run_id)
        if not path.exists():
            return []
        artifacts = list(self.read_json(path))
        for artifact in artifacts:
            validate_artifact(artifact)
        return artifacts

    def save_delegation(self, run_id: str, delegation_data: Dict[str, Any]) -> None:
        validate_delegation(delegation_data)
        path = self.delegations_dir(run_id) / f"{delegation_data['delegation_id']}.json"
        self.atomic_write_json(path, delegation_data)

    def load_delegation(self, run_id: str, delegation_id: str) -> Dict[str, Any]:
        path = self.delegations_dir(run_id) / f"{delegation_id}.json"
        data = dict(self.read_json(path))
        validate_delegation(data)
        return data

    def list_delegation_ids(self, run_id: str) -> List[str]:
        ids: List[str] = []
        for path in sorted(self.delegations_dir(run_id).glob("*.json")):
            ids.append(path.stem)
        return ids

    def load_all_delegations(self, run_id: str) -> Dict[str, Dict[str, Any]]:
        items: Dict[str, Dict[str, Any]] = {}
        for delegation_id in self.list_delegation_ids(run_id):
            items[delegation_id] = self.load_delegation(run_id, delegation_id)
        return items

    def append_journal_entry(self, run_id: str, entry: Dict[str, Any]) -> int:
        validate_journal_entry(entry)
        path = self.journal_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        count += 1
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
        return count + 1

    def read_journal(self, run_id: str) -> List[Dict[str, Any]]:
        path = self.journal_path(run_id)
        if not path.exists():
            return []
        entries: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                payload = json.loads(text)
                validate_journal_entry(payload)
                entries.append(payload)
        return entries


