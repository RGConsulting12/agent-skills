"""Storage boundary schema enforcement tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.workspace.storage import StateStore


def valid_run_state() -> dict:
    return {
        "schema_version": "1.0",
        "run_id": "run-x",
        "plan_id": "plan-x",
        "status": "running",
        "created_at": "2026-04-15T10:00:00Z",
        "started_at": None,
        "ended_at": None,
        "tasks": {
            "T1": {
                "task_id": "T1",
                "status": "ready",
                "attempts": 0,
                "max_retries": 0,
                "last_error": None,
                "approval": {"required": False, "approved": False, "approved_by": None, "approved_at": None},
                "depends_on": [],
                "started_at": None,
                "ended_at": None,
                "produced_artifacts": [],
            }
        },
        "artifacts": [],
        "current_task_id": None,
        "summary": {},
        "metadata": {},
    }


def valid_artifact() -> dict:
    return {
        "artifact_id": "art-1",
        "run_id": "run-x",
        "producer_task_id": "T1",
        "type": "report",
        "status": "final",
        "path": None,
        "content": {"ok": True},
        "created_at": "2026-04-15T10:00:00Z",
        "metadata": {},
    }


class StorageSchemaTests(unittest.TestCase):
    def test_save_run_state_validates_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = StateStore(str(Path(tmp) / "state"))
            bad = valid_run_state()
            del bad["status"]
            with self.assertRaises(ValueError):
                store.save_run_state("run-x", bad)

    def test_save_artifacts_validates_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = StateStore(str(Path(tmp) / "state"))
            bad = valid_artifact()
            del bad["type"]
            with self.assertRaises(ValueError):
                store.save_artifacts("run-x", [bad])

    def test_load_run_state_validates_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "state"
            store = StateStore(str(root))
            run_dir = root / "run-y"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "run_state.json").write_text('{"oops": true}\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                store.load_run_state("run-y")

    def test_load_artifacts_validates_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "state"
            store = StateStore(str(root))
            run_dir = root / "run-z"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "artifacts.json").write_text('[{"bad": "x"}]\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                store.load_artifacts("run-z")

