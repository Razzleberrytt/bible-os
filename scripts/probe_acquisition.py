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


def probe(target: dict[str, Any]) -> dict[str, Any]:
    expected_bytes = int(target["expected_bytes"])
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
        if observed_bytes != expected_bytes:
            raise ValueError(
                f"byte count mismatch: expected {expected_bytes}, observed {observed_bytes}"
            )

        with zipfile.ZipFile(archive_path) as archive:
            members = safe_zip_members(archive)
            file_members = [member for member in members if not member.is_dir()]
            usfm_like_members = [
                member
                for member in file_members
                if Path(member.filename).suffix.lower() in {".usfm", ".sfm"}
            ]

        expected_sha256 = target.get("expected_sha256")
        if expected_sha256 and observed_sha256 != expected_sha256:
            raise ValueError(
                f"SHA-256 mismatch: expected {expected_sha256}, observed {observed_sha256}"
            )

        verification_status = "verified" if expected_sha256 else "observed-unpinned"
        return {
            "report_version": "1.0.0",
            "target_id": target["target_id"],
            "source_id": target["source_id"],
            "requested_url": target["requested_url"],
            "resolved_url": response_headers["resolved_url"],
            "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "observed_sha256": observed_sha256,
            "observed_bytes": observed_bytes,
            "expected_bytes": expected_bytes,
            "zip_entries": len(members),
            "zip_file_entries": len(file_members),
            "usfm_like_entries": len(usfm_like_members),
            "archive_safe": True,
            "verification_status": verification_status,
            "response_headers": response_headers,
            "retention": "download deleted after verification",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely probe a registered source artifact")
    parser.add_argument("target", type=Path)
    parser.add_argument("--report", type=Path, default=Path("acquisition-report.json"))
    args = parser.parse_args()

    report = probe(load_target(args.target))
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"OBSERVED_SHA256={report['observed_sha256']}")
    print(f"OBSERVED_BYTES={report['observed_bytes']}")
    print(f"ZIP_ENTRIES={report['zip_entries']}")
    print(f"USFM_LIKE_ENTRIES={report['usfm_like_entries']}")
    print(f"VERIFICATION_STATUS={report['verification_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
