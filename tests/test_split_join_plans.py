from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from bible_os.versification import (
    SYNTHETIC_EXECUTION_ENV,
    build_group_alignment_plan,
    build_materialization_plan,
    load_json,
)


ROOT = Path(__file__).resolve().parents[1]
SPLIT_OBSERVATION = (
    ROOT / "registry/versification/observations/synthetic-split.json"
)
SPLIT_PROFILE = (
    ROOT / "registry/versification/materializers/synthetic-split.json"
)
JOIN_OBSERVATION = (
    ROOT / "registry/versification/observations/synthetic-join.json"
)
JOIN_PROFILE = (
    ROOT / "registry/versification/materializers/synthetic-join.json"
)


@pytest.fixture(autouse=True)
def enable_isolated_synthetic_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SYNTHETIC_EXECUTION_ENV, "1")


def build(observation_path: Path, profile_path: Path):
    observation = load_json(observation_path)
    profile = load_json(profile_path)
    plan = build_materialization_plan(observation, profile)
    alignment = build_group_alignment_plan(observation, profile, plan)
    return observation, profile, plan, alignment


def test_split_plan_is_deterministic_and_pinned():
    _, profile, first, alignment = build(SPLIT_OBSERVATION, SPLIT_PROFILE)
    _, _, second, second_alignment = build(SPLIT_OBSERVATION, SPLIT_PROFILE)

    assert first == second
    assert alignment == second_alignment
    assert profile["mapping_shape"] == "one-to-many-split"
    assert profile["execution_mode"] == "synthetic-fixture"
    assert [row["source_reference"] for row in first] == ["SYN 1:1", "SYN 1:1"]
    assert [row["target_reference"] for row in first] == ["SYN 1:1", "SYN 1:2"]
    assert {row["source_mapping_relation"] for row in first} == {"split"}
    assert {row["target_mapping_relation"] for row in first} == {"equivalent"}
    assert [row["passage_id"] for row in first] == [
        "pas_ejeg6zz32bzk3uqgyakz",
        "pas_xg5nvsfuzqh3aslakgfm",
    ]
    assert len({row["source_reference_id"] for row in first}) == 1
    assert len({row["target_reference_id"] for row in first}) == 2
    assert alignment["alignment_id"] == "aln_x4eniknij3uehhywq6ot"
    assert alignment["provenance"]["execution_mode"] == "synthetic-fixture"
    assert len(alignment["source_ids"]) == 1
    assert len(alignment["target_ids"]) == 2


def test_join_plan_is_deterministic_and_pinned():
    _, profile, first, alignment = build(JOIN_OBSERVATION, JOIN_PROFILE)
    _, _, second, second_alignment = build(JOIN_OBSERVATION, JOIN_PROFILE)

    assert first == second
    assert alignment == second_alignment
    assert profile["mapping_shape"] == "many-to-one-join"
    assert profile["execution_mode"] == "synthetic-fixture"
    assert [row["source_reference"] for row in first] == ["SYN 2:1", "SYN 2:2"]
    assert [row["target_reference"] for row in first] == ["SYN 2:1", "SYN 2:1"]
    assert {row["source_mapping_relation"] for row in first} == {"equivalent"}
    assert {row["target_mapping_relation"] for row in first} == {"join"}
    assert [row["passage_id"] for row in first] == [
        "pas_p2kvrvmca5gslf76xre4",
        "pas_7kxoa6ywndd2y7ps6zxd",
    ]
    assert len({row["source_reference_id"] for row in first}) == 2
    assert len({row["target_reference_id"] for row in first}) == 1
    assert alignment["alignment_id"] == "aln_yjhe42qcvvi4fq7wqcqo"
    assert alignment["provenance"]["execution_mode"] == "synthetic-fixture"
    assert len(alignment["source_ids"]) == 2
    assert len(alignment["target_ids"]) == 1


def test_split_shape_rejects_more_than_one_source_reference():
    observation = deepcopy(load_json(SPLIT_OBSERVATION))
    profile = load_json(SPLIT_PROFILE)
    observation["source_references"].append("SYN 1:2")
    with pytest.raises(ValueError, match="one source reference"):
        build_materialization_plan(observation, profile)


def test_join_shape_rejects_more_than_one_target_reference():
    observation = deepcopy(load_json(JOIN_OBSERVATION))
    profile = load_json(JOIN_PROFILE)
    observation["target_references"].append("SYN 2:2")
    with pytest.raises(ValueError, match="one target"):
        build_materialization_plan(observation, profile)


def test_split_and_join_relation_types_are_shape_locked():
    split_observation = deepcopy(load_json(SPLIT_OBSERVATION))
    split_profile = load_json(SPLIT_PROFILE)
    split_observation["relation_type"] = "join"
    for pair in split_observation["reference_pairs"]:
        pair["relation_type"] = "join"
    with pytest.raises(ValueError, match="relation_type 'split'"):
        build_materialization_plan(split_observation, split_profile)

    join_observation = deepcopy(load_json(JOIN_OBSERVATION))
    join_profile = load_json(JOIN_PROFILE)
    join_observation["relation_type"] = "split"
    for pair in join_observation["reference_pairs"]:
        pair["relation_type"] = "split"
    with pytest.raises(ValueError, match="relation_type 'join'"):
        build_materialization_plan(join_observation, join_profile)
