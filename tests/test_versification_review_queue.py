from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/versification-review-queue-item.schema.json"
SYNTHETIC_FIXTURE_PATH = (
    ROOT
    / "registry"
    / "versification"
    / "review-queue"
    / "synthetic-split-candidate.json"
)
ROMANS_FIXTURE_PATH = (
    ROOT
    / "registry"
    / "versification"
    / "review-queue"
    / "asv-webp-romans-structural-candidate.json"
)
CANDIDATE_PROFILE_PATH = (
    ROOT / "registry/experiments/asv-webp-locator-candidates.json"
)
FIXTURE_PATH = SYNTHETIC_FIXTURE_PATH


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def errors(item: dict) -> list:
    schema = load(SCHEMA_PATH)
    return list(
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(item)
    )


def test_review_queue_schema_and_fixtures_validate():
    schema = load(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    validator.validate(load(SYNTHETIC_FIXTURE_PATH))
    validator.validate(load(ROMANS_FIXTURE_PATH))


def test_romans_proposal_is_exactly_scoped_to_six_pinned_observations():
    item = load(ROMANS_FIXTURE_PATH)
    profile = load(CANDIDATE_PROFILE_PATH)
    profile_candidates = {
        candidate["candidate_id"]: candidate
        for candidate in profile["exceptional_candidates"]
    }
    evidence_ids = [
        evidence["locator"].rsplit("#", 1)[1]
        for evidence in item["evidence"]
    ]

    assert item["queue_item_id"] == "vrq_asvwebpromans01"
    assert item["candidate_kind"] == "uncertain"
    assert item["status"] == "queued"
    assert item["proposed_confidence"] == 0.0
    assert item["source_system"] == {
        "versification_system_id": "vrs_pmkqrxv7lvez52xxkan2",
        "references": ["ROM 16:25", "ROM 16:26", "ROM 16:27"],
    }
    assert item["target_system"] == {
        "versification_system_id": "vrs_dfqdldqfzy7udzlxspyw",
        "references": [
            "ROM 14:24",
            "ROM 14:25",
            "ROM 14:26",
            "ROM 16:25",
        ],
    }
    assert evidence_ids == [
        "can_py26v3umswbmzskskpp5",
        "can_wj6w6pd7c37roqplxvrh",
        "can_3sgamesf53renovukq6w",
        "can_hdyty2uvb3s3kuylkc57",
        "can_lyiw5ovpe7ir3acvsd6m",
        "can_qy4pdugmdaq26f52akxm",
    ]
    assert [profile_candidates[candidate_id]["locator"] for candidate_id in evidence_ids] == [
        "ROM 14:24",
        "ROM 14:25",
        "ROM 14:26",
        "ROM 16:25",
        "ROM 16:26",
        "ROM 16:27",
    ]
    assert [
        profile_candidates[candidate_id]["candidate_class"]
        for candidate_id in evidence_ids
    ] == [
        "webp-only-locus",
        "webp-only-locus",
        "webp-only-locus",
        "realization-mismatch-observation",
        "asv-only-locus",
        "asv-only-locus",
    ]
    assert "can_k6cfuv7sbumommdi2ha7" not in evidence_ids
    assert all(evidence["sha256"] == profile["sha256"] for evidence in item["evidence"])
    assert all(evidence["contains_source_text"] is False for evidence in item["evidence"])
    assert item["review_requirements"] == {
        "required_roles": [
            "textual-scholar",
            "data-curator",
            "engineering-reviewer",
        ],
        "minimum_approvals": 3,
        "conflict_policy": "unanimous",
    }
    assert item["materialization_state"] == "not-materialized"
    assert item["execution_eligible"] is False
    assert item["publication_eligible"] is False


def test_queue_item_is_inert_by_contract():
    item = deepcopy(load(FIXTURE_PATH))
    item["execution_eligible"] = True
    assert errors(item)

    item = deepcopy(load(FIXTURE_PATH))
    item["publication_eligible"] = True
    assert errors(item)

    item = deepcopy(load(FIXTURE_PATH))
    item["materialization_state"] = "materialized"
    assert errors(item)


def test_queue_item_requires_evidence_without_source_text():
    item = deepcopy(load(FIXTURE_PATH))
    item["evidence"] = []
    assert errors(item)

    item = deepcopy(load(FIXTURE_PATH))
    item["evidence"][0]["contains_source_text"] = True
    assert errors(item)

    item = deepcopy(load(FIXTURE_PATH))
    item["evidence"][0]["source_text"] = "not allowed"
    assert errors(item)


def test_split_and_join_cardinalities_are_enforced():
    split_item = deepcopy(load(FIXTURE_PATH))
    split_item["source_system"]["references"].append("SYN 3:2")
    assert errors(split_item)

    split_item = deepcopy(load(FIXTURE_PATH))
    split_item["target_system"]["references"] = ["SYN 3:1"]
    assert errors(split_item)

    join_item = deepcopy(load(FIXTURE_PATH))
    join_item["candidate_kind"] = "join"
    join_item["source_system"]["references"] = ["SYN 4:1", "SYN 4:2"]
    join_item["target_system"]["references"] = ["SYN 4:1"]
    assert not errors(join_item)

    join_item["target_system"]["references"].append("SYN 4:2")
    assert errors(join_item)


def test_omission_and_addition_allow_an_empty_side_only():
    omitted = deepcopy(load(FIXTURE_PATH))
    omitted["candidate_kind"] = "omitted"
    omitted["target_system"]["references"] = []
    assert not errors(omitted)

    addition = deepcopy(load(FIXTURE_PATH))
    addition["candidate_kind"] = "addition"
    addition["source_system"]["references"] = []
    addition["target_system"]["references"] = ["SYN 5:1"]
    assert not errors(addition)


def test_queued_items_cannot_contain_a_decision():
    item = deepcopy(load(FIXTURE_PATH))
    item["decision"] = {
        "outcome": "accepted",
        "decided_at": "2026-08-03T22:30:00Z",
        "decided_by": ["reviewer-1"],
        "rationale": "Synthetic approval attempt.",
    }
    assert errors(item)


def test_terminal_or_evidence_status_requires_matching_decision():
    for status in ["accepted", "rejected", "needs-evidence", "withdrawn"]:
        item = deepcopy(load(FIXTURE_PATH))
        item["status"] = status
        assert errors(item)

        item["decision"] = {
            "outcome": status,
            "decided_at": "2026-08-03T22:30:00Z",
            "decided_by": ["reviewer-1"],
            "rationale": "Synthetic decision fixture.",
        }
        assert not errors(item)

        item["decision"]["outcome"] = (
            "rejected" if status != "rejected" else "accepted"
        )
        assert errors(item)
