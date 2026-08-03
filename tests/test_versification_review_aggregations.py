from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/versification-review-aggregation.schema.json"
QUEUE_ITEM_PATH = (
    ROOT / "registry/versification/review-queue/synthetic-split-candidate.json"
)
ATTESTATION_PATH = (
    ROOT
    / "registry/versification/review-attestations"
    / "synthetic-split-data-curator.json"
)
AGGREGATION_PATH = (
    ROOT
    / "registry/versification/review-aggregations"
    / "synthetic-split-summary.json"
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def errors(record: dict) -> list:
    validator = Draft202012Validator(
        load(SCHEMA_PATH),
        format_checker=FormatChecker(),
    )
    return list(validator.iter_errors(record))


def test_review_aggregation_schema_is_valid():
    Draft202012Validator.check_schema(load(SCHEMA_PATH))


def test_registered_aggregation_validates():
    assert errors(load(AGGREGATION_PATH)) == []


def test_aggregation_is_anchored_to_exact_inputs():
    aggregation = load(AGGREGATION_PATH)
    assert aggregation["queue_item_sha256"] == hashlib.sha256(
        QUEUE_ITEM_PATH.read_bytes()
    ).hexdigest()

    source = aggregation["source_attestations"][0]
    assert source["sha256"] == hashlib.sha256(
        ATTESTATION_PATH.read_bytes()
    ).hexdigest()
    assert source["attestation_id"] == load(ATTESTATION_PATH)["attestation_id"]


def test_aggregation_recomputes_counts_from_effective_attestations():
    aggregation = load(AGGREGATION_PATH)
    sources = aggregation["source_attestations"]
    effective = [source for source in sources if source["effective"]]
    counts = Counter(source["recommendation"] for source in effective)

    assert aggregation["evaluation"]["attestation_count"] == len(sources)
    assert aggregation["evaluation"]["effective_attestation_count"] == len(effective)
    assert aggregation["evaluation"]["recommendation_counts"] == {
        "approve": counts["approve"],
        "reject": counts["reject"],
        "needs_evidence": counts["needs-evidence"],
        "abstain": counts["abstain"],
    }


def test_missing_roles_and_quorum_match_policy_snapshot():
    aggregation = load(AGGREGATION_PATH)
    policy = aggregation["policy_snapshot"]
    effective = [
        source for source in aggregation["source_attestations"] if source["effective"]
    ]
    represented = sorted({source["role"] for source in effective})
    missing = sorted(set(policy["required_roles"]) - set(represented))
    approvals = sum(source["recommendation"] == "approve" for source in effective)

    assert sorted(aggregation["evaluation"]["represented_roles"]) == represented
    assert sorted(aggregation["evaluation"]["missing_roles"]) == missing
    assert aggregation["evaluation"]["quorum_met"] is (
        approvals >= policy["minimum_approvals"] and not missing
    )
    assert aggregation["evaluation"]["aggregation_status"] == "insufficient-reviews"


def test_aggregation_has_no_decision_or_execution_authority():
    aggregation = load(AGGREGATION_PATH)
    assert "decision" not in aggregation
    assert aggregation["record_policy"] == "derived-snapshot"
    assert aggregation["decision_authority"] == "none"
    assert aggregation["queue_status_authority"] == "none"
    assert aggregation["materialization_authority"] == "none"
    assert aggregation["execution_eligible"] is False
    assert aggregation["publication_eligible"] is False


def test_ready_status_requires_quorum_no_conflicts_and_no_missing_roles():
    aggregation = deepcopy(load(AGGREGATION_PATH))
    aggregation["evaluation"]["aggregation_status"] = "ready-for-human-decision"
    assert errors(aggregation)

    aggregation["evaluation"]["quorum_met"] = True
    aggregation["evaluation"]["missing_roles"] = []
    aggregation["evaluation"]["conflicts_present"] = False
    assert errors(aggregation) == []


def test_conflicted_status_requires_a_recorded_conflict():
    aggregation = deepcopy(load(AGGREGATION_PATH))
    aggregation["evaluation"]["aggregation_status"] = "conflicted"
    assert errors(aggregation)

    aggregation["evaluation"]["conflicts_present"] = True
    assert errors(aggregation) == []


def test_insufficient_status_requires_missing_roles_or_failed_quorum():
    aggregation = deepcopy(load(AGGREGATION_PATH))
    aggregation["evaluation"]["quorum_met"] = True
    aggregation["evaluation"]["missing_roles"] = []
    assert errors(aggregation)


def test_aggregation_cannot_claim_authority_or_embed_a_decision():
    for field, unsafe_value in [
        ("decision_authority", "final"),
        ("queue_status_authority", "update"),
        ("materialization_authority", "approved"),
        ("execution_eligible", True),
        ("publication_eligible", True),
    ]:
        aggregation = deepcopy(load(AGGREGATION_PATH))
        aggregation[field] = unsafe_value
        assert errors(aggregation)

    aggregation = deepcopy(load(AGGREGATION_PATH))
    aggregation["decision"] = {"outcome": "accepted"}
    assert errors(aggregation)
