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


def test_webp_source_matches_foundation_contract():
    foundation = load_json("schemas/foundation.schema.json")
    source = load_json("registry/sources/engwebp.source.json")
    Draft202012Validator(
        foundation["$defs"]["source"],
        format_checker=FormatChecker(),
    ).validate(source)
    assert source["authority_status"] == "official"
    assert source["license_status"] == "public-domain"
    assert source["commercial_use"] == "allowed"


def test_webp_acquisition_target_contract():
    schema = load_json("schemas/acquisition-target.schema.json")
    target = load_json("registry/acquisitions/engwebp-usfm.json")
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(target)
    assert target["requested_url"] == "https://ebible.org/Scriptures/engwebp_usfm.zip"
    assert target["expected_bytes"] == 2_907_381
    assert target["archive_policy"] == "content-addressed-external"


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
