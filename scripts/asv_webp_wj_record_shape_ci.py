from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence
from zipfile import ZipFile

from bible_os.importers.webp_usfm import (
    BOOK_ORDER,
    CHAPTER_RE,
    VERSE_RE,
    WebpUsfmAdapter,
    extract_visible_text,
)
from scripts.asv_adapter_smoke import AsvUsfmAdapter
from scripts.asv_full_ci import ARTIFACT_PATH as ASV_ARTIFACT_PATH
from scripts.asv_full_ci import TARGET_PATH as ASV_TARGET_PATH
from scripts.asv_webp_gospel_structure_ci import (
    leading_marker,
    marker_root,
    ratio_ppm,
    source_documents,
)
from scripts.asv_webp_lexical_fingerprint_ci import normalize_tokens
from scripts.webp_adapter_smoke import download_verified_archive, load_json
from scripts.webp_db_load import ARTIFACT_PATH as WEBP_ARTIFACT_PATH
from scripts.webp_db_load import TARGET_PATH as WEBP_TARGET_PATH


FOCUS_BOOKS = ("MAT", "MRK", "LUK", "JHN", "ACT", "ROM", "REV")
COUNT_KEYS = (
    "record_count",
    "source_position_token_count",
    "adapter_visible_token_count",
    "token_reconciliation_delta",
    "opening_line_count",
    "opening_nonempty_line_count",
    "opening_zero_token_line_count",
    "opening_visible_token_count",
    "opening_wj_line_count",
    "opening_wj_zero_token_line_count",
    "opening_wj_visible_token_count",
    "opening_add_line_count",
    "opening_add_zero_token_line_count",
    "opening_add_visible_token_count",
    "opening_other_marker_line_count",
    "opening_other_marker_zero_token_line_count",
    "opening_other_marker_visible_token_count",
    "opening_unmarked_line_count",
    "opening_unmarked_zero_token_line_count",
    "opening_unmarked_visible_token_count",
    "subsequent_line_count",
    "subsequent_zero_token_line_count",
    "subsequent_visible_token_count",
    "subsequent_wj_line_count",
    "subsequent_wj_zero_token_line_count",
    "subsequent_wj_visible_token_count",
    "subsequent_unmarked_line_count",
    "subsequent_unmarked_visible_token_count",
    "subsequent_other_marker_line_count",
    "subsequent_other_marker_visible_token_count",
    "records_with_opening_wj",
    "records_with_opening_wj_and_subsequent_lines",
    "records_with_opening_wj_and_visible_subsequent_tokens",
    "opening_wj_record_opening_visible_token_count",
    "opening_wj_record_subsequent_visible_token_count",
    "opening_wj_record_adapter_visible_token_count",
)
SHAPE_ORDER = (
    "empty",
    "empty-plus-later",
    "opening-unmarked-only",
    "opening-unmarked-plus-later",
    "opening-wj-only",
    "opening-wj-plus-later",
    "opening-add-only",
    "opening-add-plus-later",
    "opening-other-marker-only",
    "opening-other-marker-plus-later",
)
OPENING_CLASSES = ("empty", "unmarked", "wj", "add", "other-marker")


@dataclass(frozen=True, slots=True)
class SourceShapeRecord:
    opening_payload: str
    subsequent_lines: tuple[str, ...]


def visible_tokens(value: str) -> tuple[str, ...]:
    return tuple(normalize_tokens(extract_visible_text(value)))


def iter_source_shape_records(text: str) -> Iterable[SourceShapeRecord]:
    opening_payload: str | None = None
    subsequent_lines: list[str] = []

    def flush() -> SourceShapeRecord | None:
        nonlocal opening_payload, subsequent_lines
        if opening_payload is None:
            return None
        record = SourceShapeRecord(
            opening_payload=opening_payload,
            subsequent_lines=tuple(subsequent_lines),
        )
        opening_payload = None
        subsequent_lines = []
        return record

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if CHAPTER_RE.match(stripped):
            pending = flush()
            if pending is not None:
                yield pending
            continue

        verse_match = VERSE_RE.match(stripped)
        if verse_match:
            pending = flush()
            if pending is not None:
                yield pending
            opening_payload = verse_match.group("payload") or ""
            subsequent_lines = []
            continue

        if opening_payload is not None:
            subsequent_lines.append(raw_line.rstrip("\r\n"))

    pending = flush()
    if pending is not None:
        yield pending


def classify_opening_payload(payload: str) -> str:
    stripped = payload.strip()
    if not stripped:
        return "empty"
    marker = leading_marker(stripped)
    if marker is None:
        return "unmarked"
    root = marker_root(marker)
    if root == "wj":
        return "wj"
    if root == "add":
        return "add"
    return "other-marker"


def classify_subsequent_line(line: str) -> str:
    marker = leading_marker(line.strip())
    if marker is None:
        return "unmarked"
    if marker_root(marker) == "wj":
        return "wj"
    return "other-marker"


def record_shape(opening_class: str, has_later_source_line: bool) -> str:
    if opening_class not in OPENING_CLASSES:
        raise ValueError(f"unsupported opening class: {opening_class}")
    if opening_class == "empty":
        return "empty-plus-later" if has_later_source_line else "empty"
    suffix = "plus-later" if has_later_source_line else "only"
    return f"opening-{opening_class}-{suffix}"


def empty_counts() -> Counter[str]:
    return Counter({key: 0 for key in COUNT_KEYS})


def add_counts(target: Counter[str], source: dict[str, Any] | Counter[str]) -> None:
    for key in COUNT_KEYS:
        target[key] += int(source.get(key, 0))


def histogram_rows(counter: Counter[int]) -> list[dict[str, int]]:
    return [
        {"line_count": line_count, "record_count": counter[line_count]}
        for line_count in sorted(counter)
    ]


def shape_rows(counter: Counter[str]) -> list[dict[str, Any]]:
    return [
        {"shape": shape, "record_count": counter.get(shape, 0)}
        for shape in SHAPE_ORDER
        if counter.get(shape, 0)
    ]


def finalize_counts(counts: dict[str, Any] | Counter[str]) -> dict[str, int]:
    result = {key: int(counts.get(key, 0)) for key in COUNT_KEYS}
    denominator = result["opening_wj_record_adapter_visible_token_count"]
    result["opening_wj_record_opening_token_share_ppm"] = ratio_ppm(
        result["opening_wj_record_opening_visible_token_count"], denominator
    )
    result["opening_wj_record_subsequent_token_share_ppm"] = ratio_ppm(
        result["opening_wj_record_subsequent_visible_token_count"], denominator
    )
    result["source_position_to_adapter_token_ratio_ppm"] = ratio_ppm(
        result["source_position_token_count"], result["adapter_visible_token_count"]
    )
    return result


def summarize_shape_records(
    records: Sequence[SourceShapeRecord],
    *,
    adapter_records: Sequence[Any] | None = None,
) -> dict[str, Any]:
    if adapter_records is not None and len(records) != len(adapter_records):
        raise ValueError("source/adapter record count mismatch")

    counts = empty_counts()
    shapes: Counter[str] = Counter()
    later_line_histogram_for_opening_wj: Counter[int] = Counter()

    for record_index, record in enumerate(records):
        opening_tokens = visible_tokens(record.opening_payload)
        opening_class = classify_opening_payload(record.opening_payload)
        subsequent_token_count = 0
        has_later_source_line = False

        counts["record_count"] += 1
        counts["opening_line_count"] += 1
        counts["opening_visible_token_count"] += len(opening_tokens)
        if opening_tokens:
            counts["opening_nonempty_line_count"] += 1
        else:
            counts["opening_zero_token_line_count"] += 1

        class_prefix = f"opening_{opening_class.replace('-', '_')}"
        if opening_class != "empty":
            counts[f"{class_prefix}_line_count"] += 1
            counts[f"{class_prefix}_visible_token_count"] += len(opening_tokens)
            if not opening_tokens:
                counts[f"{class_prefix}_zero_token_line_count"] += 1

        for line in record.subsequent_lines:
            classification = classify_subsequent_line(line)
            tokens = visible_tokens(line)
            counts["subsequent_line_count"] += 1
            counts["subsequent_visible_token_count"] += len(tokens)
            subsequent_token_count += len(tokens)
            has_later_source_line = has_later_source_line or bool(line.strip())
            if not tokens:
                counts["subsequent_zero_token_line_count"] += 1

            if classification == "wj":
                counts["subsequent_wj_line_count"] += 1
                counts["subsequent_wj_visible_token_count"] += len(tokens)
                if not tokens:
                    counts["subsequent_wj_zero_token_line_count"] += 1
            elif classification == "unmarked":
                counts["subsequent_unmarked_line_count"] += 1
                counts["subsequent_unmarked_visible_token_count"] += len(tokens)
            else:
                counts["subsequent_other_marker_line_count"] += 1
                counts["subsequent_other_marker_visible_token_count"] += len(tokens)

        shapes[record_shape(opening_class, has_later_source_line)] += 1

        if adapter_records is None:
            reconstructed_payload = "\n".join(
                (record.opening_payload, *record.subsequent_lines)
            )
            record_adapter_tokens = len(visible_tokens(reconstructed_payload))
        else:
            record_adapter_tokens = len(
                visible_tokens(adapter_records[record_index].raw_payload)
            )

        counts["source_position_token_count"] += (
            len(opening_tokens) + subsequent_token_count
        )
        counts["adapter_visible_token_count"] += record_adapter_tokens

        if opening_class == "wj":
            counts["records_with_opening_wj"] += 1
            if has_later_source_line:
                counts["records_with_opening_wj_and_subsequent_lines"] += 1
            if subsequent_token_count:
                counts[
                    "records_with_opening_wj_and_visible_subsequent_tokens"
                ] += 1
            counts[
                "opening_wj_record_opening_visible_token_count"
            ] += len(opening_tokens)
            counts[
                "opening_wj_record_subsequent_visible_token_count"
            ] += subsequent_token_count
            counts[
                "opening_wj_record_adapter_visible_token_count"
            ] += record_adapter_tokens
            later_line_histogram_for_opening_wj[len(record.subsequent_lines)] += 1

    counts["token_reconciliation_delta"] = (
        counts["source_position_token_count"]
        - counts["adapter_visible_token_count"]
    )

    return {
        **finalize_counts(counts),
        "record_shapes": shape_rows(shapes),
        "subsequent_lines_per_opening_wj_record": histogram_rows(
            later_line_histogram_for_opening_wj
        ),
    }


def analyze_archive(
    archive: ZipFile,
    adapter: WebpUsfmAdapter,
    translation_id: str,
) -> dict[str, Any]:
    documents = source_documents(archive)
    source_records_by_book: dict[str, list[SourceShapeRecord]] = defaultdict(list)
    for book_code, document in documents.items():
        source_records_by_book[book_code].extend(
            iter_source_shape_records(document["text"])
        )

    adapter_records_by_book: dict[str, list[Any]] = defaultdict(list)
    for record in adapter.iter_records(archive):
        adapter_records_by_book[record.book_code].append(record)

    book_summaries: list[dict[str, Any]] = []
    corpus_counts = empty_counts()
    corpus_shapes: Counter[str] = Counter()
    corpus_opening_wj_later_histogram: Counter[int] = Counter()

    for book_code in BOOK_ORDER:
        source_records = source_records_by_book.get(book_code)
        adapter_records = adapter_records_by_book.get(book_code)
        if not source_records and not adapter_records:
            continue
        if len(source_records or ()) != len(adapter_records or ()):
            raise ValueError(
                f"source/adapter record count mismatch for {translation_id} {book_code}"
            )

        summary = summarize_shape_records(
            source_records or (),
            adapter_records=adapter_records or (),
        )
        summary["book_code"] = book_code
        book_summaries.append(summary)
        add_counts(corpus_counts, summary)
        for row in summary["record_shapes"]:
            corpus_shapes[row["shape"]] += int(row["record_count"])
        for row in summary["subsequent_lines_per_opening_wj_record"]:
            corpus_opening_wj_later_histogram[int(row["line_count"])] += int(
                row["record_count"]
            )

    corpus_counts["token_reconciliation_delta"] = (
        corpus_counts["source_position_token_count"]
        - corpus_counts["adapter_visible_token_count"]
    )
    corpus = {
        **finalize_counts(corpus_counts),
        "record_shapes": shape_rows(corpus_shapes),
        "subsequent_lines_per_opening_wj_record": histogram_rows(
            corpus_opening_wj_later_histogram
        ),
    }

    return {
        "translation_id": translation_id,
        "book_count": len(book_summaries),
        "corpus": corpus,
        "books": book_summaries,
        "books_with_opening_wj": [
            book for book in book_summaries if book["records_with_opening_wj"]
        ],
        "books_with_opening_add": [
            book for book in book_summaries if book["opening_add_line_count"]
        ],
    }


def rows_by_book(analysis: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["book_code"]: row for row in analysis["books"]}


def compact_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        **{key: int(summary.get(key, 0)) for key in COUNT_KEYS},
        "opening_wj_record_opening_token_share_ppm": int(
            summary.get("opening_wj_record_opening_token_share_ppm", 0)
        ),
        "opening_wj_record_subsequent_token_share_ppm": int(
            summary.get("opening_wj_record_subsequent_token_share_ppm", 0)
        ),
        "source_position_to_adapter_token_ratio_ppm": int(
            summary.get("source_position_to_adapter_token_ratio_ppm", 0)
        ),
        "record_shapes": summary.get("record_shapes", []),
        "subsequent_lines_per_opening_wj_record": summary.get(
            "subsequent_lines_per_opening_wj_record", []
        ),
    }


def compare_focus_books(
    asv: dict[str, Any], webp: dict[str, Any]
) -> list[dict[str, Any]]:
    asv_books = rows_by_book(asv)
    webp_books = rows_by_book(webp)
    return [
        {
            "book_code": book_code,
            "asv": compact_summary(asv_books.get(book_code, {})),
            "webp": compact_summary(webp_books.get(book_code, {})),
        }
        for book_code in FOCUS_BOOKS
    ]


def compact_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "translation_id": analysis["translation_id"],
        "book_count": analysis["book_count"],
        "corpus": compact_summary(analysis["corpus"]),
        "books_with_opening_wj": [
            {"book_code": row["book_code"], **compact_summary(row)}
            for row in analysis["books_with_opening_wj"]
        ],
        "books_with_opening_add": [
            {"book_code": row["book_code"], **compact_summary(row)}
            for row in analysis["books_with_opening_add"]
        ],
    }


def summarize_comparison(
    asv: dict[str, Any], webp: dict[str, Any]
) -> dict[str, Any]:
    return {
        "diagnostic_contract": "source-verse-opening-marker-accounting-v2",
        "focus_books": list(FOCUS_BOOKS),
        "verse_opening_definition": (
            "the optional source payload carried on the same USFM line as the verse marker"
        ),
        "opening_wj_definition": (
            "a verse-opening payload whose exact leading marker root is wj"
        ),
        "opening_add_definition": (
            "a verse-opening payload whose exact leading marker root is add"
        ),
        "subsequent_line_definition": (
            "source lines after a verse marker and before the next verse or chapter marker"
        ),
        "token_reconciliation_definition": (
            "source-position visible-token sum minus adapter raw-payload visible-token count"
        ),
        "asv": compact_analysis(asv),
        "webp": compact_analysis(webp),
        "focus_book_comparisons": compare_focus_books(asv, webp),
        "scripture_text_reported": False,
        "token_lists_reported": False,
        "locator_identifiers_reported": False,
        "per_locator_text_digests_reported": False,
        "text_boundaries_defined": False,
        "parser_behavior_changed": False,
        "corpus_mutation": "not-performed",
        "mapping_authority": "none",
        "execution_eligible": False,
        "publication_eligible": False,
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
            "ASV/WEBP wj record-shape accounting mismatch: "
            f"expected {len(expected_rendered)} canonical bytes, "
            f"observed {len(observed_rendered)} canonical bytes"
        )


def run(expected_path: Path | None = None) -> dict[str, Any]:
    asv_target = load_json(ASV_TARGET_PATH)
    asv_artifact = load_json(ASV_ARTIFACT_PATH)
    webp_target = load_json(WEBP_TARGET_PATH)
    webp_artifact = load_json(WEBP_ARTIFACT_PATH)

    with tempfile.TemporaryDirectory(prefix="bible-os-wj-record-shape-") as temp_dir:
        temp_root = Path(temp_dir)
        asv_archive_path = temp_root / asv_artifact["filename"]
        webp_archive_path = temp_root / webp_artifact["filename"]
        download_verified_archive(asv_target, asv_archive_path)
        download_verified_archive(webp_target, webp_archive_path)
        with zipfile.ZipFile(asv_archive_path) as archive:
            asv = analyze_archive(archive, AsvUsfmAdapter(), "eng-asv")
        with zipfile.ZipFile(webp_archive_path) as archive:
            webp = analyze_archive(archive, WebpUsfmAdapter(), "eng-webp")

    comparison = summarize_comparison(asv, webp)
    if expected_path is None:
        profile_status = "observed-unpinned"
    else:
        assert_expected(comparison, load_json(expected_path))
        profile_status = "matched"

    return {
        "status": "passed",
        "experiment": "asv-webp-wj-record-shape-v2",
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
        "parser_behavior_changed": False,
        "mapping_authority": "none",
        "execution_eligible": False,
        "publication_eligible": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Measure source verse-opening wj marker shape without reporting scripture text"
        )
    )
    parser.add_argument("--expected", type=Path)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("asv-webp-wj-record-shape-report.json"),
    )
    args = parser.parse_args(argv)

    report = run(args.expected)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
