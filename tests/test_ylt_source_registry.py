from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SHA256 = "1a7f889c412b03c04dc65be386c83d4e3bafb4c58fd5f4e35584240dafe09831"


def load_json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def validate_foundation(definition: str, document: dict):
    foundation = load_json("schemas/foundation.schema.json")
    Draft202012Validator(
        foundation["$defs"][definition],
        format_checker=FormatChecker(),
    ).validate(document)


def test_ylt_source_matches_foundation_contract():
    source = load_json("registry/sources/engylt.source.json")
    validate_foundation("source", source)

    assert source["source_id"] == "src_engyltpublic"
    assert source["authority_status"] == "official"
    assert source["language_codes"] == ["eng"]
    assert source["license_status"] == "public-domain"
    assert source["commercial_use"] == "allowed"
    assert "https://ebible.org/Scriptures/engylt_usfm.zip" in source["official_urls"]


def test_ylt_acquisition_target_is_sha_pinned_and_verified():
    schema = load_json("schemas/acquisition-target.schema.json")
    target = load_json("registry/acquisitions/engylt-usfm.json")
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(target)

    assert target["source_id"] == "src_engyltpublic"
    assert target["requested_url"] == "https://ebible.org/Scriptures/engylt_usfm.zip"
    assert target["expected_bytes"] == 1_385_550
    assert target["upstream_last_modified"] == "2026-06-11T13:23:20Z"
    assert target["source_files_date"] == "2025-12-12"
    assert target["expected_sha256"] == EXPECTED_SHA256
    assert target["verification_status"] == "verified"
    assert target["archive_policy"] == "content-addressed-external"


def test_ylt_acquisition_event_matches_foundation_contract():
    event = load_json("registry/acquisition-events/engylt-usfm-20260808.json")
    validate_foundation("acquisition_event", event)

    assert event["source_id"] == "src_engyltpublic"
    assert event["result"] == "success"
    assert event["observed_bytes"] == 1_385_550
    assert event["observed_sha256"] == EXPECTED_SHA256
    assert event["error"] is None


def test_ylt_artifact_manifest_binds_verified_identity():
    artifact = load_json("registry/artifacts/engylt-usfm.artifact.json")

    assert artifact["source_id"] == "src_engyltpublic"
    assert artifact["acquisition_event_id"] == "acq_engylt20260808a"
    assert artifact["sha256"] == EXPECTED_SHA256
    assert artifact["byte_size"] == 1_385_550
    assert artifact["archive_uri"] == f"artifact+sha256://{EXPECTED_SHA256}"
    assert artifact["verification_status"] == "verified"
    assert artifact["license_assertion"]["status"] == "public-domain"
