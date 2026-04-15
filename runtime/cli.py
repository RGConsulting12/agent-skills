"""CLI entrypoint for the runtime."""

from __future__ import annotations

import argparse
import json
import sys

from runtime.adapters.generic_adapter import GenericAdapter
from runtime.observability.logger import TraceLogger
from runtime.orchestrator.runner import PlanRunner
from runtime.planner.validator import PlanValidationError, load_and_validate_plan
from runtime.workspace.markdown_sync import render_plan_markdown, render_todo_markdown
from runtime.workspace.storage import StateStore


def _build_runner(args: argparse.Namespace) -> PlanRunner:
    if args.adapter != "generic":
        raise ValueError("Runtime supports only --adapter generic")
    return PlanRunner(
        store=StateStore(args.state_dir),
        logger=TraceLogger(args.logs_dir),
        adapter=GenericAdapter(),
    )


def cmd_validate_plan(args: argparse.Namespace) -> int:
    try:
        plan = load_and_validate_plan(args.plan)
    except (PlanValidationError, ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"invalid plan: {exc}", file=sys.stderr)
        return 1
    print(f"valid plan: {plan.plan_id} ({len(plan.tasks)} tasks)")
    return 0


def cmd_init_run(args: argparse.Namespace) -> int:
    plan = load_and_validate_plan(args.plan)
    runner = _build_runner(args)
    run_state = runner.init_run(plan, args.run_id)
    print(f"initialized run {run_state.run_id} for plan {run_state.plan_id}")
    return 0


def cmd_approve_task(args: argparse.Namespace) -> int:
    runner = _build_runner(args)
    run_state = runner.approve_task(args.run_id, args.task_id, args.approved_by)
    print(f"approved task {args.task_id}; status={run_state.tasks[args.task_id].status}")
    return 0


def cmd_step(args: argparse.Namespace) -> int:
    runner = _build_runner(args)
    run_state, progressed = runner.step(args.run_id)
    print(
        json.dumps(
            {
                "run_id": run_state.run_id,
                "status": run_state.status,
                "progressed": progressed,
                "summary": run_state.summary,
            },
            sort_keys=True,
        )
    )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    runner = _build_runner(args)
    run_state = runner.run_until_done(args.run_id, max_steps=args.max_steps)
    print(
        json.dumps(
            {
                "run_id": run_state.run_id,
                "status": run_state.status,
                "summary": run_state.summary,
            },
            sort_keys=True,
        )
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    store = StateStore(args.state_dir)
    run_state = store.load_run_state(args.run_id)
    if args.json:
        print(json.dumps(run_state, indent=2, sort_keys=True))
    else:
        print(f"run_id: {run_state['run_id']}")
        print(f"status: {run_state['status']}")
        print("summary:")
        for key, value in sorted(run_state.get("summary", {}).items()):
            print(f"  {key}: {value}")
    return 0


def cmd_render_markdown(args: argparse.Namespace) -> int:
    runner = _build_runner(args)
    plan = runner.load_plan(args.run_id)
    run_state = runner.load_run_state(args.run_id)
    plan_path = render_plan_markdown(plan, run_state, output_dir=args.output_dir)
    todo_path = render_todo_markdown(plan, run_state, output_dir=args.output_dir)
    print(f"generated {plan_path}")
    print(f"generated {todo_path}")
    return 0


def cmd_delegate_status(args: argparse.Namespace) -> int:
    store = StateStore(args.state_dir)
    run_state = store.load_run_state(args.run_id)
    delegations = run_state.get("delegations", {})
    if args.task_id:
        delegations = {
            key: value for key, value in delegations.items() if value.get("parent_task_id") == args.task_id
        }
    if args.json:
        print(json.dumps(delegations, indent=2, sort_keys=True))
    else:
        for delegation_id in sorted(delegations):
            item = delegations[delegation_id]
            print(
                f"{delegation_id}: task={item.get('parent_task_id')} "
                f"status={item.get('status')} child_run_id={item.get('child_run_id')}"
            )
    return 0


def cmd_review_delegation(args: argparse.Namespace) -> int:
    runner = _build_runner(args)
    run_state = runner.review_delegation(
        args.run_id,
        args.delegation_id,
        decision=args.decision,
        reviewed_by=args.reviewed_by,
        notes=args.notes,
    )
    print(
        json.dumps(
            {
                "run_id": run_state.run_id,
                "status": run_state.status,
                "delegation_id": args.delegation_id,
                "summary": run_state.summary,
            },
            sort_keys=True,
        )
    )
    return 0


def cmd_approve_action(args: argparse.Namespace) -> int:
    runner = _build_runner(args)
    run_state = runner.approve_action(args.run_id, args.category, args.target_id, args.approved_by)
    print(
        json.dumps(
            {
                "run_id": run_state.run_id,
                "status": run_state.status,
                "approved": {"category": args.category, "target_id": args.target_id},
            },
            sort_keys=True,
        )
    )
    return 0


def cmd_trace(args: argparse.Namespace) -> int:
    logger = TraceLogger(args.logs_dir)
    events = logger.read_tail(args.run_id, tail=args.tail)
    for event in events:
        print(json.dumps(event, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Runtime CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-plan", help="Validate plan JSON")
    validate.add_argument("--plan", required=True)
    validate.set_defaults(func=cmd_validate_plan)

    init_run = subparsers.add_parser("init-run", help="Initialize typed run state")
    init_run.add_argument("--plan", required=True)
    init_run.add_argument("--run-id", required=True)
    init_run.add_argument("--adapter", default="generic")
    init_run.add_argument("--state-dir", default=".agent-runtime/state")
    init_run.add_argument("--logs-dir", default=".agent-runtime/logs")
    init_run.set_defaults(func=cmd_init_run)

    approve = subparsers.add_parser("approve-task", help="Approve a task")
    approve.add_argument("--run-id", required=True)
    approve.add_argument("--task-id", required=True)
    approve.add_argument("--approved-by", required=True)
    approve.add_argument("--adapter", default="generic")
    approve.add_argument("--state-dir", default=".agent-runtime/state")
    approve.add_argument("--logs-dir", default=".agent-runtime/logs")
    approve.set_defaults(func=cmd_approve_task)

    step = subparsers.add_parser("step", help="Execute one task attempt")
    step.add_argument("--run-id", required=True)
    step.add_argument("--adapter", default="generic")
    step.add_argument("--state-dir", default=".agent-runtime/state")
    step.add_argument("--logs-dir", default=".agent-runtime/logs")
    step.set_defaults(func=cmd_step)

    run = subparsers.add_parser("run", help="Execute until terminal or max steps")
    run.add_argument("--run-id", required=True)
    run.add_argument("--max-steps", type=int, default=None)
    run.add_argument("--adapter", default="generic")
    run.add_argument("--state-dir", default=".agent-runtime/state")
    run.add_argument("--logs-dir", default=".agent-runtime/logs")
    run.set_defaults(func=cmd_run)

    status = subparsers.add_parser("status", help="Show run status")
    status.add_argument("--run-id", required=True)
    status.add_argument("--state-dir", default=".agent-runtime/state")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    render = subparsers.add_parser("render-markdown", help="Generate markdown from typed state")
    render.add_argument("--run-id", required=True)
    render.add_argument("--output-dir", default=".")
    render.add_argument("--adapter", default="generic")
    render.add_argument("--state-dir", default=".agent-runtime/state")
    render.add_argument("--logs-dir", default=".agent-runtime/logs")
    render.set_defaults(func=cmd_render_markdown)

    trace = subparsers.add_parser("trace", help="Tail run trace")
    trace.add_argument("--run-id", required=True)
    trace.add_argument("--tail", type=int, default=20)
    trace.add_argument("--logs-dir", default=".agent-runtime/logs")
    trace.set_defaults(func=cmd_trace)

    delegate_status = subparsers.add_parser("delegate-status", help="Show delegation status")
    delegate_status.add_argument("--run-id", required=True)
    delegate_status.add_argument("--task-id")
    delegate_status.add_argument("--state-dir", default=".agent-runtime/state")
    delegate_status.add_argument("--json", action="store_true")
    delegate_status.set_defaults(func=cmd_delegate_status)

    review = subparsers.add_parser("review-delegation", help="Review delegation result")
    review.add_argument("--run-id", required=True)
    review.add_argument("--delegation-id", required=True)
    review.add_argument("--decision", required=True, choices=["accepted", "rejected"])
    review.add_argument("--reviewed-by", required=True)
    review.add_argument("--notes")
    review.add_argument("--adapter", default="generic")
    review.add_argument("--state-dir", default=".agent-runtime/state")
    review.add_argument("--logs-dir", default=".agent-runtime/logs")
    review.set_defaults(func=cmd_review_delegation)

    approve_action = subparsers.add_parser("approve-action", help="Approve policy/action gate")
    approve_action.add_argument("--run-id", required=True)
    approve_action.add_argument("--category", required=True)
    approve_action.add_argument("--target-id", required=True)
    approve_action.add_argument("--approved-by", required=True)
    approve_action.add_argument("--adapter", default="generic")
    approve_action.add_argument("--state-dir", default=".agent-runtime/state")
    approve_action.add_argument("--logs-dir", default=".agent-runtime/logs")
    approve_action.set_defaults(func=cmd_approve_action)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:  # pragma: no cover - CLI guardrail
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

