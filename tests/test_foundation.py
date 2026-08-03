from pathlib import Path
import json
import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_foundation_schema_is_valid():
    schema = load_json(ROOT / "schemas/foundation.schema.json")
    Draft202012Validator.check_schema(schema)


def test_synthetic_fixture_contracts():
    schema = load_json(ROOT / "schemas/foundation.schema.json")
    fixture = load_json(ROOT / "examples/synthetic-fixture.json")
    mapping = {
        "source": "source",
        "acquisition": "acquisition_event",
        "artifact": "artifact_manifest",
        "release": "release_manifest",
    }
    for fixture_key, definition_key in mapping.items():
        Draft202012Validator(
            schema["$defs"][definition_key],
            format_checker=FormatChecker(),
        ).validate(fixture[fixture_key])


def test_fixture_cannot_be_mistaken_for_publishable_evidence():
    fixture = load_json(ROOT / "examples/synthetic-fixture.json")
    assert fixture["source"]["license_status"] == "rejected"
    assert fixture["artifact"]["verification_status"] == "rejected"
    assert fixture["release"]["status"] == "provisional"
    assert fixture["release"]["quality"]["critical_failures"] > 0


def test_provenance_envelope():
    statement = load_json(ROOT / "examples/synthetic-fixture.json")["provenance"]
    assert statement["_type"] == "https://in-toto.io/Statement/v1"
    assert statement["predicateType"] == "https://slsa.dev/provenance/v1"
    assert statement["subject"][0]["digest"]["sha256"]


def test_openapi_contract():
    spec = yaml.safe_load((ROOT / "openapi/openapi.yaml").read_text(encoding="utf-8"))
    assert spec["openapi"] == "3.2.0"
    assert {"/releases", "/passages/{passageId}", "/comparisons"} <= set(spec["paths"])


def test_migration_has_integrity_controls():
    sql = (ROOT / "database/migrations/0001_foundation.up.sql").read_text(encoding="utf-8")
    for required in [
        "CREATE TABLE source_artifact",
        "CREATE TABLE passage",
        "CREATE TABLE versification_reference",
        "CREATE TABLE text_unit",
        "CREATE TABLE alignment",
        "source_artifact_immutable",
    ]:
        assert required in sql
