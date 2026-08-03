from __future__ import annotations

from copy import deepcopy

import pytest

from bible_os.versification import build_materialization_plan, load_json, parse_reference
from scripts.reference_observation_materializer import (
    DEFAULT_OBSERVATION_PATH,
    DEFAULT_PROFILE_PATH,
)


def fixture() -> tuple[dict, dict]:
    return load_json(DEFAULT_OBSERVATION_PATH), load_json(DEFAULT_PROFILE_PATH)


def test_reference_parser_accepts_canonical_loci():
    assert parse_reference("ROM 14:24") == ("ROM", 14, 24)
    assert parse_reference("ROM 16:27") == ("ROM", 16, 27)


@pytest.mark.parametrize("reference", ["", "ROM", "ROM x:1", "ROM 1:x", "ROM 0:1"])
def test_reference_parser_rejects_invalid_loci(reference: str):
    with pytest.raises(ValueError, match="invalid reference"):
        parse_reference(reference)


def test_mapping_plan_is_exact_and_preserves_existing_ids():
    observation, profile = fixture()
    first = build_materialization_plan(observation, profile)
    second = build_materialization_plan(observation, profile)

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
    assert [row["passage_id"] for row in first] == [
        "pas_ynrxvaiblnak7gkderct",
        "pas_vc3xe5g2mtpoj3tvpwi3",
        "pas_5rqizejwneqcpkcmk7ol",
    ]
    assert [row["reference_relation_id"] for row in first] == [
        "rrl_cmuhs633qb3nneldtms6",
        "rrl_acl66lxjvrymf6e33rjx",
        "rrl_amlujgbct366ltnkk376",
    ]
    assert len({row["source_mapping_id"] for row in first}) == 3
    assert len({row["target_mapping_id"] for row in first}) == 3


def test_materialization_requires_profile_review_state():
    observation, profile = fixture()
    observation = deepcopy(observation)
    observation["status"] = "machine-observed"
    with pytest.raises(ValueError, match="review state"):
        build_materialization_plan(observation, profile)


def test_explicit_pairs_must_match_ordered_reference_arrays():
    observation, profile = fixture()
    observation = deepcopy(observation)
    observation["reference_pairs"][0]["target_reference"] = "ROM 16:27"
    with pytest.raises(ValueError, match="explicit reference pairs"):
        build_materialization_plan(observation, profile)


def test_profile_restricts_books():
    observation, profile = fixture()
    profile = deepcopy(profile)
    profile["allowed_book_codes"] = ["GEN"]
    with pytest.raises(ValueError, match="source book"):
        build_materialization_plan(observation, profile)


def test_profile_system_keys_must_match_observation():
    observation, profile = fixture()
    profile = deepcopy(profile)
    profile["target_system"]["system_key"] = "different-system"
    with pytest.raises(ValueError, match="target system"):
        build_materialization_plan(observation, profile)
