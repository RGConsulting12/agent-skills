# Runtime Contract (Post-Phase 2A Cleanup)

This document defines the **current** runtime contract as implemented in `runtime/` after Phase 2A cleanup.

Scope:
- machine-readable plan execution
- typed run-state persistence
- runtime-managed delegation with review
- CLI command behavior

This is an implementation contract, not a roadmap.

## 1) Supported plan/task execution kinds

The runtime accepts `schema_version: "1.0"` plans and currently supports these task `execution.kind` values:

- `noop`
- `shell`
- `delegate`

Notes:
- Unknown execution kinds are rejected at validation time.
- `shell` tasks require `execution.command`.
- `delegate` tasks require `execution.delegation` with:
  - `objective`
  - `tool_allowlist`
  - `path_allowlist`
  - `max_steps`
  - `timeout_seconds`
  - `expected_artifact_types`
  - `max_delegation_attempts`
  - `review_required` (must be `true`)
- Delegation schema rejects additional undeclared fields.

## 2) Run-state and task-state lifecycle definitions

## Run status values

Run status is one of:
- `initialized`
- `running`
- `completed`
- `failed`
- `cancelled`

Operational behavior:
- `init-run` creates `initialized`.
- `step` moves `initialized -> running` on first execution attempt.
- Run becomes `completed` when all tasks are `completed`.
- Run becomes `failed` when failures remain and no runnable non-terminal progress exists.

## Task status values

Task status is one of:
- `pending_approval`
- `blocked`
- `ready`
- `running`
- `delegating`
- `waiting_review`
- `completed`
- `failed`
- `cancelled`

Transition model:
- `pending_approval` requires explicit task approval before becoming runnable.
- `blocked` indicates unmet dependencies.
- `ready` is schedulable.
- `running` is active execution of the parent task attempt.
- `delegating` indicates a delegation attempt is active.
- `waiting_review` indicates delegated output is awaiting review decision.
- terminal states: `completed`, `failed`, `cancelled`.

Scheduling:
- Runnable tasks are selected deterministically by `priority DESC`, then `task_id ASC`.
- The runtime executes one task attempt per `step`.

## 3) Delegation lifecycle and review model

Each delegation has:
- `delegation_id`
- `child_run_id`
- `lineage_depth` (currently fixed to `1`)
- `status`
- request/result/review payloads

Delegation status values supported by schema:
- `created`
- `running`
- `submitted_for_review`
- `accepted`
- `rejected`
- `failed`
- `cancelled`
- `exhausted`

Current operational flow:
1. Parent task enters `delegating`.
2. Delegation record is persisted immediately (`created`).
3. Policy checks + workspace preparation.
4. Child run executes inline (same process, no detached worker).
5. Outcomes:
   - success with required outputs -> `submitted_for_review`, parent `waiting_review`
   - failure/timeout/max-step/output-missing/policy-denied -> `failed` (or `exhausted`), parent `ready` or `failed`
6. Review applies to `submitted_for_review` only:
   - `accepted` -> parent task `completed`
   - `rejected` -> parent `ready` (or `failed` with `exhausted` if attempts exhausted)

Invariants:
- A parent task may have at most one active delegation at a time.
- Delegation attempt count increments when a new delegation is created.
- Every `delegation_id` referenced in task state is represented by a persisted delegation record.

## 4) Approval model split

The runtime has two independent approval channels:

## Task approval
- Command: `approve-task`
- Purpose: satisfy task-level `approval_required`.
- Behavior: idempotent; rejects unknown/non-approval/terminal tasks.

## Action approval
- Command: `approve-action`
- Purpose: satisfy policy-gated actions independent of task approval.
- Current category in use: `delegation_accept`.
- Behavior: idempotent by `(category, target_id)`.

Delegation review acceptance requires action approval when policy setting
`require_action_approval_for_delegation_accept` is enabled (enabled by default).

## 5) Artifact lifecycle

Artifact status values:
- `draft`
- `final`

Delegated artifact behavior:
- Child-produced artifacts copied into parent scope are persisted as `draft`.
- These artifacts are explicitly provisional (metadata carries provisional marker from child output path).
- On delegation review `accepted`, delegated artifacts are promoted to `final`.

Non-delegated task artifacts are typically emitted as `final` unless adapter payload specifies otherwise.

## 6) CLI commands and guarantees

Current commands:
- `validate-plan`
- `init-run`
- `approve-task`
- `approve-action`
- `step`
- `run`
- `status`
- `delegate-status`
- `review-delegation`
- `render-markdown`
- `trace`

Guarantees by command:
- `validate-plan`: validates schema + semantic rules; does not mutate runtime state.
- `init-run`: persists plan snapshot, typed initial run state, and artifacts store.
- `approve-task`: records task approval only.
- `approve-action`: records action approval only.
- `step`: executes at most one task attempt; returns whether progress occurred.
- `run`: loops `step` until terminal status, no progress, or `--max-steps`.
- `status`: returns persisted typed run-state (human or JSON).
- `delegate-status`: returns persisted delegation records (optionally filtered by parent task).
- `review-delegation`: applies accepted/rejected decision to a reviewable delegation.
- `render-markdown`: one-way export from typed state (`tasks/plan.md`, `tasks/todo.md`); does not mutate typed state semantics.
- `trace`: tails persisted trace events.

## 7) Known limitations / non-goals

Current non-goals and constraints:
- no nested delegation (`lineage_depth` fixed to `1`)
- no automatic patch application from delegation outputs
- no detached/background workers (child execution is inline)
- no container/worktree isolation for child execution in Phase 2A

## 8) Compatibility expectations for future phases

Compatibility expectations from this baseline:
- Keep `schema_version: "1.0"` behavior stable for existing valid plans.
- Preserve current execution kinds (`noop`, `shell`, `delegate`) and approval split semantics.
- Preserve delegation review gating contract (including action approval for acceptance by default).
- Treat new capabilities as additive; avoid breaking existing CLI workflows and persisted state shape without migration/versioning.

