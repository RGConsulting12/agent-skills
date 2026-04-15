"""CLI command tests."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


def write_plan(path: Path) -> None:
    payload = {
        "schema_version": "1.0",
        "plan_id": "plan-cli",
        "title": "CLI Plan",
        "created_at": "2026-04-15T10:00:00Z",
        "created_by": "tester",
        "tasks": [
            {"task_id": "T1", "title": "one", "execution": {"kind": "noop"}},
            {"task_id": "T2", "title": "two", "depends_on": ["T1"], "execution": {"kind": "noop"}},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


class CLITests(unittest.TestCase):
    def test_validate_plan_and_run_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "plan.json"
            write_plan(plan_path)
            state_dir = root / "state"
            logs_dir = root / "logs"
            output_dir = root / "out"

            cmd_base = ["python3", "-m", "runtime.cli"]
            validated = subprocess.run(
                cmd_base + ["validate-plan", "--plan", str(plan_path)],
                cwd="/workspace",
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(validated.returncode, 0, validated.stderr)

            initialized = subprocess.run(
                cmd_base
                + [
                    "init-run",
                    "--plan",
                    str(plan_path),
                    "--run-id",
                    "run-cli",
                    "--state-dir",
                    str(state_dir),
                    "--logs-dir",
                    str(logs_dir),
                ],
                cwd="/workspace",
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)

            ran = subprocess.run(
                cmd_base
                + [
                    "run",
                    "--run-id",
                    "run-cli",
                    "--state-dir",
                    str(state_dir),
                    "--logs-dir",
                    str(logs_dir),
                ],
                cwd="/workspace",
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(ran.returncode, 0, ran.stderr)
            data = json.loads(ran.stdout)
            self.assertEqual(data["status"], "completed")

            rendered = subprocess.run(
                cmd_base
                + [
                    "render-markdown",
                    "--run-id",
                    "run-cli",
                    "--state-dir",
                    str(state_dir),
                    "--logs-dir",
                    str(logs_dir),
                    "--output-dir",
                    str(output_dir),
                ],
                cwd="/workspace",
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            self.assertTrue((output_dir / "tasks" / "plan.md").exists())
            self.assertTrue((output_dir / "tasks" / "todo.md").exists())

