"""Markdown rendering tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.adapters.generic_adapter import GenericAdapter
from runtime.observability.logger import TraceLogger
from runtime.orchestrator.runner import PlanRunner
from runtime.planner.validator import validate_plan_dict
from runtime.workspace.markdown_sync import render_plan_markdown, render_todo_markdown
from runtime.workspace.storage import StateStore


def sample_plan():
    return validate_plan_dict(
        {
            "schema_version": "1.0",
            "plan_id": "plan-md",
            "title": "Markdown Plan",
            "created_at": "2026-04-15T10:00:00Z",
            "created_by": "tester",
            "tasks": [
                {"task_id": "T1", "title": "one", "execution": {"kind": "noop"}},
                {"task_id": "T2", "title": "two", "depends_on": ["T1"], "execution": {"kind": "noop"}},
            ],
        }
    )


class MarkdownTests(unittest.TestCase):
    def test_renderer_outputs_from_typed_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "state"
            logs_dir = Path(tmp) / "logs"
            output_dir = Path(tmp) / "out"
            runner = PlanRunner(StateStore(str(state_dir)), TraceLogger(str(logs_dir)), GenericAdapter())
            plan = sample_plan()
            runner.init_run(plan, "run-md")
            run_state = runner.run_until_done("run-md")

            plan_path = render_plan_markdown(plan, run_state, output_dir=str(output_dir))
            todo_path = render_todo_markdown(plan, run_state, output_dir=str(output_dir))

            self.assertTrue(plan_path.exists())
            self.assertTrue(todo_path.exists())
            self.assertIn("T1", plan_path.read_text(encoding="utf-8"))
            self.assertIn("[x]", todo_path.read_text(encoding="utf-8"))
            plan_text = plan_path.read_text(encoding="utf-8")
            self.assertIn("approved_by", plan_text)
            self.assertIn("approved_at", plan_text)
            self.assertIn("last_error", plan_text)
            self.assertIn("produced_artifacts", plan_text)

    def test_markdown_edit_does_not_change_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "state"
            logs_dir = Path(tmp) / "logs"
            output_dir = Path(tmp) / "out"
            runner = PlanRunner(StateStore(str(state_dir)), TraceLogger(str(logs_dir)), GenericAdapter())
            plan = sample_plan()
            runner.init_run(plan, "run-md-2")
            run_state = runner.run_until_done("run-md-2")

            todo_path = render_todo_markdown(plan, run_state, output_dir=str(output_dir))
            todo_path.write_text("# tampered\n", encoding="utf-8")

            state_after = runner.load_run_state("run-md-2")
            self.assertEqual(state_after.status, "completed")
            self.assertEqual(state_after.tasks["T1"].status, "completed")

