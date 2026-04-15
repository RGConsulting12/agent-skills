"""Trace helpers with deterministic sequencing."""

from __future__ import annotations

import uuid
from typing import Any, Dict


def new_trace_id() -> str:
    """Create a run-level trace identifier."""
    return f"trc-{uuid.uuid4().hex[:10]}"


def next_span_id(run_state_metadata: Dict[str, Any]) -> str:
    """Create deterministic span ids by incrementing sequence in state metadata."""
    counter = int(run_state_metadata.get("span_counter", 0)) + 1
    run_state_metadata["span_counter"] = counter
    return f"spn-{counter:04d}"


def next_event_seq(run_state_metadata: Dict[str, Any]) -> int:
    """Increment event sequence for deterministic log ordering."""
    seq = int(run_state_metadata.get("event_seq", 0)) + 1
    run_state_metadata["event_seq"] = seq
    return seq


def sync_event_seq(run_state_metadata: Dict[str, Any], observed_seq: int) -> None:
    """Advance in-memory sequence to at least the observed value."""
    current = int(run_state_metadata.get("event_seq", 0))
    if observed_seq > current:
        run_state_metadata["event_seq"] = observed_seq


def make_event(
    *,
    seq: int,
    run_id: str,
    trace_id: str,
    span_id: str,
    event: str,
    ts: str,
    payload: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a trace event dictionary."""
    data: Dict[str, Any] = {
        "seq": seq,
        "ts": ts,
        "run_id": run_id,
        "trace_id": trace_id,
        "span_id": span_id,
        "event": event,
    }
    if payload:
        data.update(payload)
    return data

