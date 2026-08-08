from __future__ import annotations

import argparse
import hashlib
import json
import stat
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

CHUNK_SIZE = 1024 * 1024
MAX_SIZE_MARGIN = 1024 * 1024
USER_AGENT = "Bible-OS-Acquisition-Probe/0.1 (+https://github.com/Razzleberrytt/bible-os)"


def load_target(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_zip_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = archive.infolist()
    if not members:
        raise ValueError("archive is empty")

    for member in members:
        logical_path = PurePosixPath(member.filename)
        if logical_path.is_absolute() or ".." in logical_path.parts:
            raise ValueError(f"unsafe archive path: {member.filename}")

        unix_mode = member.external_attr >> 16
        if unix_mode and stat.S_ISLNK(unix_mode):
            raise ValueError(f"symbolic links are not allowed: {member.filename}")

    damaged = archive.testzip()
    if damaged is not None:
        raise ValueError(f"corrupt ZIP member: {damaged}")
    return members


def observe(target: dict[str, Any]) -> dict[str, Any]:
    """Observe a live artifact without accepting it as the registered artifact."""
    expected_bytes = int(target["expected_bytes"])
    expected_sha256 = target.get("expected_sha256")
    request = urllib.request.Request(
        target["requested_url"],
        headers={"User-Agent": USER_AGENT, "Accept": "application/zip,*/*;q=0.1"},
    )

    digest = hashlib.sha256()
    observed_bytes = 0
    response_headers: dict[str, str] = {}

    with tempfile.TemporaryDirectory(prefix="bible-os-acquisition-") as temp_dir:
        archive_path = Path(temp_dir) / "source.zip"
        with urllib.request.urlopen(request, timeout=60) as response, archive_path.open("wb") as output:
            response_headers = {
                "content_type": response.headers.get("Content-Type", ""),
                "content_length": response.headers.get("Content-Length", ""),
                "last_modified": response.headers.get("Last-Modified", ""),
                "etag": response.headers.get("ETag", ""),
                "resolved_url": response.geturl(),
            }
            while chunk := response.read(CHUNK_SIZE):
                observed_bytes += len(chunk)
                if observed_bytes > expected_bytes + MAX_SIZE_MARGIN:
                    raise ValueError("download exceeded the registered size safety margin")
                digest.update(chunk)
                output.write(chunk)

        observed_sha256 = digest.hexdigest()
        with zipfile.ZipFile(archive_path) as archive:
            members = safe_zip_members(archive)
            file_members = [member for member in members if not member.is_dir()]
            usfm_like_members = [
                member
                for member in file_members
                if Path(member.filename).suffix.lower() in {".usfm", ".sfm"}
            ]

    byte_count_matches = observed_bytes == expected_bytes
    sha256_matches = observed_sha256 == expected_sha256 if expected_sha256 else None
    if expected_sha256 is None:
        verification_status = "observed-unpinned"
    elif byte_count_matches and sha256_matches:
        verification_status = "verified"
    else:
        verification_status = "drift-observed"

    return {
        "report_version": "1.1.0",
        "target_id": target["target_id"],
        "source_id": target["source_id"],
        "requested_url": target["requested_url"],
        "resolved_url": response_headers["resolved_url"],
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "observed_sha256": observed_sha256,
        "observed_bytes": observed_bytes,
        "expected_sha256": expected_sha256,
        "expected_bytes": expected_bytes,
        "byte_count_matches": byte_count_matches,
        "sha256_matches": sha256_matches,
        "zip_entries": len(members),
        "zip_file_entries": len(file_members),
        "usfm_like_entries": len(usfm_like_members),
        "archive_safe": True,
        "verification_status": verification_status,
        "response_headers": response_headers,
        "retention": "download deleted after observation",
        "acceptance_effect": "none",
    }


def probe(target: dict[str, Any]) -> dict[str, Any]:
    """Strictly verify that the live artifact still equals the registered artifact."""
    report = observe(target)
    if not report["byte_count_matches"]:
        raise ValueError(
            f"byte count mismatch: expected {report['expected_bytes']}, observed {report['observed_bytes']}"
        )
    if report["sha256_matches"] is False:
        raise ValueError(
            f"SHA-256 mismatch: expected {report['expected_sha256']}, observed {report['observed_sha256']}"
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely probe a registered source artifact")
    parser.add_argument("target", type=Path)
    parser.add_argument("--report", type=Path, default=Path("acquisition-report.json"))
    parser.add_argument(
        "--observe-only",
        action="store_true",
        help="Record live artifact metadata even when it differs from the registered artifact; never accepts drift.",
    )
    args = parser.parse_args()

    target = load_target(args.target)
    report = observe(target) if args.observe_only else probe(target)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"OBSERVED_SHA256={report['observed_sha256']}")
    print(f"OBSERVED_BYTES={report['observed_bytes']}")
    print(f"ZIP_ENTRIES={report['zip_entries']}")
    print(f"USFM_LIKE_ENTRIES={report['usfm_like_entries']}")
    print(f"VERIFICATION_STATUS={report['verification_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
