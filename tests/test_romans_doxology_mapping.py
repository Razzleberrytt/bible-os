from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.romans_doxology_mapping import (
    BSB_VERSIFICATION_ID,
    build_plan,
    load_json,
    OBSERVATION_PATH,
    parse_reference,
)


def test_reference_parser_accepts_canonical_loci():
    assert parse_reference("ROM 14:24") == ("ROM", 14, 24)
    assert parse_reference("ROM 16:27") == ("ROM", 16, 27)


@pytest.mark.parametrize("reference", ["", "ROM", "ROM x:1", "ROM 1:x", "ROM 0:1"])
def test_reference_parser_rejects_invalid_loci(reference: str):
    with pytest.raises(ValueError, match="invalid reference"):
        parse_reference(reference)


def test_mapping_plan_is_exact_and_deterministic():
    observation = load_json(OBSERVATION_PATH)
    first = build_plan(observation)
    second = build_plan(observation)

    assert first == second
    assert BSB_VERSIFICATION_ID.startswith("vrs_")
    assert [row["source_reference"] for row in first] == [
        "ROM 14:24",
        "ROM 14:25",
        "ROM 14:26",
    ]
    assert [row["target_reference"] for row in first] == [
        "ROM 16:25",
        "ROM 16:26",
        "ROM 16:27",
    ]
    assert len({row["passage_id"] for row in first}) == 3
    assert len({row["source_mapping_id"] for row in first}) == 3
    assert len({row["target_mapping_id"] for row in first}) == 3


def test_materialization_requires_evidence_review():
    observation = load_json(OBSERVATION_PATH)
    observation = deepcopy(observation)
    observation["status"] = "machine-observed"
    with pytest.raises(ValueError, match="evidence-reviewed"):
        build_plan(observation)


def test_explicit_pairs_must_match_ordered_reference_arrays():
    observation = load_json(OBSERVATION_PATH)
    observation = deepcopy(observation)
    observation["reference_pairs"][0]["target_reference"] = "ROM 16:27"
    with pytest.raises(ValueError, match="explicit reference pairs"):
        build_plan(observation)
