from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from bible_os.importers.base import SourceRecord
from bible_os.importers.webp_usfm import WebpUsfmAdapter
from scripts.webp_adapter_smoke import (
    assert_expected,
    build_report,
    download_verified_archive,
    load_json,
)


class AsvUsfmAdapter(WebpUsfmAdapter):
    """ASV identity over the verified generic eBible USFM structure contract."""

    name = "eng-asv-usfm-v1"


def compare_locator_sets(
    asv_records: list[SourceRecord],
    webp_records: list[SourceRecord],
) -> dict[str, Any]:
    """Compare source locators without exposing or retaining scripture text."""

    asv_order = [record.source_locator for record in asv_records]
    webp_order = [record.source_locator for record in webp_records]
    asv_set = set(asv_order)
    webp_set = set(webp_order)

    return {
        "comparison_corpus": "registered WEBP artifact",
        "common_locator_count": len(asv_set & webp_set),
        "asv_only_locator_count": len(asv_set - webp_set),
        "asv_only_locators": [locator for locator in asv_order if locator not in webp_set],
        "webp_only_locator_count": len(webp_set - asv_set),
        "webp_only_locators": [locator for locator in webp_order if locator not in asv_set],
        "comparison_text_retention": "locator identities only; no corpus text written to report",
    }


def build_asv_report(
    asv_archive: zipfile.ZipFile,
    webp_archive: zipfile.ZipFile,
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    asv_adapter = AsvUsfmAdapter()
    webp_adapter = WebpUsfmAdapter()

    report = build_report(asv_archive, baseline, adapter=asv_adapter)
    asv_records = list(asv_adapter.iter_records(asv_archive))
    webp_records = list(webp_adapter.iter_records(webp_archive))
    report.update(compare_locator_sets(asv_records, webp_records))
    report["source_status"] = "verified-structure-only"
    report["publication_eligible"] = False
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a no-retention ASV structure smoke test and compare locators with WEBP"
    )
    parser.add_argument("target", type=Path)
    parser.add_argument("--webp-target", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--expected", type=Path)
    parser.add_argument("--report", type=Path, default=Path("asv-adapter-report.json"))
    args = parser.parse_args()

    asv_target = load_json(args.target)
    webp_target = load_json(args.webp_target)
    baseline = load_json(args.baseline) if args.baseline else None

    with tempfile.TemporaryDirectory(prefix="bible-os-asv-adapter-") as temp_dir:
        asv_path = Path(temp_dir) / "eng-asv_usfm.zip"
        webp_path = Path(temp_dir) / "engwebp_usfm.zip"
        download_verified_archive(asv_target, asv_path)
        download_verified_archive(webp_target, webp_path)
        with zipfile.ZipFile(asv_path) as asv_archive, zipfile.ZipFile(webp_path) as webp_archive:
            report = build_asv_report(asv_archive, webp_archive, baseline)

    if args.expected:
        assert_expected(report, load_json(args.expected))
        report["expected_profile"] = str(args.expected)
        report["profile_status"] = "matched"
    else:
        report["profile_status"] = "observed-unpinned"

    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
