from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/versification-review-attestation.schema.json"
QUEUE_PATH = (
    ROOT
    / "registry/versification/review-queue"
    / "asv-webp-romans-structural-candidate.json"
)
ATTESTATION_PATH = (
    ROOT
    / "registry/versification/review-attestations"
    / "asv-webp-romans-textual-needs-evidence.json"
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def errors(record: dict) -> list:
    return list(
        Draft202012Validator(
            load(SCHEMA_PATH),
            format_checker=FormatChecker(),
        ).iter_errors(record)
    )


def test_romans_textual_attestation_validates():
    assert errors(load(ATTESTATION_PATH)) == []


def test_attestation_is_anchored_to_exact_romans_queue_bytes():
    attestation = load(ATTESTATION_PATH)
    queue = load(QUEUE_PATH)

    assert attestation["queue_item_id"] == queue["queue_item_id"]
    assert attestation["queue_item_sha256"] == hashlib.sha256(
        QUEUE_PATH.read_bytes()
    ).hexdigest()


def test_attestation_cites_exactly_the_six_queue_evidence_records():
    attestation = load(ATTESTATION_PATH)
    queue = load(QUEUE_PATH)

    assert attestation["evidence_ids"] == [
        evidence["evidence_id"] for evidence in queue["evidence"]
    ]
    assert len(attestation["evidence_ids"]) == 6
    assert len(set(attestation["evidence_ids"])) == 6


def test_provisional_reviewer_identity_is_transparent_and_not_human_claimed():
    reviewer = load(ATTESTATION_PATH)["reviewer"]

    assert reviewer["role"] == "textual-scholar"
    assert reviewer["reviewer_id"] == "bible-os:ai-assisted:provisional-textual-review"
    assert "AI-assisted" in reviewer["affiliation"]
    assert "human textual-scholar validation" in reviewer["affiliation"]


def test_recommendation_requests_evidence_instead_of_approving_a_mapping():
    attestation = load(ATTESTATION_PATH)

    assert attestation["recommendation"] == "needs-evidence"
    assert attestation["recommendation"] not in {"approve", "reject"}
    assert "structure alone cannot establish" in attestation["rationale"]
    assert "source-anchored textual comparison" in attestation["rationale"]
    assert "independent scholarly evidence" in attestation["rationale"]


def test_attestation_and_queue_remain_inert():
    attestation = load(ATTESTATION_PATH)
    queue = load(QUEUE_PATH)

    assert attestation["record_policy"] == "append-only"
    assert attestation["materialization_authority"] == "none"
    assert attestation["execution_eligible"] is False
    assert attestation["publication_eligible"] is False

    assert queue["status"] == "queued"
    assert "decision" not in queue
    assert queue["materialization_state"] == "not-materialized"
    assert queue["execution_eligible"] is False
    assert queue["publication_eligible"] is False


def test_attestation_cannot_be_mutated_into_an_authoritative_record():
    original = load(ATTESTATION_PATH)
    for field, unsafe_value in [
        ("record_policy", "mutable"),
        ("materialization_authority", "approved"),
        ("execution_eligible", True),
        ("publication_eligible", True),
    ]:
        mutated = deepcopy(original)
        mutated[field] = unsafe_value
        assert errors(mutated)
