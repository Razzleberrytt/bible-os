from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from bible_os.governance import QueueStateError, reduce_queue_state


ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = (
    ROOT / "registry/versification/review-queue/synthetic-split-candidate.json"
)
TRANSITION_PATH = (
    ROOT
    / "registry/versification/queue-transitions"
    / "synthetic-split-needs-evidence.json"
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def encode(record: dict) -> bytes:
    return (json.dumps(record, indent=2) + "\n").encode("utf-8")


def transition(**changes: object) -> bytes:
    record = deepcopy(load(TRANSITION_PATH))
    record.update(changes)
    return encode(record)


def test_registered_transition_reduces_to_needs_evidence():
    state = reduce_queue_state(
        QUEUE_PATH.read_bytes(),
        [TRANSITION_PATH.read_bytes()],
    )

    assert state.queue_item_id == "vrq_synthsplit01"
    assert state.initial_status == "queued"
    assert state.effective_status == "needs-evidence"
    assert state.status_source == "append-only-transition-event"
    assert state.transition_count == 1
    assert state.effective_transition_ids == ("vqt_synthtransition01",)
    assert state.superseded_transition_ids == ()
    assert state.last_applied_at == "2026-08-03T22:51:00Z"


def test_no_transition_preserves_immutable_queue_status():
    state = reduce_queue_state(QUEUE_PATH.read_bytes(), [])

    assert state.initial_status == "queued"
    assert state.effective_status == "queued"
    assert state.status_source == "queue-item"
    assert state.transition_count == 0
    assert state.effective_transition_ids == ()
    assert state.last_applied_at is None


def test_input_order_does_not_change_the_result():
    first = transition(
        transition_id="vqt_orderedfirst01",
        decision_id="vrd_orderedfirst01",
        from_status="queued",
        to_status="needs-evidence",
        decision_outcome="needs-evidence",
        applied_at="2026-08-03T22:51:00Z",
        supersedes_transition_id=None,
    )
    second = transition(
        transition_id="vqt_orderedsecond01",
        decision_id="vrd_orderedsecond01",
        from_status="needs-evidence",
        to_status="withdrawn",
        decision_outcome="withdrawn",
        applied_at="2026-08-03T22:52:00Z",
        supersedes_transition_id=None,
    )

    forward = reduce_queue_state(QUEUE_PATH.read_bytes(), [first, second])
    reverse = reduce_queue_state(QUEUE_PATH.read_bytes(), [second, first])

    assert forward == reverse
    assert forward.effective_status == "withdrawn"
    assert forward.effective_transition_ids == (
        "vqt_orderedfirst01",
        "vqt_orderedsecond01",
    )


def test_exact_queue_bytes_are_hash_anchored():
    changed_bytes = QUEUE_PATH.read_bytes() + b" "

    with pytest.raises(QueueStateError, match="sha256"):
        reduce_queue_state(changed_bytes, [TRANSITION_PATH.read_bytes()])


def test_transition_must_target_the_same_queue_item():
    wrong_queue = transition(queue_item_id="vrq_anotherqueue01")

    with pytest.raises(QueueStateError, match="queue_item_id"):
        reduce_queue_state(QUEUE_PATH.read_bytes(), [wrong_queue])


def test_broken_status_chain_fails_closed():
    broken = transition(from_status="in-review")

    with pytest.raises(QueueStateError, match="current status"):
        reduce_queue_state(QUEUE_PATH.read_bytes(), [broken])


def test_decision_outcome_must_match_target_status():
    broken = transition(decision_outcome="accepted")

    with pytest.raises(QueueStateError, match="decision_outcome"):
        reduce_queue_state(QUEUE_PATH.read_bytes(), [broken])


def test_duplicate_transition_ids_are_rejected():
    document = TRANSITION_PATH.read_bytes()

    with pytest.raises(QueueStateError, match="duplicate transition id"):
        reduce_queue_state(QUEUE_PATH.read_bytes(), [document, document])


def test_unsafe_authority_claims_are_rejected():
    unsafe = transition(mapping_execution_authority="approved")

    with pytest.raises(QueueStateError, match="mapping_execution_authority"):
        reduce_queue_state(QUEUE_PATH.read_bytes(), [unsafe])

    nonhuman = load(TRANSITION_PATH)
    nonhuman["applied_by"][0]["actor_type"] = "automated-agent"
    with pytest.raises(QueueStateError, match="must be human"):
        reduce_queue_state(QUEUE_PATH.read_bytes(), [encode(nonhuman)])


def test_terminal_status_cannot_accept_another_effective_transition():
    accepted = transition(
        transition_id="vqt_terminalfirst01",
        decision_id="vrd_terminalfirst01",
        from_status="queued",
        to_status="accepted",
        decision_outcome="accepted",
        applied_at="2026-08-03T22:51:00Z",
    )
    later = transition(
        transition_id="vqt_terminalsecond01",
        decision_id="vrd_terminalsecond01",
        from_status="needs-evidence",
        to_status="withdrawn",
        decision_outcome="withdrawn",
        applied_at="2026-08-03T22:52:00Z",
    )

    with pytest.raises(QueueStateError, match="terminal status accepted"):
        reduce_queue_state(QUEUE_PATH.read_bytes(), [accepted, later])


def test_later_correction_can_supersede_one_prior_transition():
    original = TRANSITION_PATH.read_bytes()
    correction = transition(
        transition_id="vqt_synthtransition02",
        decision_id="vrd_synthdecision02",
        from_status="queued",
        to_status="withdrawn",
        decision_outcome="withdrawn",
        applied_at="2026-08-03T22:52:00Z",
        supersedes_transition_id="vqt_synthtransition01",
    )

    state = reduce_queue_state(QUEUE_PATH.read_bytes(), [correction, original])

    assert state.effective_status == "withdrawn"
    assert state.transition_count == 2
    assert state.effective_transition_ids == ("vqt_synthtransition02",)
    assert state.superseded_transition_ids == ("vqt_synthtransition01",)


def test_supersession_must_reference_an_earlier_unique_event():
    unknown = transition(
        transition_id="vqt_synthtransition02",
        supersedes_transition_id="vqt_missingevent01",
        applied_at="2026-08-03T22:52:00Z",
    )
    with pytest.raises(QueueStateError, match="earlier transition"):
        reduce_queue_state(QUEUE_PATH.read_bytes(), [unknown])

    first = TRANSITION_PATH.read_bytes()
    second = transition(
        transition_id="vqt_synthtransition02",
        decision_id="vrd_synthdecision02",
        supersedes_transition_id="vqt_synthtransition01",
        applied_at="2026-08-03T22:52:00Z",
    )
    third = transition(
        transition_id="vqt_synthtransition03",
        decision_id="vrd_synthdecision03",
        supersedes_transition_id="vqt_synthtransition01",
        applied_at="2026-08-03T22:53:00Z",
    )
    with pytest.raises(QueueStateError, match="superseded more than once"):
        reduce_queue_state(QUEUE_PATH.read_bytes(), [first, second, third])


def test_timestamps_must_be_timezone_aware():
    naive = transition(applied_at="2026-08-03T22:51:00")

    with pytest.raises(QueueStateError, match="include a timezone"):
        reduce_queue_state(QUEUE_PATH.read_bytes(), [naive])
