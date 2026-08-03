from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/versification-review-decision.schema.json"
QUEUE_ITEM_PATH = (
    ROOT / "registry/versification/review-queue/synthetic-split-candidate.json"
)
AGGREGATION_PATH = (
    ROOT
    / "registry/versification/review-aggregations"
    / "synthetic-split-summary.json"
)
DECISION_PATH = (
    ROOT
    / "registry/versification/review-decisions"
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


def test_review_decision_schema_is_valid():
    Draft202012Validator.check_schema(load(SCHEMA_PATH))


def test_registered_decision_validates():
    assert errors(load(DECISION_PATH)) == []


def test_decision_is_anchored_to_exact_queue_and_aggregation_bytes():
    decision = load(DECISION_PATH)
    queue_item = load(QUEUE_ITEM_PATH)
    aggregation = load(AGGREGATION_PATH)

    assert decision["queue_item_sha256"] == hashlib.sha256(
        QUEUE_ITEM_PATH.read_bytes()
    ).hexdigest()
    assert decision["aggregation_sha256"] == hashlib.sha256(
        AGGREGATION_PATH.read_bytes()
    ).hexdigest()
    assert decision["queue_item_id"] == queue_item["queue_item_id"]
    assert decision["aggregation_id"] == aggregation["aggregation_id"]


def test_insufficient_review_cannot_be_accepted_or_rejected():
    for outcome in ["accepted", "rejected"]:
        decision = deepcopy(load(DECISION_PATH))
        decision["outcome"] = outcome
        assert errors(decision)


def test_accepted_decision_requires_all_preconditions():
    decision = deepcopy(load(DECISION_PATH))
    decision["outcome"] = "accepted"
    decision["aggregation_evaluation"] = {
        "aggregation_status": "ready-for-human-decision",
        "quorum_met": True,
        "required_roles_satisfied": True,
        "conflicts_present": False,
        "decision_preconditions_satisfied": True,
    }
    decision.pop("requested_follow_up")
    assert errors(decision) == []

    decision["aggregation_evaluation"]["conflicts_present"] = True
    assert errors(decision)


def test_needs_evidence_requires_explicit_follow_up():
    decision = deepcopy(load(DECISION_PATH))
    decision.pop("requested_follow_up")
    assert errors(decision)


def test_only_human_decision_makers_are_allowed():
    decision = deepcopy(load(DECISION_PATH))
    decision["decision_makers"][0]["actor_type"] = "automation"
    assert errors(decision)


def test_decision_has_no_automatic_downstream_authority():
    decision = load(DECISION_PATH)
    assert decision["record_policy"] == "append-only"
    assert decision["decision_authority"] == "human-review-governance"
    assert decision["decision_scope"] == "review-governance-only"
    assert decision["decision_effect"] == "record-only"
    assert decision["queue_status_mutation"] == "not-applied"
    assert decision["materialization_authority"] == "none"
    assert decision["execution_eligible"] is False
    assert decision["publication_eligible"] is False

    for field, unsafe_value in [
        ("record_policy", "mutable"),
        ("decision_effect", "automatic-transition"),
        ("queue_status_mutation", "applied"),
        ("materialization_authority", "granted"),
        ("execution_eligible", True),
        ("publication_eligible", True),
    ]:
        mutated = deepcopy(decision)
        mutated[field] = unsafe_value
        assert errors(mutated)


def test_decision_record_does_not_mutate_upstream_records():
    queue_item = load(QUEUE_ITEM_PATH)
    aggregation = load(AGGREGATION_PATH)

    assert queue_item["status"] == "queued"
    assert "decision" not in queue_item
    assert aggregation["decision_authority"] == "none"
    assert aggregation["queue_status_authority"] == "none"
    assert aggregation["execution_eligible"] is False
    assert aggregation["publication_eligible"] is False


def test_correction_must_reference_a_valid_prior_decision_id():
    decision = deepcopy(load(DECISION_PATH))
    decision["supersedes_decision_id"] = "bad-id"
    assert errors(decision)

    decision["supersedes_decision_id"] = "vrd_priordecision01"
    assert errors(decision) == []
