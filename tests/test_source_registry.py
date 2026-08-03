from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from scripts.probe_acquisition import safe_zip_members

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def validate_foundation(definition: str, document: dict):
    foundation = load_json("schemas/foundation.schema.json")
    Draft202012Validator(
        foundation["$defs"][definition],
        format_checker=FormatChecker(),
    ).validate(document)


def test_webp_source_matches_foundation_contract():
    source = load_json("registry/sources/engwebp.source.json")
    validate_foundation("source", source)
    assert source["authority_status"] == "official"
    assert source["license_status"] == "public-domain"
    assert source["commercial_use"] == "allowed"


def test_webp_acquisition_target_contract():
    schema = load_json("schemas/acquisition-target.schema.json")
    target = load_json("registry/acquisitions/engwebp-usfm.json")
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(target)
    assert target["requested_url"] == "https://ebible.org/Scriptures/engwebp_usfm.zip"
    assert target["expected_bytes"] == 2_903_202
    assert target["expected_sha256"] == (
        "9b4330ba6baf9bd5fa8ea63a8ff255c9ab326da8c843f0355c23734e61ee6276"
    )
    assert target["upstream_last_modified"] == "2026-07-28T03:14:48Z"
    assert target["verification_status"] == "verified"
    assert target["archive_policy"] == "content-addressed-external"


def test_webp_acquisition_event_and_artifact_are_consistent():
    event = load_json("registry/acquisition-events/engwebp-usfm-20260803.json")
    artifact = load_json("registry/artifacts/engwebp-usfm.artifact.json")
    target = load_json("registry/acquisitions/engwebp-usfm.json")

    validate_foundation("acquisition_event", event)
    validate_foundation("artifact_manifest", artifact)

    assert artifact["acquisition_event_id"] == event["event_id"]
    assert artifact["source_id"] == event["source_id"] == target["source_id"]
    assert artifact["sha256"] == event["observed_sha256"] == target["expected_sha256"]
    assert artifact["byte_size"] == event["observed_bytes"] == target["expected_bytes"]
    assert artifact["archive_uri"] == f"artifact+sha256://{artifact['sha256']}"
    assert artifact["verification_status"] == "verified"


def test_verified_target_requires_pinned_digest():
    schema = load_json("schemas/acquisition-target.schema.json")
    target = load_json("registry/acquisitions/engwebp-usfm.json")
    target["verification_status"] = "verified"
    target["expected_sha256"] = None
    errors = list(Draft202012Validator(schema).iter_errors(target))
    assert errors


def test_zip_path_traversal_is_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../escape.usfm", "synthetic")
    buffer.seek(0)
    with zipfile.ZipFile(buffer) as archive:
        with pytest.raises(ValueError, match="unsafe archive path"):
            safe_zip_members(archive)
