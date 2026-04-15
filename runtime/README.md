# Runtime (Phase 2A)

Minimal, host-agnostic runtime that executes machine-readable plans with:

- typed state as source of truth
- task-level approvals
- runtime-managed delegation with review-required acceptance
- deterministic scheduling and event ordering
- one-way markdown rendering from typed state
- adapter surface limited to `noop` and `shell`

## Layout

```text
runtime/
  cli.py
  models.py
  schemas/
  planner/
  workspace/
  orchestrator/
  adapters/
  observability/
  delegation/
  policy/
  examples/sample-plan.json
  examples/sample-plan-phase2a.json
```

## Quick demo commands

From repo root:

```bash
python3 -m runtime.cli validate-plan --plan runtime/examples/sample-plan-phase2a.json

python3 -m runtime.cli init-run \
  --plan runtime/examples/sample-plan-phase2a.json \
  --run-id demo-run-p2a

python3 -m runtime.cli step --run-id demo-run-p2a
python3 -m runtime.cli status --run-id demo-run-p2a --json

python3 -m runtime.cli approve-task \
  --run-id demo-run-p2a \
  --task-id T2 \
  --approved-by you

python3 -m runtime.cli run --run-id demo-run-p2a --max-steps 2
python3 -m runtime.cli delegate-status --run-id demo-run-p2a --json
python3 -m runtime.cli approve-action \
  --run-id demo-run-p2a \
  --category delegation_accept \
  --target-id dlg-0001 \
  --approved-by you
python3 -m runtime.cli review-delegation \
  --run-id demo-run-p2a \
  --delegation-id dlg-0001 \
  --decision accepted \
  --reviewed-by you
python3 -m runtime.cli run --run-id demo-run-p2a

python3 -m runtime.cli render-markdown --run-id demo-run-p2a --output-dir .
python3 -m runtime.cli trace --run-id demo-run-p2a --tail 80
```

Generated files:

- typed state: `.agent-runtime/state/demo-run-p2a/`
- trace logs: `.agent-runtime/logs/demo-run-p2a.jsonl`
- delegation workspaces: `.agent-runtime/workspaces/demo-run-p2a/`
- markdown exports: `tasks/plan.md`, `tasks/todo.md`

## Run tests

```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

## Phase 2A notes

- Delegation is runtime-managed inline (no detached workers, no nested delegation).
- Parent tasks remain DAG nodes; delegation uses `delegating` and `waiting_review` task statuses.
- Child outputs copied back before review are persisted as `draft` artifacts and finalized only after review acceptance.
- Action approvals are separate from task approvals (`approve-action` vs `approve-task`).
- Child failures include timeout, max child step exhaustion, terminal child run failure, and missing required output artifact types.
- Each parent task allows at most one active delegation at a time.

Remaining limitations:

- Nested delegation is intentionally unsupported in Phase 2A (`lineage_depth` fixed at 1).
- No automatic patch application is performed in Phase 2A (artifact/result acceptance only).
- Child execution still uses the same process runtime with workspace isolation, not containers/worktrees.

