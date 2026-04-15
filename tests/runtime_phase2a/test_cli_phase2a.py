"""CLI coverage for Phase 2A delegation commands."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


def write_delegate_plan(path: Path) -> None:
    payload = {
        "schema_version": "1.0",
        "plan_id": "plan-cli-p2a",
        "title": "CLI Delegation",
        "created_at": "2026-04-15T10:00:00Z",
        "created_by": "tester",
        "tasks": [
            {
                "task_id": "T1",
                "title": "delegate",
                "execution": {
                    "kind": "delegate",
                    "delegation": {
                        "objective": "child",
                        "tool_allowlist": ["noop"],
                        "path_allowlist": ["/workspace/runtime/examples"],
                        "path_denylist": [],
                        "max_steps": 1,
                        "timeout_seconds": 30,
                        "expected_artifact_types": ["report"],
                        "max_delegation_attempts": 1,
                        "review_required": True
                    },
                },
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


class Phase2ACLITests(unittest.TestCase):
    def test_delegate_status_and_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_path = root / "plan.json"
            write_delegate_plan(plan_path)
            state_dir = root / "state"
            logs_dir = root / "logs"

            cmd_base = ["python3", "-m", "runtime.cli"]
            init_proc = subprocess.run(
                cmd_base
                + [
                    "init-run",
                    "--plan",
                    str(plan_path),
                    "--run-id",
                    "run-p2a-cli",
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
            self.assertEqual(init_proc.returncode, 0, init_proc.stderr)

            step_proc = subprocess.run(
                cmd_base
                + [
                    "step",
                    "--run-id",
                    "run-p2a-cli",
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
            self.assertEqual(step_proc.returncode, 0, step_proc.stderr)

            status_proc = subprocess.run(
                cmd_base
                + [
                    "delegate-status",
                    "--run-id",
                    "run-p2a-cli",
                    "--state-dir",
                    str(state_dir),
                    "--json",
                ],
                cwd="/workspace",
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(status_proc.returncode, 0, status_proc.stderr)
            data = json.loads(status_proc.stdout)
            self.assertEqual(len(data), 1)
            delegation_id = next(iter(data))

            approve_proc = subprocess.run(
                cmd_base
                + [
                    "approve-action",
                    "--run-id",
                    "run-p2a-cli",
                    "--category",
                    "delegation_accept",
                    "--target-id",
                    delegation_id,
                    "--approved-by",
                    "security",
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
            self.assertEqual(approve_proc.returncode, 0, approve_proc.stderr)

            review_proc = subprocess.run(
                cmd_base
                + [
                    "review-delegation",
                    "--run-id",
                    "run-p2a-cli",
                    "--delegation-id",
                    delegation_id,
                    "--decision",
                    "accepted",
                    "--reviewed-by",
                    "qa",
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
            self.assertEqual(review_proc.returncode, 0, review_proc.stderr)

