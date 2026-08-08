from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from bible_os.artifacts import (
    ArtifactStoreError,
    artifact_uri,
    object_path,
    parse_artifact_uri,
    put_file,
    resolve_uri,
    verify_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
WEBP_MANIFEST = ROOT / "registry" / "artifacts" / "engwebp-usfm.artifact.json"


def test_artifact_uri_round_trip() -> None:
    digest = "a" * 64
    uri = artifact_uri(digest)

    assert uri == f"artifact+sha256://{digest}"
    assert parse_artifact_uri(uri) == digest


@pytest.mark.parametrize(
    "value",
    [
        "",
        "artifact+sha256://ABC",
        "artifact+sha256://" + "A" * 64,
        "https://example.test/object",
        "artifact+sha256://" + "a" * 63,
    ],
)
def test_parse_artifact_uri_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ArtifactStoreError):
        parse_artifact_uri(value)


def test_put_file_is_content_addressed_and_deduplicated(tmp_path: Path) -> None:
    source = tmp_path / "source.zip"
    source.write_bytes(b"immutable source observation")
    store = tmp_path / "store"
    expected_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()

    first = put_file(source, store)
    second = put_file(source, store)

    assert first.sha256 == expected_sha256
    assert first.uri == f"artifact+sha256://{expected_sha256}"
    assert first.path == object_path(store, expected_sha256)
    assert first.path.read_bytes() == source.read_bytes()
    assert first.already_present is False
    assert second.already_present is True
    assert second.path == first.path


def test_resolve_uri_detects_corruption(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"original")
    stored = put_file(source, tmp_path / "store")
    stored.path.write_bytes(b"corrupt")

    with pytest.raises(ArtifactStoreError, match="digest mismatch"):
        resolve_uri(stored.uri, tmp_path / "store")


def test_verify_manifest_binds_uri_digest_and_size(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"manifest bound payload")
    stored = put_file(source, tmp_path / "store")
    manifest = {
        "artifact_id": "art_fixture",
        "sha256": stored.sha256,
        "byte_size": stored.byte_size,
        "archive_uri": stored.uri,
    }

    assert verify_manifest(manifest, tmp_path / "store") == stored.path

    bad_manifest = dict(manifest)
    bad_manifest["archive_uri"] = artifact_uri("b" * 64)
    with pytest.raises(ArtifactStoreError, match="does not match"):
        verify_manifest(bad_manifest, tmp_path / "store")


def test_existing_webp_manifest_uses_supported_content_addressed_uri() -> None:
    manifest = json.loads(WEBP_MANIFEST.read_text(encoding="utf-8"))

    assert parse_artifact_uri(manifest["archive_uri"]) == manifest["sha256"]
    assert manifest["verification_status"] == "verified"
