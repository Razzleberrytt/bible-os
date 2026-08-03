from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "reference-materializer.schema.json"
PROFILE_PATH = (
    ROOT
    / "registry"
    / "versification"
    / "materializers"
    / "engwebp-bsb-romans-doxology.json"
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_materializer_profile_validates():
    Draft202012Validator(load(SCHEMA_PATH)).validate(load(PROFILE_PATH))


def test_materializer_profile_is_explicitly_non_publishable():
    profile = load(PROFILE_PATH)
    assert profile["publication_eligible"] is False
    assert profile["mapping_shape"] == "one-to-one-ordered"
    assert profile["observation_id"] == "obs_romdoxology2026"
    assert profile["source_system"]["versification_system_id"] == "vrs_dfqdldqfzy7udzlxspyw"
    assert profile["target_system"]["versification_system_id"] == "vrs_tbgrhqbyag3ymkpq2lf4"


def test_publishable_materializer_profile_is_rejected():
    schema = load(SCHEMA_PATH)
    profile = deepcopy(load(PROFILE_PATH))
    profile["publication_eligible"] = True
    errors = list(Draft202012Validator(schema).iter_errors(profile))
    assert errors


def test_target_system_metadata_is_required():
    schema = load(SCHEMA_PATH)
    profile = deepcopy(load(PROFILE_PATH))
    del profile["target_system"]["authority"]
    errors = list(Draft202012Validator(schema).iter_errors(profile))
    assert errors
