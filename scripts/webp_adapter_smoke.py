from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from bible_os.importers.webp_usfm import BOOK_ORDER, WebpUsfmAdapter
from scripts.probe_acquisition import CHUNK_SIZE, MAX_SIZE_MARGIN, USER_AGENT, safe_zip_members


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def download_verified_archive(target: dict[str, Any], destination: Path) -> None:
    expected_bytes = int(target["expected_bytes"])
    expected_sha256 = target["expected_sha256"]
    request = urllib.request.Request(
        target["requested_url"],
        headers={"User-Agent": USER_AGENT, "Accept": "application/zip,*/*;q=0.1"},
    )
    digest = hashlib.sha256()
    observed_bytes = 0

    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
        while chunk := response.read(CHUNK_SIZE):
            observed_bytes += len(chunk)
            if observed_bytes > expected_bytes + MAX_SIZE_MARGIN:
                raise ValueError("download exceeded the registered size safety margin")
            digest.update(chunk)
            output.write(chunk)

    if observed_bytes != expected_bytes:
        raise ValueError(
            f"byte count mismatch: expected {expected_bytes}, observed {observed_bytes}"
        )
    observed_sha256 = digest.hexdigest()
    if observed_sha256 != expected_sha256:
        raise ValueError(
            f"SHA-256 mismatch: expected {expected_sha256}, observed {observed_sha256}"
        )


def build_report(archive: zipfile.ZipFile) -> dict[str, Any]:
    safe_zip_members(archive)
    adapter = WebpUsfmAdapter()
    probe = adapter.probe(archive)
    if not probe.compatible:
        raise ValueError("WEBP adapter did not recognize the archive")

    records = list(adapter.iter_records(archive))
    book_counts = Counter(record.book_code for record in records)
    chapter_loci = {(record.book_code, record.chapter) for record in records}
    empty_payloads = sum(not record.raw_payload.strip() for record in records)
    range_labels = sum("-" in record.verse_label or "–" in record.verse_label for record in records)

    report = {
        "report_version": "1.0.0",
        "adapter": adapter.name,
        "archive_files": probe.archive_files,
        "source_files": probe.source_files,
        "recognized_books": len(probe.recognized_books),
        "recognized_book_ids": list(probe.recognized_books),
        "unrecognized_book_ids": list(probe.unrecognized_book_ids),
        "expected_canonical_books": len(BOOK_ORDER),
        "chapter_loci": len(chapter_loci),
        "verse_records": len(records),
        "empty_raw_payloads": empty_payloads,
        "verse_range_labels": range_labels,
        "first_locator": records[0].source_locator if records else None,
        "last_locator": records[-1].source_locator if records else None,
        "first_sequence": records[0].source_sequence if records else None,
        "last_sequence": records[-1].source_sequence if records else None,
        "book_record_counts": dict(sorted(book_counts.items(), key=lambda item: BOOK_ORDER.index(item[0]))),
        "text_retention": "raw payloads streamed for validation; no corpus text written to report",
    }
    return report


def assert_expected(report: dict[str, Any], expected: dict[str, Any]) -> None:
    for key, expected_value in expected.items():
        if key.startswith("_"):
            continue
        observed_value = report.get(key)
        if observed_value != expected_value:
            raise ValueError(
                f"WEBP smoke metric mismatch for {key}: "
                f"expected {expected_value!r}, observed {observed_value!r}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a no-retention WEBP adapter smoke test")
    parser.add_argument("target", type=Path)
    parser.add_argument("--expected", type=Path)
    parser.add_argument("--report", type=Path, default=Path("webp-adapter-report.json"))
    args = parser.parse_args()

    target = load_json(args.target)
    with tempfile.TemporaryDirectory(prefix="bible-os-webp-adapter-") as temp_dir:
        archive_path = Path(temp_dir) / "engwebp_usfm.zip"
        download_verified_archive(target, archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            report = build_report(archive)

    if args.expected:
        assert_expected(report, load_json(args.expected))
        report["expected_profile"] = str(args.expected)
        report["profile_status"] = "matched"
    else:
        report["profile_status"] = "observed-unpinned"

    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
