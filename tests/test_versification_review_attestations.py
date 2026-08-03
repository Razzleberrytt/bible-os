from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/versification-review-attestation.schema.json"
QUEUE_ITEM_PATH = (
    ROOT / "registry/versification/review-queue/synthetic-split-candidate.json"
)
ATTESTATION_PATH = (
    ROOT
    / "registry/versification/review-attestations"
    / "synthetic-split-data-curator.json"
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def errors(record: dict) -> list:
    validator = Draft202012Validator(
        load(SCHEMA_PATH),
        format_checker=FormatChecker(),
    )
    return list(validator.iter_errors(record))


def test_review_attestation_schema_is_valid():
    Draft202012Validator.check_schema(load(SCHEMA_PATH))


def test_registered_attestation_validates():
    assert errors(load(ATTESTATION_PATH)) == []


def test_attestation_is_anchored_to_exact_queue_item_bytes():
    attestation = load(ATTESTATION_PATH)
    observed = hashlib.sha256(QUEUE_ITEM_PATH.read_bytes()).hexdigest()
    assert attestation["queue_item_sha256"] == observed
    assert attestation["queue_item_id"] == load(QUEUE_ITEM_PATH)["queue_item_id"]


def test_attestation_has_no_materialization_or_publication_authority():
    attestation = load(ATTESTATION_PATH)
    assert attestation["record_policy"] == "append-only"
    assert attestation["materialization_authority"] == "none"
    assert attestation["execution_eligible"] is False
    assert attestation["publication_eligible"] is False


def test_review_does_not_mutate_the_queued_candidate():
    queue_item = load(QUEUE_ITEM_PATH)
    assert queue_item["status"] == "queued"
    assert "decision" not in queue_item
    assert queue_item["materialization_state"] == "not-materialized"
    assert queue_item["execution_eligible"] is False
    assert queue_item["publication_eligible"] is False


def test_conflict_disclosure_requires_matching_details():
    attestation = deepcopy(load(ATTESTATION_PATH))
    attestation["conflict_disclosure"] = {
        "status": "disclosed",
        "details": null,
    }
    assert errors(attestation)

    attestation = deepcopy(load(ATTESTATION_PATH))
    attestation["conflict_disclosure"] = {
        "status": "none",
        "details": "Unexpected text",
    }
    assert errors(attestation)


def test_evidence_and_reviewer_role_are_required():
    attestation = deepcopy(load(ATTESTATION_PATH))
    attestation["evidence_ids"] = []
    assert errors(attestation)

    attestation = deepcopy(load(ATTESTATION_PATH))
    attestation["reviewer"]["role"] = "automatic-approver"
    assert errors(attestation)


def test_attestation_cannot_claim_mutable_or_executable_status():
    for field, unsafe_value in [
        ("record_policy", "mutable"),
        ("materialization_authority", "approved"),
        ("execution_eligible", True),
        ("publication_eligible", True),
    ]:
        attestation = deepcopy(load(ATTESTATION_PATH))
        attestation[field] = unsafe_value
        assert errors(attestation)


def test_correction_must_reference_a_valid_prior_attestation_id():
    attestation = deepcopy(load(ATTESTATION_PATH))
    attestation["supersedes_attestation_id"] = "bad-id"
    assert errors(attestation)

    attestation["supersedes_attestation_id"] = "vra_priorreview01"
    assert errors(attestation) == []
