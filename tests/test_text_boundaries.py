from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from bible_os.text_boundaries import (
    apply_join_policy,
    apply_split_policy,
    text_sha256,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/text-boundary-policy.schema.json"
SPLIT_POLICY_PATH = (
    ROOT / "registry/versification/text-boundaries/synthetic-split.json"
)
JOIN_POLICY_PATH = (
    ROOT / "registry/versification/text-boundaries/synthetic-join.json"
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_registered_text_boundary_policies_validate():
    validator = Draft202012Validator(load(SCHEMA_PATH))
    validator.validate(load(SPLIT_POLICY_PATH))
    validator.validate(load(JOIN_POLICY_PATH))


def test_split_policy_extracts_exact_reviewed_components():
    source_text = "FirstSecond"
    components = apply_split_policy(source_text, load(SPLIT_POLICY_PATH))

    assert [component["text"] for component in components] == ["First", "Second"]
    assert [component["target_reference"] for component in components] == [
        "SYN 1:1",
        "SYN 1:2",
    ]
    assert "".join(component["text"] for component in components) == source_text
    assert [component["text_sha256"] for component in components] == [
        text_sha256("First"),
        text_sha256("Second"),
    ]


def test_split_policy_rejects_source_drift():
    with pytest.raises(ValueError, match="source text hash mismatch"):
        apply_split_policy("First-Second", load(SPLIT_POLICY_PATH))


def test_split_policy_rejects_gaps_overlap_and_partial_coverage():
    policy = deepcopy(load(SPLIT_POLICY_PATH))
    policy["components"][1]["start"] = 6
    with pytest.raises(ValueError, match="no gaps or overlap"):
        apply_split_policy("FirstSecond", policy)

    policy = deepcopy(load(SPLIT_POLICY_PATH))
    policy["components"][0]["end"] = 6
    with pytest.raises(ValueError, match="text hash mismatch"):
        apply_split_policy("FirstSecond", policy)

    policy = deepcopy(load(SPLIT_POLICY_PATH))
    policy["components"][1]["end"] = 10
    policy["components"][1]["text_sha256"] = text_sha256("Secon")
    with pytest.raises(ValueError, match="complete source text"):
        apply_split_policy("FirstSecond", policy)


def test_split_policy_rejects_component_hash_drift():
    policy = deepcopy(load(SPLIT_POLICY_PATH))
    policy["components"][1]["text_sha256"] = text_sha256("Different")
    with pytest.raises(ValueError, match="component text hash mismatch"):
        apply_split_policy("FirstSecond", policy)


def test_join_policy_reconstructs_exact_reviewed_output():
    result = apply_join_policy(
        {"SYN 2:1": "First", "SYN 2:2": "Second"},
        load(JOIN_POLICY_PATH),
    )

    assert result["source_references"] == ["SYN 2:1", "SYN 2:2"]
    assert result["target_reference"] == "SYN 2:1"
    assert result["separator"] == " "
    assert result["text"] == "First Second"
    assert result["text_sha256"] == text_sha256("First Second")


def test_join_policy_rejects_source_drift_and_unreviewed_sources():
    policy = load(JOIN_POLICY_PATH)
    with pytest.raises(ValueError, match="source text hash mismatch"):
        apply_join_policy(
            {"SYN 2:1": "First", "SYN 2:2": "Changed"},
            policy,
        )

    with pytest.raises(ValueError, match="source set does not exactly match"):
        apply_join_policy(
            {
                "SYN 2:1": "First",
                "SYN 2:2": "Second",
                "SYN 2:3": "Third",
            },
            policy,
        )


def test_join_policy_rejects_separator_and_output_drift():
    policy = deepcopy(load(JOIN_POLICY_PATH))
    policy["separator"] = ""
    with pytest.raises(ValueError, match="output text hash mismatch"):
        apply_join_policy(
            {"SYN 2:1": "First", "SYN 2:2": "Second"},
            policy,
        )


def test_schema_rejects_mixed_split_and_join_fields():
    validator = Draft202012Validator(load(SCHEMA_PATH))
    policy = deepcopy(load(SPLIT_POLICY_PATH))
    policy["sources"] = load(JOIN_POLICY_PATH)["sources"]
    assert list(validator.iter_errors(policy))


def test_policy_cannot_be_marked_publishable():
    validator = Draft202012Validator(load(SCHEMA_PATH))
    policy = deepcopy(load(SPLIT_POLICY_PATH))
    policy["publication_eligible"] = True
    assert list(validator.iter_errors(policy))
