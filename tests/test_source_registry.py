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


def test_webp_structural_profile_and_reference_observation():
    baseline = load_json("registry/versification/bsb-chapter-verse-counts.json")
    profile = load_json("registry/import-profiles/engwebp-usfm-smoke.json")
    observation = load_json(
        "registry/versification/observations/engwebp-bsb-romans-doxology.json"
    )
    schema = load_json("schemas/reference-mapping-observation.schema.json")

    Draft202012Validator(schema).validate(observation)
    assert baseline["reference_count"] == 31_102
    assert sum(sum(chapters) for chapters in baseline["books"].values()) == 31_102
    assert sum(len(chapters) for chapters in baseline["books"].values()) == 1_189
    assert profile["verse_records"] == 31_103
    assert profile["versification_delta_count"] == 2
    assert observation["relation_type"] == "relocated"
    assert observation["status"] == "evidence-reviewed"
    assert observation["source_references"] == ["ROM 14:24", "ROM 14:25", "ROM 14:26"]
    assert observation["target_references"] == ["ROM 16:25", "ROM 16:26", "ROM 16:27"]
    assert observation["reference_pairs"] == [
        {
            "source_reference": "ROM 14:24",
            "target_reference": "ROM 16:25",
            "relation_type": "relocated",
        },
        {
            "source_reference": "ROM 14:25",
            "target_reference": "ROM 16:26",
            "relation_type": "relocated",
        },
        {
            "source_reference": "ROM 14:26",
            "target_reference": "ROM 16:27",
            "relation_type": "relocated",
        },
    ]
    assert observation["canonical_mapping_status"] == "materialized"


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
