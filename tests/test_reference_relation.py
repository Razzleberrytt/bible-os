from __future__ import annotations

from copy import deepcopy

import pytest

from bible_os.versification import load_json
from scripts.reference_observation_materializer import (
    DEFAULT_OBSERVATION_PATH,
    DEFAULT_PROFILE_PATH,
)
from scripts.reference_relation_backfill import build_relations


def fixture() -> tuple[dict, dict]:
    return load_json(DEFAULT_OBSERVATION_PATH), load_json(DEFAULT_PROFILE_PATH)


def test_reference_relations_are_exact_and_deterministic():
    observation, profile = fixture()
    first = build_relations(observation, profile)
    second = build_relations(observation, profile)

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
    assert [row["reference_relation_id"] for row in first] == [
        "rrl_cmuhs633qb3nneldtms6",
        "rrl_acl66lxjvrymf6e33rjx",
        "rrl_amlujgbct366ltnkk376",
    ]


def test_pair_relation_type_must_match_observation():
    observation, profile = fixture()
    observation = deepcopy(observation)
    observation["reference_pairs"][1]["relation_type"] = "equivalent"
    with pytest.raises(ValueError, match="relation types"):
        build_relations(observation, profile)
