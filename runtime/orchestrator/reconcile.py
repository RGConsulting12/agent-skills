"""Deterministic reconciliation helpers for Phase 2B."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from runtime.models import DelegationRecord, Plan, RunState, now_iso
from runtime.workspace.storage import StateStore
from runtime.workspace.transitions import refresh_nonterminal_statuses, summarize_tasks


ACTIVE_DELEGATION_STATUSES = {"created", "running", "submitted_for_review"}


@dataclass
class ReconcileResult:
    """Outcome of a reconciliation pass."""

    repaired: bool
    repairs_applied: int
    warnings: List[str] = field(default_factory=list)
    repair_entries: List[Dict[str, object]] = field(default_factory=list)


def _repair_entry(
    *,
    run_id: str,
    op_id: str,
    entity_kind: str,
    entity_id: str,
    operation: str,
    state_before: Dict[str, object] | None,
    state_after: Dict[str, object] | None,
    reason_code: str,
) -> Dict[str, object]:
    return {
        "op_id": op_id,
        "run_id": run_id,
        "entity_kind": entity_kind,
        "entity_id": entity_id,
        "operation": operation,
        "phase": "repair",
        "state_before": state_before,
        "state_after": state_after,
        "reason_code": reason_code,
        "trace": {"trace_id": None, "seq": None},
        "ts": now_iso(),
    }


def _next_op_id(run_state: RunState) -> str:
    counter = int(run_state.metadata.get("repair_op_counter", 0)) + 1
    run_state.metadata["repair_op_counter"] = counter
    return f"reconcile-{counter:06d}"


def reconcile_run_state(
    *,
    plan: Plan,
    run_state: RunState,
    store: StateStore,
) -> tuple[RunState, dict]:
    """Reconcile run_state with persisted delegation records.

    Rules:
    - Delegation file content is canonical for run_state.delegations.
    - Task delegation_ids must include all delegations whose parent_task_id matches.
    - active_delegation_id derives from active statuses + parent task status.
    - Reconciliation is deterministic and idempotent.
    """
    repairs = 0
    warnings: List[str] = []
    repair_entries: List[Dict[str, object]] = []

    # 1) Delegation records in run_state are overwritten by persisted records.
    persisted_delegations = {
        key: DelegationRecord.from_dict(value)
        for key, value in store.load_all_delegations(run_state.run_id).items()
    }
    current_ids = sorted(run_state.delegations.keys())
    persisted_ids = sorted(persisted_delegations.keys())
    if current_ids != persisted_ids:
        before = {"delegation_ids": current_ids}
        run_state.delegations = dict(sorted(persisted_delegations.items(), key=lambda item: item[0]))
        after = {"delegation_ids": sorted(run_state.delegations.keys())}
        repairs += 1
        repair_entries.append(
            _repair_entry(
                run_id=run_state.run_id,
                op_id=_next_op_id(run_state),
                entity_kind="run",
                entity_id=run_state.run_id,
                operation="reconciliation_repair",
                state_before=before,
                state_after=after,
                reason_code="DELEGATION_INDEX_REPAIRED",
            )
        )

    # 2) Ensure task delegation ids include all matching persisted delegations.
    by_task: Dict[str, List[str]] = {}
    for delegation_id, record in sorted(run_state.delegations.items()):
        by_task.setdefault(record.parent_task_id, []).append(delegation_id)

    for task_id in sorted(run_state.tasks.keys()):
        task_state = run_state.tasks[task_id]
        expected_ids = sorted(set(task_state.delegation_ids) | set(by_task.get(task_id, [])))
        if expected_ids != sorted(task_state.delegation_ids):
            before = {"delegation_ids": list(task_state.delegation_ids)}
            task_state.delegation_ids = expected_ids
            after = {"delegation_ids": list(task_state.delegation_ids)}
            repairs += 1
            repair_entries.append(
                _repair_entry(
                    run_id=run_state.run_id,
                    op_id=_next_op_id(run_state),
                    entity_kind="task",
                    entity_id=task_id,
                    operation="reconciliation_repair",
                    state_before=before,
                    state_after=after,
                    reason_code="TASK_DELEGATION_IDS_REPAIRED",
                )
            )

        # 3) Recompute active_delegation_id deterministically.
        candidates = [
            delegation_id
            for delegation_id in task_state.delegation_ids
            if delegation_id in run_state.delegations
            and run_state.delegations[delegation_id].status in ACTIVE_DELEGATION_STATUSES
            and task_state.status in {"delegating", "waiting_review"}
        ]
        candidates.sort()
        selected = candidates[0] if candidates else None
        if len(candidates) > 1:
            warnings.append(
                f"task {task_id} has multiple active delegation candidates; chose {selected}"
            )
        if task_state.active_delegation_id != selected:
            before = {"active_delegation_id": task_state.active_delegation_id}
            task_state.active_delegation_id = selected
            after = {"active_delegation_id": task_state.active_delegation_id}
            repairs += 1
            repair_entries.append(
                _repair_entry(
                    run_id=run_state.run_id,
                    op_id=_next_op_id(run_state),
                    entity_kind="task",
                    entity_id=task_id,
                    operation="reconciliation_repair",
                    state_before=before,
                    state_after=after,
                    reason_code="TASK_ACTIVE_DELEGATION_REPAIRED",
                )
            )

    # 4) Recompute summaries/statuses from authoritative task state.
    previous_summary = dict(run_state.summary)
    refresh_nonterminal_statuses(plan, run_state)
    run_state.summary = summarize_tasks(run_state)
    if previous_summary != run_state.summary:
        repairs += 1
        repair_entries.append(
            _repair_entry(
                run_id=run_state.run_id,
                op_id=_next_op_id(run_state),
                entity_kind="run",
                entity_id=run_state.run_id,
                operation="reconciliation_repair",
                state_before={"summary": previous_summary},
                state_after={"summary": dict(run_state.summary)},
                reason_code="SUMMARY_RECOMPUTED",
            )
        )

    run_state.reconciliation = {
        "last_reconciled_at": now_iso(),
        "algorithm_version": "2b-v1",
        "repairs_applied": repairs,
        "warnings": warnings,
        "last_journal_offset": 0,  # filled by caller after journaling.
    }
    # Persist deterministic repair journal entries.
    for entry in repair_entries:
        store.append_journal_entry(run_state.run_id, entry)
    journal_offset = len(store.read_journal(run_state.run_id))
    run_state.reconciliation["last_journal_offset"] = journal_offset
    return run_state, {
        "repaired": repairs > 0,
        "repairs_applied": repairs,
        "warnings": warnings,
        "repair_entries": repair_entries,
        "last_reconciled_at": run_state.reconciliation["last_reconciled_at"],
        "algorithm_version": run_state.reconciliation["algorithm_version"],
        "last_journal_offset": journal_offset,
    }

