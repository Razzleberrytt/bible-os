from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]


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


def test_ylt_registered_acquisition_target_is_explicitly_unpinned():
    schema = load_json("schemas/acquisition-target.schema.json")
    target = load_json("registry/acquisitions/engylt-usfm.json")
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(target)

    assert target["source_id"] == "src_engyltpublic"
    assert target["requested_url"] == "https://ebible.org/Scriptures/engylt_usfm.zip"
    assert target["expected_bytes"] == 1_385_550
    assert target["upstream_last_modified"] == "2026-06-11T13:23:20Z"
    assert target["source_files_date"] == "2025-12-12"
    assert target["expected_sha256"] is None
    assert target["verification_status"] == "registered"
    assert target["archive_policy"] == "content-addressed-external"
