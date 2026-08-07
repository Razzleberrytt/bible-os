from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

from bible_os.exports import verify_reproducible_ndjson
from bible_os.importers.webp_usfm import BOOK_ORDER, WebpUsfmAdapter
from scripts.asv_full_ci import ARTIFACT_PATH as ASV_ARTIFACT_PATH
from scripts.asv_full_ci import TARGET_PATH as ASV_TARGET_PATH
from scripts.asv_full_ci import source_rows as asv_source_rows
from scripts.asv_webp_lexical_fingerprint_ci import (
    locator,
    locator_sort_key,
    nearest_rank,
    normalize_tokens,
)
from scripts.asv_webp_wj_record_shape_ci import (
    classify_opening_payload,
    iter_source_shape_records,
)
from scripts.asv_webp_gospel_structure_ci import source_documents
from scripts.webp_adapter_smoke import download_verified_archive, load_json
from scripts.webp_db_load import ARTIFACT_PATH as WEBP_ARTIFACT_PATH
from scripts.webp_db_load import TARGET_PATH as WEBP_TARGET_PATH
from scripts.webp_db_load import source_rows as webp_source_rows


STRATUM_ORDER = ("webp-opening-wj", "webp-non-wj")
FOCUS_BOOKS = ("MAT", "MRK", "LUK", "JHN", "ACT", "ROM", "REV")
PPM = 1_000_000


def ratio_ppm(numerator: int, denominator: int) -> int:
    if numerator < 0 or denominator < 0:
        raise ValueError("ratio inputs must be nonnegative")
    if denominator == 0:
        return 0 if numerator == 0 else numerator * PPM
    return (numerator * PPM + denominator // 2) // denominator


def mean_rounded(values: Sequence[int]) -> int:
    if not values:
        return 0
    return (sum(values) + len(values) // 2) // len(values)


def opening_classes_by_locator(
    archive: zipfile.ZipFile,
    adapter: WebpUsfmAdapter,
) -> dict[str, str]:
    documents = source_documents(archive)
    adapter_by_book: dict[str, list[Any]] = defaultdict(list)
    for record in adapter.iter_records(archive):
        adapter_by_book[record.book_code].append(record)

    classes: dict[str, str] = {}
    for book_code in BOOK_ORDER:
        document = documents.get(book_code)
        adapter_records = adapter_by_book.get(book_code, [])
        if document is None and not adapter_records:
            continue
        if document is None:
            raise ValueError(f"missing source document for {book_code}")
        source_records = list(iter_source_shape_records(document["text"]))
        if len(source_records) != len(adapter_records):
            raise ValueError(
                f"source/adapter record count mismatch for {book_code}: "
                f"{len(source_records)} != {len(adapter_records)}"
            )
        for source_record, adapter_record in zip(
            source_records, adapter_records, strict=True
        ):
            value = adapter_record.source_locator
            if value in classes:
                raise ValueError(f"duplicate WEBP source locator: {value}")
            classes[value] = classify_opening_payload(
                source_record.opening_payload
            )
    return classes


def _rows_by_locator(
    rows: Iterable[dict[str, Any]], translation: str
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = locator(row)
        if value in result:
            raise ValueError(f"duplicate {translation} locator detected: {value}")
        result[value] = row
    return result


def build_stratified_records(
    asv_rows: list[dict[str, Any]],
    webp_rows: list[dict[str, Any]],
    webp_opening_classes: dict[str, str],
) -> list[dict[str, Any]]:
    asv_by_locator = _rows_by_locator(asv_rows, "ASV")
    webp_by_locator = _rows_by_locator(webp_rows, "WEBP")
    if set(webp_by_locator) != set(webp_opening_classes):
        missing = sorted(set(webp_by_locator) - set(webp_opening_classes))
        extra = sorted(set(webp_opening_classes) - set(webp_by_locator))
        raise ValueError(
            "WEBP opening-class locator mismatch: "
            f"missing={len(missing)}, extra={len(extra)}"
        )

    records: list[dict[str, Any]] = []
    shared = sorted(
        set(asv_by_locator) & set(webp_by_locator),
        key=locator_sort_key,
    )
    for value in shared:
        asv = asv_by_locator[value]
        webp = webp_by_locator[value]
        if (
            asv.get("realization_type") != "text"
            or webp.get("realization_type") != "text"
        ):
            continue

        asv_text = asv.get("source_text")
        webp_text = webp.get("source_text")
        if not isinstance(asv_text, str) or not isinstance(webp_text, str):
            raise ValueError(f"text realization is missing source text at {value}")
        asv_tokens = normalize_tokens(asv_text)
        webp_tokens = normalize_tokens(webp_text)
        if not asv_tokens or not webp_tokens:
            raise ValueError(f"text realization normalized to zero tokens at {value}")

        asv_count = len(asv_tokens)
        webp_count = len(webp_tokens)
        opening_class = webp_opening_classes[value]
        stratum = (
            "webp-opening-wj"
            if opening_class == "wj"
            else "webp-non-wj"
        )
        records.append(
            {
                "stratification_version": "1.0.0",
                "locator": value,
                "book_code": asv["book_code"],
                "stratum": stratum,
                "webp_opening_class": opening_class,
                "asv_token_count": asv_count,
                "webp_token_count": webp_count,
                "token_count_delta": webp_count - asv_count,
                "token_count_abs_delta": abs(webp_count - asv_count),
                "webp_to_asv_token_ratio_ppm": ratio_ppm(
                    webp_count, asv_count
                ),
                "comparison_direction": (
                    "webp-longer"
                    if webp_count > asv_count
                    else "asv-longer"
                    if asv_count > webp_count
                    else "equal"
                ),
            }
        )
    return records


def summarize_stratum(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    ratios = [
        int(record["webp_to_asv_token_ratio_ppm"]) for record in records
    ]
    asv_total = sum(int(record["asv_token_count"]) for record in records)
    webp_total = sum(int(record["webp_token_count"]) for record in records)
    return {
        "locator_count": len(records),
        "asv_token_count": asv_total,
        "webp_token_count": webp_total,
        "token_count_delta": webp_total - asv_total,
        "token_count_abs_delta": sum(
            int(record["token_count_abs_delta"]) for record in records
        ),
        "webp_to_asv_total_token_ratio_ppm": ratio_ppm(
            webp_total, asv_total
        ),
        "mean_locator_token_ratio_ppm": mean_rounded(ratios),
        "median_locator_token_ratio_ppm": (
            nearest_rank(ratios, 50) if ratios else 0
        ),
        "p90_locator_token_ratio_ppm": (
            nearest_rank(ratios, 90) if ratios else 0
        ),
        "webp_longer_count": sum(
            record["comparison_direction"] == "webp-longer"
            for record in records
        ),
        "asv_longer_count": sum(
            record["comparison_direction"] == "asv-longer"
            for record in records
        ),
        "equal_count": sum(
            record["comparison_direction"] == "equal"
            for record in records
        ),
    }


def grouped_strata(
    records: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record["stratum"])].append(record)
    return [
        {"stratum": stratum, **summarize_stratum(grouped.get(stratum, []))}
        for stratum in STRATUM_ORDER
    ]


def book_summaries(
    records: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record["book_code"])].append(record)
    return [
        {
            "book_code": book_code,
            "locator_count": len(grouped[book_code]),
            "strata": grouped_strata(grouped[book_code]),
        }
        for book_code in BOOK_ORDER
        if grouped.get(book_code)
    ]


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise ValueError("stratification stream must not be empty")
    fingerprint = verify_reproducible_ndjson(records)
    return {
        **fingerprint,
        "analysis_contract": "shared-text-locator-opening-wj-stratification-v1",
        "normalization_contract": (
            "unicode-nfkc-casefold-alnum-apostrophe-token-v1"
        ),
        "shared_text_text_locator_count": len(records),
        "strata": grouped_strata(records),
        "book_summaries": book_summaries(records),
        "focus_books": list(FOCUS_BOOKS),
        "scripture_text_reported": False,
        "token_lists_reported": False,
        "locator_identifiers_reported": False,
        "per_locator_text_digests_reported": False,
        "parser_behavior_changed": False,
        "text_boundaries_defined": False,
        "corpus_mutation": "not-performed",
        "mapping_authority": "none",
        "execution_eligible": False,
        "publication_eligible": False,
        "retention": (
            "numeric per-locator records fingerprinted in memory; "
            "only aggregate strata and book metrics are reported"
        ),
    }


def assert_expected(observed: dict[str, Any], expected: dict[str, Any]) -> None:
    if observed != expected:
        observed_rendered = json.dumps(
            observed, sort_keys=True, separators=(",", ":")
        )
        expected_rendered = json.dumps(
            expected, sort_keys=True, separators=(",", ":")
        )
        raise ValueError(
            "ASV/WEBP opening-wj token stratification mismatch: "
            f"expected {len(expected_rendered)} canonical bytes, "
            f"observed {len(observed_rendered)} canonical bytes"
        )


def run(expected_path: Path | None = None) -> dict[str, Any]:
    asv_target = load_json(ASV_TARGET_PATH)
    asv_artifact = load_json(ASV_ARTIFACT_PATH)
    webp_target = load_json(WEBP_TARGET_PATH)
    webp_artifact = load_json(WEBP_ARTIFACT_PATH)

    with tempfile.TemporaryDirectory(
        prefix="bible-os-wj-token-strata-"
    ) as temp_dir:
        temp_root = Path(temp_dir)
        asv_archive_path = temp_root / asv_artifact["filename"]
        webp_archive_path = temp_root / webp_artifact["filename"]
        download_verified_archive(asv_target, asv_archive_path)
        download_verified_archive(webp_target, webp_archive_path)
        with zipfile.ZipFile(asv_archive_path) as archive:
            asv_rows = asv_source_rows(archive)
        with zipfile.ZipFile(webp_archive_path) as archive:
            webp_rows = webp_source_rows(archive)
            opening_classes = opening_classes_by_locator(
                archive, WebpUsfmAdapter()
            )

    summary = summarize_records(
        build_stratified_records(asv_rows, webp_rows, opening_classes)
    )
    if expected_path is None:
        profile_status = "observed-unpinned"
    else:
        assert_expected(summary, load_json(expected_path))
        profile_status = "matched"

    return {
        "status": "passed",
        "experiment": "asv-webp-wj-token-strata-v1",
        "asv_artifact_sha256": asv_artifact["sha256"],
        "webp_artifact_sha256": webp_artifact["sha256"],
        "summary": summary,
        "profile_status": profile_status,
        "expected_profile": (
            str(expected_path) if expected_path is not None else None
        ),
        "corpus_bytes_committed": False,
        "scripture_text_reported": False,
        "token_lists_reported": False,
        "locator_identifiers_reported": False,
        "per_locator_text_digests_reported": False,
        "parser_behavior_changed": False,
        "text_boundaries_defined": False,
        "mapping_authority": "none",
        "execution_eligible": False,
        "publication_eligible": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Stratify shared ASV/WEBP token counts by WEBP opening wj status "
            "without reporting scripture text"
        )
    )
    parser.add_argument("--expected", type=Path)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("asv-webp-wj-token-strata-report.json"),
    )
    args = parser.parse_args(argv)

    report = run(args.expected)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
