from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/versification-review-queue-item.schema.json"
FIXTURE_PATH = (
    ROOT
    / "registry"
    / "versification"
    / "review-queue"
    / "synthetic-split-candidate.json"
)


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


def test_review_queue_schema_and_fixture_validate():
    schema = load(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(load(FIXTURE_PATH))


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
