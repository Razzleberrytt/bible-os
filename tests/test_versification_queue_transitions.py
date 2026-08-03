from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/versification-queue-transition.schema.json"
QUEUE_ITEM_PATH = (
    ROOT / "registry/versification/review-queue/synthetic-split-candidate.json"
)
DECISION_PATH = (
    ROOT
    / "registry/versification/review-decisions"
    / "synthetic-split-needs-evidence.json"
)
TRANSITION_PATH = (
    ROOT
    / "registry/versification/queue-transitions"
    / "synthetic-split-needs-evidence.json"
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def errors(record: dict) -> list:
    validator = Draft202012Validator(
        load(SCHEMA_PATH),
        format_checker=FormatChecker(),
    )
    return list(validator.iter_errors(record))


def test_queue_transition_schema_is_valid():
    Draft202012Validator.check_schema(load(SCHEMA_PATH))


def test_registered_transition_validates():
    assert errors(load(TRANSITION_PATH)) == []


def test_transition_is_anchored_to_exact_queue_and_decision_bytes():
    transition = load(TRANSITION_PATH)
    queue_item = load(QUEUE_ITEM_PATH)
    decision = load(DECISION_PATH)

    assert transition["queue_item_sha256"] == hashlib.sha256(
        QUEUE_ITEM_PATH.read_bytes()
    ).hexdigest()
    assert transition["decision_sha256"] == hashlib.sha256(
        DECISION_PATH.read_bytes()
    ).hexdigest()
    assert transition["queue_item_id"] == queue_item["queue_item_id"]
    assert transition["decision_id"] == decision["decision_id"]


def test_transition_target_matches_human_decision_outcome():
    transition = load(TRANSITION_PATH)
    decision = load(DECISION_PATH)

    assert transition["decision_outcome"] == decision["outcome"]
    assert transition["to_status"] == "needs-evidence"


def test_original_queue_document_is_not_rewritten():
    queue_item = load(QUEUE_ITEM_PATH)
    decision = load(DECISION_PATH)
    transition = load(TRANSITION_PATH)

    assert queue_item["status"] == "queued"
    assert "decision" not in queue_item
    assert decision["queue_status_mutation"] == "not-applied"
    assert transition["queue_document_mutation"] == "not-performed"
    assert transition["effective_status_source"] == "append-only-transition-event"


def test_outcome_must_map_to_exact_governance_status():
    for outcome, target in [
        ("accepted", "accepted"),
        ("rejected", "rejected"),
        ("needs-evidence", "needs-evidence"),
        ("withdrawn", "withdrawn"),
    ]:
        transition = deepcopy(load(TRANSITION_PATH))
        transition["decision_outcome"] = outcome
        transition["to_status"] = target
        assert errors(transition) == []

        transition["to_status"] = "accepted" if target != "accepted" else "rejected"
        assert errors(transition)


def test_terminal_status_cannot_be_used_as_transition_source():
    for status in ["accepted", "rejected", "withdrawn"]:
        transition = deepcopy(load(TRANSITION_PATH))
        transition["from_status"] = status
        assert errors(transition)


def test_transition_requires_a_human_governance_actor():
    transition = deepcopy(load(TRANSITION_PATH))
    transition["applied_by"][0]["actor_type"] = "automation"
    assert errors(transition)

    transition = deepcopy(load(TRANSITION_PATH))
    transition["applied_by"] = []
    assert errors(transition)


def test_transition_grants_no_downstream_authority():
    transition = load(TRANSITION_PATH)
    assert transition["application_scope"] == "queue-governance-status-only"
    assert transition["materialization_authority"] == "none"
    assert transition["mapping_execution_authority"] == "none"
    assert transition["corpus_mutation_authority"] == "none"
    assert transition["release_authority"] == "none"
    assert transition["execution_eligible"] is False
    assert transition["publication_eligible"] is False


def test_transition_cannot_claim_execution_or_publication_authority():
    unsafe_values = [
        ("queue_document_mutation", "performed"),
        ("materialization_authority", "approved"),
        ("mapping_execution_authority", "approved"),
        ("corpus_mutation_authority", "approved"),
        ("release_authority", "approved"),
        ("execution_eligible", True),
        ("publication_eligible", True),
    ]
    for field, value in unsafe_values:
        transition = deepcopy(load(TRANSITION_PATH))
        transition[field] = value
        assert errors(transition)


def test_transition_cannot_smuggle_a_mapping_plan():
    transition = deepcopy(load(TRANSITION_PATH))
    transition["mapping_plan_id"] = "map_synthetic0001"
    assert errors(transition)


def test_correction_must_reference_a_valid_prior_transition_id():
    transition = deepcopy(load(TRANSITION_PATH))
    transition["supersedes_transition_id"] = "bad-id"
    assert errors(transition)

    transition["supersedes_transition_id"] = "vqt_priortransition01"
    assert errors(transition) == []
