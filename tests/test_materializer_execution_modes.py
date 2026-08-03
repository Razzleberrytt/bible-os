from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from bible_os.versification import (
    SYNTHETIC_EXECUTION_ENV,
    build_materialization_plan,
    load_json,
)


ROOT = Path(__file__).resolve().parents[1]
ROMANS_OBSERVATION = (
    ROOT
    / "registry"
    / "versification"
    / "observations"
    / "engwebp-bsb-romans-doxology.json"
)
ROMANS_PROFILE = (
    ROOT
    / "registry"
    / "versification"
    / "materializers"
    / "engwebp-bsb-romans-doxology.json"
)
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


def test_production_one_to_one_plan_runs_without_fixture_opt_in(monkeypatch):
    monkeypatch.delenv(SYNTHETIC_EXECUTION_ENV, raising=False)
    plan = build_materialization_plan(
        load_json(ROMANS_OBSERVATION),
        load_json(ROMANS_PROFILE),
    )
    assert len(plan) == 3


@pytest.mark.parametrize(
    ("observation_path", "profile_path"),
    [
        (SPLIT_OBSERVATION, SPLIT_PROFILE),
        (JOIN_OBSERVATION, JOIN_PROFILE),
    ],
)
def test_production_runtime_refuses_synthetic_profiles_without_opt_in(
    monkeypatch,
    observation_path: Path,
    profile_path: Path,
):
    monkeypatch.delenv(SYNTHETIC_EXECUTION_ENV, raising=False)
    with pytest.raises(ValueError, match="synthetic materializer execution is disabled"):
        build_materialization_plan(
            load_json(observation_path),
            load_json(profile_path),
        )


def test_synthetic_profiles_run_only_with_explicit_isolated_opt_in(monkeypatch):
    monkeypatch.setenv(SYNTHETIC_EXECUTION_ENV, "1")
    split_plan = build_materialization_plan(
        load_json(SPLIT_OBSERVATION),
        load_json(SPLIT_PROFILE),
    )
    join_plan = build_materialization_plan(
        load_json(JOIN_OBSERVATION),
        load_json(JOIN_PROFILE),
    )
    assert len(split_plan) == 2
    assert len(join_plan) == 2


def test_runtime_rejects_production_split_even_with_fixture_flag(monkeypatch):
    monkeypatch.setenv(SYNTHETIC_EXECUTION_ENV, "1")
    observation = load_json(SPLIT_OBSERVATION)
    profile = deepcopy(load_json(SPLIT_PROFILE))
    profile["execution_mode"] = "production-one-to-one"
    with pytest.raises(ValueError, match="production materializers support only"):
        build_materialization_plan(observation, profile)


def test_runtime_rejects_unknown_execution_mode(monkeypatch):
    monkeypatch.setenv(SYNTHETIC_EXECUTION_ENV, "1")
    observation = load_json(SPLIT_OBSERVATION)
    profile = deepcopy(load_json(SPLIT_PROFILE))
    profile["execution_mode"] = "unsafe-auto-split"
    with pytest.raises(ValueError, match="unsupported materializer execution mode"):
        build_materialization_plan(observation, profile)
