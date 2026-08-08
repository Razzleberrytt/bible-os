from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest

from bible_os.acquisition import AcquisitionArchiveError, archive_registered_source
from bible_os.artifacts import object_path


class FakeResponse(io.BytesIO):
    def __init__(self, payload: bytes) -> None:
        super().__init__(payload)
        self.headers = {
            "Content-Type": "application/zip",
            "Content-Length": str(len(payload)),
            "Last-Modified": "Sat, 08 Aug 2026 00:00:00 GMT",
            "ETag": '"fixture"',
        }

    def geturl(self) -> str:
        return "https://example.test/source.zip"


def opener_for(payload: bytes):
    def opener(request, timeout):
        assert request.full_url == "https://example.test/source.zip"
        assert timeout == 60
        return FakeResponse(payload)

    return opener


def target_for(payload: bytes) -> dict:
    return {
        "target_id": "tgt_fixture",
        "source_id": "src_fixture",
        "requested_url": "https://example.test/source.zip",
        "expected_bytes": len(payload),
        "expected_sha256": hashlib.sha256(payload).hexdigest(),
    }


def stored_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file()] if root.exists() else []


def test_archive_registered_source_retains_exact_verified_bytes(tmp_path: Path) -> None:
    payload = b"exact registered source observation"
    target = target_for(payload)
    store = tmp_path / "store"

    report = archive_registered_source(target, store, opener=opener_for(payload))

    expected_path = object_path(store, target["expected_sha256"])
    assert expected_path.read_bytes() == payload
    assert report["verification_status"] == "verified"
    assert report["archive_uri"] == f"artifact+sha256://{target['expected_sha256']}"
    assert report["archive_effect"] == "stored-new"
    assert report["observed_bytes"] == len(payload)
    assert report["observed_sha256"] == target["expected_sha256"]
    assert report["retention"] == "verified bytes retained in content-addressed store"
    assert report["source_text_reported"] is False


def test_archive_registered_source_deduplicates_identical_observation(tmp_path: Path) -> None:
    payload = b"same observation"
    target = target_for(payload)
    store = tmp_path / "store"

    first = archive_registered_source(target, store, opener=opener_for(payload))
    second = archive_registered_source(target, store, opener=opener_for(payload))

    assert first["archive_effect"] == "stored-new"
    assert second["archive_effect"] == "deduplicated-existing"
    assert len(stored_files(store)) == 1


def test_archive_rejects_hash_drift_without_retaining_changed_bytes(tmp_path: Path) -> None:
    registered = b"registered"
    changed = b"publisherrr"
    assert len(registered) == len(changed)
    target = target_for(registered)
    store = tmp_path / "store"

    with pytest.raises(AcquisitionArchiveError, match="SHA-256 mismatch"):
        archive_registered_source(target, store, opener=opener_for(changed))

    assert stored_files(store) == []


def test_archive_rejects_size_drift_without_retention(tmp_path: Path) -> None:
    registered = b"registered"
    changed = b"registered plus drift"
    target = target_for(registered)
    store = tmp_path / "store"

    with pytest.raises(AcquisitionArchiveError, match="byte count mismatch"):
        archive_registered_source(target, store, opener=opener_for(changed))

    assert stored_files(store) == []


def test_archive_requires_pinned_sha256_before_network_access(tmp_path: Path) -> None:
    payload = b"unpinned"
    target = target_for(payload)
    target.pop("expected_sha256")
    called = False

    def forbidden_opener(request, timeout):
        nonlocal called
        called = True
        raise AssertionError("network must not be used for unpinned archival")

    with pytest.raises(AcquisitionArchiveError, match="archival requires"):
        archive_registered_source(target, tmp_path / "store", opener=forbidden_opener)

    assert called is False
