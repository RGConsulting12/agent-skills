"""Delegation review lifecycle helpers."""

from __future__ import annotations

from runtime.models import DelegationRecord, now_iso


def apply_review(
    delegation: DelegationRecord,
    *,
    decision: str,
    reviewed_by: str,
    notes: str | None = None,
) -> None:
    """Apply accepted/rejected decision to a review-submitted delegation."""
    if delegation.status != "submitted_for_review":
        raise ValueError(f"delegation '{delegation.delegation_id}' is not reviewable")
    if decision not in {"accepted", "rejected"}:
        raise ValueError("decision must be accepted or rejected")
    delegation.status = decision
    delegation.review_decision = decision
    delegation.reviewed_by = reviewed_by
    delegation.reviewed_at = now_iso()
    delegation.review_notes = notes
    delegation.updated_at = delegation.reviewed_at

