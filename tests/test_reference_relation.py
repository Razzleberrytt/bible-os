from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.reference_relation_backfill import build_relations
from scripts.romans_doxology_mapping import OBSERVATION_PATH, load_json


def test_reference_relations_are_exact_and_deterministic():
    observation = load_json(OBSERVATION_PATH)
    first = build_relations(observation)
    second = build_relations(observation)

    assert first == second
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
    assert {row["relation_type"] for row in first} == {"relocated"}
    assert {row["confidence"] for row in first} == {1.0}
    assert len({row["reference_relation_id"] for row in first}) == 3
    assert all(row["reference_relation_id"].startswith("rrl_") for row in first)


def test_pair_relation_type_must_match_observation():
    observation = deepcopy(load_json(OBSERVATION_PATH))
    observation["reference_pairs"][1]["relation_type"] = "equivalent"
    with pytest.raises(ValueError, match="relation types"):
        build_relations(observation)
