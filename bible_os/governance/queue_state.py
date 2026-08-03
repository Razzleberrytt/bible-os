"""Deterministically reduce immutable queue documents and transition events."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

_QUEUE_ID = re.compile(r"^vrq_[a-z0-9]{12,}$")
_TRANSITION_ID = re.compile(r"^vqt_[a-z0-9]{12,}$")
_DECISION_ID = re.compile(r"^vrd_[a-z0-9]{12,}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")

_QUEUE_STATUSES = {
    "queued",
    "in-review",
    "needs-evidence",
    "accepted",
    "rejected",
    "withdrawn",
}
_TRANSITION_SOURCE_STATUSES = {"queued", "in-review", "needs-evidence"}
_TRANSITION_TARGET_STATUSES = {
    "accepted",
    "rejected",
    "needs-evidence",
    "withdrawn",
}
_TERMINAL_STATUSES = {"accepted", "rejected", "withdrawn"}

_EXPECTED_TRANSITION_CONSTANTS = {
    "schema_version": "1.0.0",
    "transition_kind": "apply-human-governance-decision",
    "record_policy": "append-only",
    "application_scope": "queue-governance-status-only",
    "status_effect": "effective-governance-status",
    "queue_document_mutation": "not-performed",
    "effective_status_source": "append-only-transition-event",
    "materialization_authority": "none",
    "mapping_execution_authority": "none",
    "corpus_mutation_authority": "none",
    "release_authority": "none",
}


class QueueStateError(ValueError):
    """Raised when the governance event stream cannot be reduced safely."""


@dataclass(frozen=True, slots=True)
class QueueState:
    """Frozen result of reducing one queue document and its transition stream."""

    queue_item_id: str
    queue_item_sha256: str
    initial_status: str
    effective_status: str
    status_source: str
    transition_count: int
    effective_transition_ids: tuple[str, ...]
    superseded_transition_ids: tuple[str, ...]
    last_applied_at: str | None


@dataclass(frozen=True, slots=True)
class _Transition:
    transition_id: str
    queue_item_id: str
    queue_item_sha256: str
    decision_id: str
    decision_outcome: str
    from_status: str
    to_status: str
    applied_at: str
    applied_at_utc: datetime
    supersedes_transition_id: str | None


def _decode_document(document: bytes, *, label: str) -> dict[str, Any]:
    if not isinstance(document, bytes):
        raise QueueStateError(f"{label} must be supplied as immutable bytes")
    try:
        value = json.loads(document.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QueueStateError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise QueueStateError(f"{label} must decode to a JSON object")
    return value


def _text(record: Mapping[str, Any], field: str, *, label: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise QueueStateError(f"{label}.{field} must be a non-empty string")
    return value


def _match(value: str, pattern: re.Pattern[str], *, label: str) -> str:
    if pattern.fullmatch(value) is None:
        raise QueueStateError(f"{label} has an invalid identifier or digest format")
    return value


def _timestamp(value: str, *, label: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise QueueStateError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise QueueStateError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_queue_document(
    queue_item: Mapping[str, Any], queue_item_sha256: str
) -> tuple[str, str]:
    if queue_item.get("schema_version") != "1.0.0":
        raise QueueStateError("queue item schema_version must be 1.0.0")

    queue_item_id = _match(
        _text(queue_item, "queue_item_id", label="queue item"),
        _QUEUE_ID,
        label="queue item.queue_item_id",
    )
    status = _text(queue_item, "status", label="queue item")
    if status not in _QUEUE_STATUSES:
        raise QueueStateError(f"unsupported queue status: {status}")

    if queue_item.get("materialization_state") != "not-materialized":
        raise QueueStateError("queue item must remain not-materialized")
    if queue_item.get("execution_eligible") is not False:
        raise QueueStateError("queue item must not be execution eligible")
    if queue_item.get("publication_eligible") is not False:
        raise QueueStateError("queue item must not be publication eligible")
    if _SHA256.fullmatch(queue_item_sha256) is None:
        raise QueueStateError("computed queue item digest is invalid")
    return queue_item_id, status


def _parse_transition(document: bytes) -> _Transition:
    record = _decode_document(document, label="transition")

    for field, expected in _EXPECTED_TRANSITION_CONSTANTS.items():
        if record.get(field) != expected:
            raise QueueStateError(f"transition.{field} must equal {expected!r}")
    if record.get("execution_eligible") is not False:
        raise QueueStateError("transition must not be execution eligible")
    if record.get("publication_eligible") is not False:
        raise QueueStateError("transition must not be publication eligible")

    transition_id = _match(
        _text(record, "transition_id", label="transition"),
        _TRANSITION_ID,
        label="transition.transition_id",
    )
    queue_item_id = _match(
        _text(record, "queue_item_id", label="transition"),
        _QUEUE_ID,
        label="transition.queue_item_id",
    )
    queue_item_sha256 = _match(
        _text(record, "queue_item_sha256", label="transition"),
        _SHA256,
        label="transition.queue_item_sha256",
    )
    decision_id = _match(
        _text(record, "decision_id", label="transition"),
        _DECISION_ID,
        label="transition.decision_id",
    )
    decision_sha256 = _text(record, "decision_sha256", label="transition")
    _match(decision_sha256, _SHA256, label="transition.decision_sha256")

    decision_outcome = _text(record, "decision_outcome", label="transition")
    from_status = _text(record, "from_status", label="transition")
    to_status = _text(record, "to_status", label="transition")
    if from_status not in _TRANSITION_SOURCE_STATUSES:
        raise QueueStateError(f"invalid transition source status: {from_status}")
    if to_status not in _TRANSITION_TARGET_STATUSES:
        raise QueueStateError(f"invalid transition target status: {to_status}")
    if decision_outcome != to_status:
        raise QueueStateError("transition decision_outcome must equal to_status")

    actors = record.get("applied_by")
    if not isinstance(actors, list) or not actors:
        raise QueueStateError("transition.applied_by must contain a human actor")
    for actor in actors:
        if not isinstance(actor, dict) or actor.get("actor_type") != "human":
            raise QueueStateError("every transition actor must be human")

    applied_at = _text(record, "applied_at", label="transition")
    applied_at_utc = _timestamp(applied_at, label="transition.applied_at")

    supersedes = record.get("supersedes_transition_id")
    if supersedes is not None:
        if not isinstance(supersedes, str):
            raise QueueStateError("supersedes_transition_id must be a string or null")
        _match(
            supersedes,
            _TRANSITION_ID,
            label="transition.supersedes_transition_id",
        )

    return _Transition(
        transition_id=transition_id,
        queue_item_id=queue_item_id,
        queue_item_sha256=queue_item_sha256,
        decision_id=decision_id,
        decision_outcome=decision_outcome,
        from_status=from_status,
        to_status=to_status,
        applied_at=applied_at,
        applied_at_utc=applied_at_utc,
        supersedes_transition_id=supersedes,
    )


def reduce_queue_state(
    queue_item_document: bytes,
    transition_documents: Iterable[bytes],
) -> QueueState:
    """Reduce one immutable queue item and transition stream into current state.

    Documents are parsed from bytes so every transition can be checked against the
    exact SHA-256 of the original queue document. Transition input order is not
    trusted; events are ordered deterministically by UTC timestamp and transition
    identifier. The function performs no I/O and mutates no input.
    """

    queue_item_sha256 = hashlib.sha256(queue_item_document).hexdigest()
    queue_item = _decode_document(queue_item_document, label="queue item")
    queue_item_id, initial_status = _validate_queue_document(
        queue_item, queue_item_sha256
    )

    transitions = [_parse_transition(document) for document in transition_documents]
    transitions.sort(key=lambda event: (event.applied_at_utc, event.transition_id))

    seen: dict[str, _Transition] = {}
    superseded_by: dict[str, str] = {}
    for event in transitions:
        if event.transition_id in seen:
            raise QueueStateError(f"duplicate transition id: {event.transition_id}")
        if event.queue_item_id != queue_item_id:
            raise QueueStateError("transition queue_item_id does not match queue item")
        if event.queue_item_sha256 != queue_item_sha256:
            raise QueueStateError("transition queue_item_sha256 does not match bytes")

        supersedes = event.supersedes_transition_id
        if supersedes is not None:
            if supersedes not in seen:
                raise QueueStateError(
                    "supersedes_transition_id must reference an earlier transition"
                )
            if supersedes in superseded_by:
                raise QueueStateError(
                    f"transition {supersedes} is superseded more than once"
                )
            superseded_by[supersedes] = event.transition_id
        seen[event.transition_id] = event

    effective = [
        event for event in transitions if event.transition_id not in superseded_by
    ]

    current_status = initial_status
    for event in effective:
        if current_status in _TERMINAL_STATUSES:
            raise QueueStateError(
                f"terminal status {current_status} cannot accept another transition"
            )
        if event.from_status != current_status:
            raise QueueStateError(
                f"transition {event.transition_id} expects {event.from_status} "
                f"but current status is {current_status}"
            )
        current_status = event.to_status

    effective_ids = tuple(event.transition_id for event in effective)
    superseded_ids = tuple(
        event.transition_id
        for event in transitions
        if event.transition_id in superseded_by
    )
    last_applied_at = effective[-1].applied_at if effective else None

    return QueueState(
        queue_item_id=queue_item_id,
        queue_item_sha256=queue_item_sha256,
        initial_status=initial_status,
        effective_status=current_status,
        status_source=(
            "append-only-transition-event" if effective else "queue-item"
        ),
        transition_count=len(transitions),
        effective_transition_ids=effective_ids,
        superseded_transition_ids=superseded_ids,
        last_applied_at=last_applied_at,
    )
