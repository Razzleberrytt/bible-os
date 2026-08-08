from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from bible_os.importers.base import SourceRecord
from bible_os.importers.webp_usfm import WebpUsfmAdapter
from scripts.asv_adapter_smoke import AsvUsfmAdapter
from scripts.webp_adapter_smoke import assert_expected, build_report, download_verified_archive, load_json


class YltUsfmAdapter(WebpUsfmAdapter):
    """YLT identity over the verified generic eBible USFM structure contract."""

    name = "eng-ylt-usfm-v1"


def locator_field(records: list[SourceRecord]) -> tuple[list[str], set[str]]:
    order = [record.source_locator for record in records]
    return order, set(order)


def compare_three_corpora(
    ylt_records: list[SourceRecord],
    asv_records: list[SourceRecord],
    webp_records: list[SourceRecord],
) -> dict[str, Any]:
    ylt_order, ylt = locator_field(ylt_records)
    asv_order, asv = locator_field(asv_records)
    webp_order, webp = locator_field(webp_records)
    all_three = ylt & asv & webp

    return {
        "comparison_corpora": ["registered ASV artifact", "registered WEBP artifact"],
        "three_way_common_locator_count": len(all_three),
        "ylt_asv_common_locator_count": len(ylt & asv),
        "ylt_webp_common_locator_count": len(ylt & webp),
        "asv_webp_common_locator_count": len(asv & webp),
        "ylt_only_locator_count": len(ylt - asv - webp),
        "ylt_only_locators": [x for x in ylt_order if x not in asv and x not in webp],
        "asv_only_locator_count": len(asv - ylt - webp),
        "asv_only_locators": [x for x in asv_order if x not in ylt and x not in webp],
        "webp_only_locator_count": len(webp - ylt - asv),
        "webp_only_locators": [x for x in webp_order if x not in ylt and x not in asv],
        "comparison_text_retention": "locator identities only; no corpus text written to report",
        "mapping_authority": "none",
    }


def build_ylt_report(
    ylt_archive: zipfile.ZipFile,
    asv_archive: zipfile.ZipFile,
    webp_archive: zipfile.ZipFile,
) -> dict[str, Any]:
    ylt_adapter = YltUsfmAdapter()
    asv_adapter = AsvUsfmAdapter()
    webp_adapter = WebpUsfmAdapter()

    report = build_report(ylt_archive, None, adapter=ylt_adapter)
    report.update(
        compare_three_corpora(
            list(ylt_adapter.iter_records(ylt_archive)),
            list(asv_adapter.iter_records(asv_archive)),
            list(webp_adapter.iter_records(webp_archive)),
        )
    )
    report["source_status"] = "verified-structure-only"
    report["publication_eligible"] = False
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a no-retention YLT structure smoke test")
    parser.add_argument("target", type=Path)
    parser.add_argument("--asv-target", type=Path, required=True)
    parser.add_argument("--webp-target", type=Path, required=True)
    parser.add_argument("--expected", type=Path)
    parser.add_argument("--report", type=Path, default=Path("ylt-adapter-report.json"))
    args = parser.parse_args()

    ylt_target = load_json(args.target)
    asv_target = load_json(args.asv_target)
    webp_target = load_json(args.webp_target)

    with tempfile.TemporaryDirectory(prefix="bible-os-ylt-adapter-") as temp_dir:
        root = Path(temp_dir)
        ylt_path, asv_path, webp_path = root / "ylt.zip", root / "asv.zip", root / "webp.zip"
        download_verified_archive(ylt_target, ylt_path)
        download_verified_archive(asv_target, asv_path)
        download_verified_archive(webp_target, webp_path)
        with zipfile.ZipFile(ylt_path) as ylt_archive, zipfile.ZipFile(asv_path) as asv_archive, zipfile.ZipFile(webp_path) as webp_archive:
            report = build_ylt_report(ylt_archive, asv_archive, webp_archive)

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
