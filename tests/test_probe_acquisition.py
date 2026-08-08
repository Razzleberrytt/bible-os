from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from scripts import probe_acquisition

ROOT = Path(__file__).resolve().parents[1]


def make_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("01GEN.usfm", "\\id GEN\n")
        archive.writestr("README.txt", "fixture")
    return buffer.getvalue()


class FakeResponse(io.BytesIO):
    def __init__(self, payload: bytes) -> None:
        super().__init__(payload)
        self.headers = {
            "Content-Type": "application/zip",
            "Content-Length": str(len(payload)),
            "Last-Modified": "Fri, 07 Aug 2026 12:00:00 GMT",
            "ETag": '"fixture-v2"',
        }

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def geturl(self) -> str:
        return "https://example.test/source.zip"


def target(payload: bytes, *, expected_bytes: int | None = None, expected_sha256: str | None = None) -> dict:
    return {
        "target_id": "tgt_fixture",
        "source_id": "src_fixture",
        "requested_url": "https://example.test/source.zip",
        "expected_bytes": len(payload) if expected_bytes is None else expected_bytes,
        "expected_sha256": hashlib.sha256(payload).hexdigest() if expected_sha256 is None else expected_sha256,
    }


def install_response(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> None:
    monkeypatch.setattr(
        probe_acquisition.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse(payload),
    )


def test_observe_reports_drift_without_accepting_it(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = make_zip()
    install_response(monkeypatch, payload)
    registered = target(payload, expected_bytes=len(payload) - 1, expected_sha256="0" * 64)

    report = probe_acquisition.observe(registered)

    assert report["verification_status"] == "drift-observed"
    assert report["observed_bytes"] == len(payload)
    assert report["observed_sha256"] == hashlib.sha256(payload).hexdigest()
    assert report["byte_count_matches"] is False
    assert report["sha256_matches"] is False
    assert report["zip_entries"] == 2
    assert report["zip_file_entries"] == 2
    assert report["usfm_like_entries"] == 1
    assert report["archive_safe"] is True
    assert report["acceptance_effect"] == "none"
    assert report["retention"] == "download deleted after observation"


def test_strict_probe_still_rejects_byte_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = make_zip()
    install_response(monkeypatch, payload)
    registered = target(payload, expected_bytes=len(payload) - 1)

    with pytest.raises(ValueError, match="byte count mismatch"):
        probe_acquisition.probe(registered)


def test_strict_probe_verifies_exact_registered_artifact(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = make_zip()
    install_response(monkeypatch, payload)

    report = probe_acquisition.probe(target(payload))

    assert report["verification_status"] == "verified"
    assert report["byte_count_matches"] is True
    assert report["sha256_matches"] is True


def test_recorded_webp_drift_is_quarantined_and_schema_valid() -> None:
    foundation = json.loads((ROOT / "schemas/foundation.schema.json").read_text(encoding="utf-8"))
    event = json.loads(
        (ROOT / "registry/acquisition-events/engwebp-usfm-20260808-drift.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(
        foundation["$defs"]["acquisition_event"],
        format_checker=FormatChecker(),
    ).validate(event)

    assert event["result"] == "quarantined"
    assert event["observed_bytes"] == 2_903_587
    assert event["observed_sha256"] == "1c5957d487d9473c87ea5c7e6acffd0caa402ce98c4a577f3164cfd94b9b437d"
    assert "not accepted" in event["error"]
