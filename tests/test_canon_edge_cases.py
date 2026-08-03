from copy import deepcopy
from pathlib import Path
import json

import pytest
from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "passage-mapping.schema.json"
FIXTURE_PATH = ROOT / "fixtures" / "canon" / "mapping-edge-cases.json"


def documents():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return schema, fixture


def test_mapping_schema_and_all_fixtures_are_valid():
    schema, fixture = documents()
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    for mapping in fixture["mappings"]:
        validator.validate(mapping)


def test_fixture_covers_every_relation_type_once():
    _, fixture = documents()
    relation_types = [mapping["relation_type"] for mapping in fixture["mappings"]]
    assert sorted(relation_types) == sorted(
        [
            "equivalent",
            "split",
            "join",
            "overlap",
            "omitted",
            "addition",
            "relocated",
            "uncertain",
        ]
    )
    assert len(relation_types) == len(set(relation_types)) == 8


def test_edge_cardinalities_are_explicit():
    _, fixture = documents()
    by_type = {mapping["relation_type"]: mapping for mapping in fixture["mappings"]}
    assert (len(by_type["equivalent"]["source_passage_ids"]), len(by_type["equivalent"]["target_passage_ids"])) == (1, 1)
    assert (len(by_type["split"]["source_passage_ids"]), len(by_type["split"]["target_passage_ids"])) == (1, 2)
    assert (len(by_type["join"]["source_passage_ids"]), len(by_type["join"]["target_passage_ids"])) == (2, 1)
    assert by_type["omitted"]["target_passage_ids"] == []
    assert by_type["addition"]["source_passage_ids"] == []
    assert by_type["uncertain"]["confidence"] < 0.5
    assert by_type["uncertain"]["review_state"] == "unreviewed"


def test_schema_rejects_invalid_split_cardinality():
    schema, fixture = documents()
    split = next(mapping for mapping in fixture["mappings"] if mapping["relation_type"] == "split")
    invalid = deepcopy(split)
    invalid["target_passage_ids"] = ["pas_target000002"]
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(invalid)
