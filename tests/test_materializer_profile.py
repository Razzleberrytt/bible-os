from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "reference-materializer.schema.json"
PROFILE_PATHS = (
    ROOT / "registry/versification/materializers/engwebp-bsb-romans-doxology.json",
    ROOT / "registry/versification/materializers/synthetic-split.json",
    ROOT / "registry/versification/materializers/synthetic-join.json",
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_all_materializer_profiles_validate():
    validator = Draft202012Validator(load(SCHEMA_PATH))
    for profile_path in PROFILE_PATHS:
        validator.validate(load(profile_path))


def test_materializer_profiles_are_explicitly_non_publishable():
    profiles = [load(path) for path in PROFILE_PATHS]
    assert all(profile["publication_eligible"] is False for profile in profiles)
    assert {profile["mapping_shape"] for profile in profiles} == {
        "one-to-one-ordered",
        "one-to-many-split",
        "many-to-one-join",
    }


def test_romans_profile_identity_contract_is_unchanged():
    profile = load(PROFILE_PATHS[0])
    assert profile["observation_id"] == "obs_romdoxology2026"
    assert profile["source_system"]["versification_system_id"] == "vrs_dfqdldqfzy7udzlxspyw"
    assert profile["target_system"]["versification_system_id"] == "vrs_tbgrhqbyag3ymkpq2lf4"


def test_publishable_materializer_profile_is_rejected():
    schema = load(SCHEMA_PATH)
    profile = deepcopy(load(PROFILE_PATHS[1]))
    profile["publication_eligible"] = True
    errors = list(Draft202012Validator(schema).iter_errors(profile))
    assert errors


def test_target_system_metadata_is_required():
    schema = load(SCHEMA_PATH)
    profile = deepcopy(load(PROFILE_PATHS[2]))
    del profile["target_system"]["authority"]
    errors = list(Draft202012Validator(schema).iter_errors(profile))
    assert errors


def test_unknown_mapping_shape_is_rejected():
    schema = load(SCHEMA_PATH)
    profile = deepcopy(load(PROFILE_PATHS[1]))
    profile["mapping_shape"] = "many-to-many-magic"
    errors = list(Draft202012Validator(schema).iter_errors(profile))
    assert errors
