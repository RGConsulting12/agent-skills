# Phase 1 Runtime

Minimal, host-agnostic runtime that executes machine-readable plans with:

- typed state as source of truth
- task-level approvals
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
  examples/sample-plan.json
```

## Quick demo commands

From repo root:

```bash
python3 -m runtime.cli validate-plan --plan runtime/examples/sample-plan.json

python3 -m runtime.cli init-run \
  --plan runtime/examples/sample-plan.json \
  --run-id demo-run

python3 -m runtime.cli step --run-id demo-run
python3 -m runtime.cli status --run-id demo-run --json

python3 -m runtime.cli approve-task \
  --run-id demo-run \
  --task-id T2 \
  --approved-by you

python3 -m runtime.cli run --run-id demo-run

python3 -m runtime.cli render-markdown --run-id demo-run --output-dir .
python3 -m runtime.cli trace --run-id demo-run --tail 50
```

Generated files:

- typed state: `.agent-runtime/state/demo-run/`
- trace logs: `.agent-runtime/logs/demo-run.jsonl`
- markdown exports: `tasks/plan.md`, `tasks/todo.md`

## Run tests

```bash
python3 -m unittest discover -s tests/runtime_phase1 -p "test_*.py"
```

## Hardening notes (Phase 1)

- Run terminal semantics now allow independent ready/running work to continue after a branch failure. The run fails only when at least one task is failed and there is no ready/running work remaining.
- JSON Schema is enforced in code for plan validation and at run_state/artifact persistence boundaries.
- Task approvals enforce invariants (unknown IDs, non-approval tasks, terminal tasks are rejected) and repeated approvals are idempotent no-ops.
- Trace sequence metadata is persisted after every event to reduce duplicate sequence numbers after abrupt termination.

Remaining limitation:

- If a crash happens between writing the event log line and persisting run_state metadata, the next process may reuse a sequence number. This window is small but not fully eliminated without transactional journaling.

