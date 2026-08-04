from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

from bible_os.importers.base import SourceRecord
from bible_os.importers.webp_usfm import BOOK_INDEX, BOOK_ORDER, WebpUsfmAdapter, extract_visible_text
from scripts.asv_adapter_smoke import AsvUsfmAdapter
from scripts.asv_full_ci import ARTIFACT_PATH as ASV_ARTIFACT_PATH
from scripts.asv_full_ci import TARGET_PATH as ASV_TARGET_PATH
from scripts.asv_webp_gospel_structure_ci import (
    CONTROL_BOOKS,
    FOCUS_BOOKS,
    GOSPEL_BOOKS,
    leading_marker,
    marker_class,
    marker_root,
    ratio_ppm,
)
from scripts.asv_webp_lexical_fingerprint_ci import normalize_tokens
from scripts.webp_adapter_smoke import download_verified_archive, load_json
from scripts.webp_db_load import ARTIFACT_PATH as WEBP_ARTIFACT_PATH
from scripts.webp_db_load import TARGET_PATH as WEBP_TARGET_PATH


ROOT = Path(__file__).resolve().parents[1]
COUNT_KEYS = (
    "line_count",
    "record_count",
    "zero_token_line_count",
    "visible_token_count",
    "exact_duplicate_line_count",
    "exact_duplicate_token_count",
    "contained_duplicate_line_count",
    "contained_duplicate_token_count",
)


def contains_contiguous(needle: tuple[str, ...], haystack: tuple[str, ...]) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    width = len(needle)
    return any(haystack[index : index + width] == needle for index in range(len(haystack) - width + 1))


def empty_counts() -> Counter[str]:
    return Counter({key: 0 for key in COUNT_KEYS})


def add_counts(target: Counter[str], source: dict[str, Any] | Counter[str]) -> None:
    for key in COUNT_KEYS:
        target[key] += int(source.get(key, 0))


def finalize_counts(counts: dict[str, Any] | Counter[str]) -> dict[str, int]:
    result = {key: int(counts.get(key, 0)) for key in COUNT_KEYS}
    result["exact_duplicate_line_ratio_ppm"] = ratio_ppm(
        result["exact_duplicate_line_count"], result["line_count"]
    )
    result["exact_duplicate_token_ratio_ppm"] = ratio_ppm(
        result["exact_duplicate_token_count"], result["visible_token_count"]
    )
    result["contained_duplicate_line_ratio_ppm"] = ratio_ppm(
        result["contained_duplicate_line_count"], result["line_count"]
    )
    result["contained_duplicate_token_ratio_ppm"] = ratio_ppm(
        result["contained_duplicate_token_count"], result["visible_token_count"]
    )
    return result


def marker_rows(marker_counts: dict[str, Counter[str]]) -> list[dict[str, Any]]:
    rows = []
    for marker, counts in marker_counts.items():
        row: dict[str, Any] = {"marker": marker}
        row.update(finalize_counts(counts))
        rows.append(row)
    return sorted(rows, key=lambda row: (-row["visible_token_count"], row["marker"]))


def summarize_records(records: Sequence[SourceRecord]) -> dict[str, Any]:
    marker_counts: dict[str, Counter[str]] = defaultdict(empty_counts)
    totals = empty_counts()
    records_with_character_style = 0

    for record in records:
        lines: list[tuple[str | None, tuple[str, ...]]] = []
        for raw_line in record.raw_payload.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            marker = leading_marker(stripped)
            tokens = tuple(normalize_tokens(extract_visible_text(stripped)))
            lines.append((marker, tokens))

        record_markers: set[str] = set()
        record_has_character_style = False
        for index, (marker, tokens) in enumerate(lines):
            if marker is None or marker_class(marker) != "character-style":
                continue

            record_has_character_style = True
            root = marker_root(marker)
            record_markers.add(root)
            counts = marker_counts[root]
            counts["line_count"] += 1
            counts["visible_token_count"] += len(tokens)
            if not tokens:
                counts["zero_token_line_count"] += 1

            other_lines = [other_tokens for other_index, (_, other_tokens) in enumerate(lines) if other_index != index and other_tokens]
            exact_duplicate = bool(tokens) and any(tokens == other_tokens for other_tokens in other_lines)
            contained_duplicate = bool(tokens) and any(
                contains_contiguous(tokens, other_tokens) for other_tokens in other_lines
            )
            if exact_duplicate:
                counts["exact_duplicate_line_count"] += 1
                counts["exact_duplicate_token_count"] += len(tokens)
            if contained_duplicate:
                counts["contained_duplicate_line_count"] += 1
                counts["contained_duplicate_token_count"] += len(tokens)

        if record_has_character_style:
            records_with_character_style += 1
        for root in record_markers:
            marker_counts[root]["record_count"] += 1

    for counts in marker_counts.values():
        add_counts(totals, counts)
    totals["record_count"] = records_with_character_style

    return {
        "record_count": len(records),
        "records_with_character_style": records_with_character_style,
        "character_style": finalize_counts(totals),
        "markers": marker_rows(marker_counts),
    }


def analyze_translation(records: Iterable[SourceRecord], translation_id: str) -> dict[str, Any]:
    records_by_book: dict[str, list[SourceRecord]] = defaultdict(list)
    for record in records:
        records_by_book[record.book_code].append(record)

    book_summaries: list[dict[str, Any]] = []
    corpus_marker_counts: dict[str, Counter[str]] = defaultdict(empty_counts)
    corpus_totals = empty_counts()
    corpus_record_count = 0
    corpus_records_with_character_style = 0

    for book_code in BOOK_ORDER:
        book_records = records_by_book.get(book_code)
        if not book_records:
            continue
        summary = summarize_records(book_records)
        summary["book_code"] = book_code
        book_summaries.append(summary)
        corpus_record_count += summary["record_count"]
        corpus_records_with_character_style += summary["records_with_character_style"]
        add_counts(corpus_totals, summary["character_style"])
        for row in summary["markers"]:
            add_counts(corpus_marker_counts[row["marker"]], row)

    corpus_totals["record_count"] = corpus_records_with_character_style
    books_with_character_style = [
        {
            "book_code": book["book_code"],
            "record_count": book["record_count"],
            "records_with_character_style": book["records_with_character_style"],
            **book["character_style"],
        }
        for book in book_summaries
        if book["character_style"]["line_count"]
    ]

    return {
        "translation_id": translation_id,
        "book_count": len(book_summaries),
        "record_count": corpus_record_count,
        "records_with_character_style": corpus_records_with_character_style,
        "character_style": finalize_counts(corpus_totals),
        "markers": marker_rows(corpus_marker_counts),
        "books_with_character_style": books_with_character_style,
        "focus_books": [book for book in book_summaries if book["book_code"] in FOCUS_BOOKS],
    }


def rows_by_name(rows: Sequence[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {str(row[key]): row for row in rows}


def compare_count_rows(asv: dict[str, Any], webp: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in COUNT_KEYS:
        asv_value = int(asv.get(key, 0))
        webp_value = int(webp.get(key, 0))
        result[f"asv_{key}"] = asv_value
        result[f"webp_{key}"] = webp_value
        result[f"{key}_delta"] = webp_value - asv_value
        result[f"{key}_ratio_ppm"] = ratio_ppm(webp_value, asv_value)
    return result


def compare_marker_rows(
    asv_rows: Sequence[dict[str, Any]], webp_rows: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    asv = rows_by_name(asv_rows, "marker")
    webp = rows_by_name(webp_rows, "marker")
    markers = sorted(set(asv) | set(webp))
    rows = []
    for marker in markers:
        row = {"marker": marker}
        row.update(compare_count_rows(asv.get(marker, {}), webp.get(marker, {})))
        rows.append(row)
    return sorted(rows, key=lambda row: (-row["visible_token_count_delta"], row["marker"]))


def compare_focus_books(asv: dict[str, Any], webp: dict[str, Any]) -> list[dict[str, Any]]:
    asv_books = rows_by_name(asv["focus_books"], "book_code")
    webp_books = rows_by_name(webp["focus_books"], "book_code")
    rows = []
    for book_code in FOCUS_BOOKS:
        asv_book = asv_books.get(book_code, {"character_style": {}, "markers": []})
        webp_book = webp_books.get(book_code, {"character_style": {}, "markers": []})
        row: dict[str, Any] = {"book_code": book_code}
        row.update(compare_count_rows(asv_book["character_style"], webp_book["character_style"]))
        row["marker_comparisons"] = compare_marker_rows(asv_book["markers"], webp_book["markers"])
        rows.append(row)
    return rows


def compact_translation(analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "translation_id": analysis["translation_id"],
        "book_count": analysis["book_count"],
        "record_count": analysis["record_count"],
        "records_with_character_style": analysis["records_with_character_style"],
        "character_style": analysis["character_style"],
        "markers": analysis["markers"],
        "books_with_character_style": analysis["books_with_character_style"],
    }


def summarize_comparison(asv: dict[str, Any], webp: dict[str, Any]) -> dict[str, Any]:
    return {
        "diagnostic_contract": "character-marker-same-record-accounting-v1",
        "focus_books": list(FOCUS_BOOKS),
        "gospel_books": list(GOSPEL_BOOKS),
        "control_books": list(CONTROL_BOOKS),
        "duplicate_definition": "normalized nonempty character-style leading-line tokens occur contiguously in another nonempty line of the same adapter record",
        "exact_duplicate_definition": "normalized nonempty character-style leading-line tokens exactly equal another nonempty line of the same adapter record",
        "asv": compact_translation(asv),
        "webp": compact_translation(webp),
        "corpus_marker_comparisons": compare_marker_rows(asv["markers"], webp["markers"]),
        "focus_book_comparisons": compare_focus_books(asv, webp),
        "scripture_text_reported": False,
        "token_lists_reported": False,
        "locator_identifiers_reported": False,
        "per_locator_text_digests_reported": False,
        "text_boundaries_defined": False,
        "corpus_mutation": "not-performed",
        "mapping_authority": "none",
        "execution_eligible": False,
        "publication_eligible": False,
    }


def assert_expected(observed: dict[str, Any], expected: dict[str, Any]) -> None:
    if observed != expected:
        observed_rendered = json.dumps(observed, sort_keys=True, separators=(",", ":"))
        expected_rendered = json.dumps(expected, sort_keys=True, separators=(",", ":"))
        raise ValueError(
            "ASV/WEBP character marker accounting mismatch: "
            f"expected {len(expected_rendered)} canonical bytes, "
            f"observed {len(observed_rendered)} canonical bytes"
        )


def run(expected_path: Path | None = None) -> dict[str, Any]:
    asv_target = load_json(ASV_TARGET_PATH)
    asv_artifact = load_json(ASV_ARTIFACT_PATH)
    webp_target = load_json(WEBP_TARGET_PATH)
    webp_artifact = load_json(WEBP_ARTIFACT_PATH)

    with tempfile.TemporaryDirectory(prefix="bible-os-character-marker-") as temp_dir:
        temp_root = Path(temp_dir)
        asv_archive_path = temp_root / asv_artifact["filename"]
        webp_archive_path = temp_root / webp_artifact["filename"]
        download_verified_archive(asv_target, asv_archive_path)
        download_verified_archive(webp_target, webp_archive_path)
        with zipfile.ZipFile(asv_archive_path) as archive:
            asv = analyze_translation(AsvUsfmAdapter().iter_records(archive), "eng-asv")
        with zipfile.ZipFile(webp_archive_path) as archive:
            webp = analyze_translation(WebpUsfmAdapter().iter_records(archive), "eng-webp")

    comparison = summarize_comparison(asv, webp)
    if expected_path is None:
        profile_status = "observed-unpinned"
    else:
        assert_expected(comparison, load_json(expected_path))
        profile_status = "matched"

    return {
        "status": "passed",
        "experiment": "asv-webp-character-marker-accounting-v1",
        "asv_artifact_sha256": asv_artifact["sha256"],
        "webp_artifact_sha256": webp_artifact["sha256"],
        "comparison": comparison,
        "profile_status": profile_status,
        "expected_profile": str(expected_path) if expected_path is not None else None,
        "corpus_bytes_committed": False,
        "scripture_text_reported": False,
        "token_lists_reported": False,
        "locator_identifiers_reported": False,
        "per_locator_text_digests_reported": False,
        "text_boundaries_defined": False,
        "mapping_authority": "none",
        "execution_eligible": False,
        "publication_eligible": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Attribute ASV/WEBP character-style marker counts without reporting scripture text"
    )
    parser.add_argument("--expected", type=Path)
    parser.add_argument(
        "--report", type=Path, default=Path("asv-webp-character-marker-accounting-report.json")
    )
    args = parser.parse_args(argv)

    report = run(args.expected)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
