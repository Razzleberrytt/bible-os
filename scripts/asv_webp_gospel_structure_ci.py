from __future__ import annotations

import argparse
import json
import re
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

from bible_os.importers.base import SourceRecord
from bible_os.importers.webp_usfm import (
    BOOK_INDEX,
    BOOK_ORDER,
    ID_RE,
    MARKER_RE,
    WebpUsfmAdapter,
    extract_visible_text,
)
from scripts.asv_adapter_smoke import AsvUsfmAdapter
from scripts.asv_full_ci import ARTIFACT_PATH as ASV_ARTIFACT_PATH
from scripts.asv_full_ci import TARGET_PATH as ASV_TARGET_PATH
from scripts.asv_webp_lexical_fingerprint_ci import normalize_tokens
from scripts.webp_adapter_smoke import download_verified_archive, load_json
from scripts.webp_db_load import ARTIFACT_PATH as WEBP_ARTIFACT_PATH
from scripts.webp_db_load import TARGET_PATH as WEBP_TARGET_PATH


ROOT = Path(__file__).resolve().parents[1]
FOCUS_BOOKS = ("MAT", "MRK", "LUK", "JHN", "ACT", "ROM")
GOSPEL_BOOKS = ("MAT", "MRK", "LUK", "JHN")
CONTROL_BOOKS = ("ACT", "ROM")
PPM = 1_000_000
LEADING_MARKER_RE = re.compile(r"^\\(?P<marker>[a-z0-9][a-z0-9-]*)(?:\*|\b)", re.I)
TRAILING_DIGITS_RE = re.compile(r"[0-9]+$")
MARKER_CLASS_ORDER = (
    "chapter-verse",
    "note-cross-reference",
    "word-attribute",
    "character-style",
    "heading-title",
    "paragraph-poetry-list",
    "milestone",
    "metadata",
    "other",
)

NOTE_MARKERS = {
    "f", "fe", "ef", "ex", "fr", "fk", "fq", "fqa", "fl", "fw", "fp",
    "ft", "fv", "fdc", "fm", "x", "xo", "xk", "xq", "xt", "xta", "xop",
    "xot", "xnt", "xdc",
}
WORD_ATTRIBUTE_MARKERS = {"w", "wg", "wh", "wa"}
CHARACTER_STYLE_MARKERS = {
    "add", "bk", "dc", "k", "litl", "nd", "ord", "pn", "png", "qac", "qs",
    "qt", "rq", "sig", "sls", "tl", "wj", "em", "bd", "bdit", "it", "no",
    "sc", "sup", "pro",
}
HEADING_MARKERS = {
    "mt", "mte", "ms", "mr", "s", "sr", "r", "d", "sp", "cl", "cd", "qa",
    "qc", "qr", "sd", "sts",
}
PARAGRAPH_MARKERS = {
    "p", "m", "po", "pr", "cls", "pmo", "pm", "pmc", "pmr", "pi", "mi",
    "nb", "pc", "ph", "q", "qm", "b", "lh", "li", "lf", "lim", "litl",
    "tr", "th", "thr", "tc", "tcr",
}
METADATA_MARKERS = {
    "id", "ide", "usfm", "h", "toc", "toca", "rem", "restore", "periph",
    "jmp", "fig", "cat", "ca", "cp", "va", "vp",
}


def marker_root(marker: str) -> str:
    return TRAILING_DIGITS_RE.sub("", marker.casefold().rstrip("*"))


def marker_class(marker: str) -> str:
    name = marker.casefold().rstrip("*")
    root = marker_root(name)
    if root in {"c", "v"}:
        return "chapter-verse"
    if root in NOTE_MARKERS:
        return "note-cross-reference"
    if root in WORD_ATTRIBUTE_MARKERS:
        return "word-attribute"
    if name.endswith("-s") or name.endswith("-e"):
        return "milestone"
    if root in CHARACTER_STYLE_MARKERS:
        return "character-style"
    if root in HEADING_MARKERS:
        return "heading-title"
    if root in PARAGRAPH_MARKERS:
        return "paragraph-poetry-list"
    if root in METADATA_MARKERS:
        return "metadata"
    return "other"


def leading_marker(line: str) -> str | None:
    match = LEADING_MARKER_RE.match(line.strip())
    return match.group("marker").casefold() if match else None


def ratio_ppm(numerator: int, denominator: int) -> int:
    if numerator < 0 or denominator < 0:
        raise ValueError("ratio inputs must be nonnegative")
    if denominator == 0:
        return 0 if numerator == 0 else numerator * PPM
    return (numerator * PPM + denominator // 2) // denominator


def per_thousand(numerator: int, denominator: int) -> int:
    if numerator < 0 or denominator < 0:
        raise ValueError("rate inputs must be nonnegative")
    if denominator == 0:
        return 0
    return (numerator * 1_000 + denominator // 2) // denominator


def counter_rows(counter: Counter[str], order: Iterable[str] | None = None) -> list[dict[str, Any]]:
    names = list(order) if order is not None else sorted(counter)
    return [{"name": name, "count": counter[name]} for name in names if counter[name]]


def top_counter_rows(counter: Counter[str], limit: int = 20) -> list[dict[str, Any]]:
    return [
        {"name": name, "count": count}
        for name, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def source_documents(archive: zipfile.ZipFile) -> dict[str, dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    members = sorted(
        (
            member
            for member in archive.infolist()
            if not member.is_dir() and Path(member.filename).suffix.casefold() in {".usfm", ".sfm"}
        ),
        key=lambda member: member.filename,
    )
    for member in members:
        payload = archive.read(member)
        text = payload.decode("utf-8-sig")
        book_code = ""
        for line in text.splitlines():
            match = ID_RE.match(line.strip())
            if match:
                book_code = match.group("book")
                break
        if not book_code:
            raise ValueError(f"USFM file has no id marker: {member.filename}")
        if book_code in documents:
            raise ValueError(f"duplicate USFM book id: {book_code}")
        if book_code not in BOOK_INDEX:
            continue
        documents[book_code] = {
            "source_file": member.filename,
            "source_bytes": member.file_size,
            "compressed_bytes": member.compress_size,
            "crc32": f"{member.CRC:08x}",
            "text": text,
        }
    return documents


def analyze_book_document(document: dict[str, Any]) -> dict[str, Any]:
    lines = document["text"].splitlines()
    markers: Counter[str] = Counter()
    classes: Counter[str] = Counter()
    leading_nonempty = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        marker = leading_marker(stripped)
        if marker is not None:
            leading_nonempty += 1
        for match in MARKER_RE.finditer(stripped):
            name = match.group(0)[1:].rstrip("*").casefold()
            markers[name] += 1
            classes[marker_class(name)] += 1
    return {
        "source_file": document["source_file"],
        "source_bytes": document["source_bytes"],
        "compressed_bytes": document["compressed_bytes"],
        "crc32": document["crc32"],
        "source_line_count": len(lines),
        "source_nonempty_line_count": sum(bool(line.strip()) for line in lines),
        "source_leading_marker_line_count": leading_nonempty,
        "source_marker_count": sum(markers.values()),
        "source_marker_class_counts": counter_rows(classes, MARKER_CLASS_ORDER),
        "top_source_markers": top_counter_rows(markers),
    }


def analyze_book_records(records: Sequence[SourceRecord]) -> dict[str, Any]:
    payload_markers: Counter[str] = Counter()
    payload_classes: Counter[str] = Counter()
    leading_marker_lines: Counter[str] = Counter()
    leading_class_lines: Counter[str] = Counter()
    leading_class_line_local_tokens: Counter[str] = Counter()

    payload_bytes = 0
    payload_line_count = 0
    payload_nonempty_line_count = 0
    unmarked_payload_line_count = 0
    unmarked_line_local_token_count = 0
    visible_token_count = 0
    text_record_count = 0
    empty_record_count = 0

    for record in records:
        payload_bytes += len(record.raw_payload.encode("utf-8"))
        lines = record.raw_payload.splitlines()
        payload_line_count += len(lines)
        visible_tokens = normalize_tokens(extract_visible_text(record.raw_payload))
        visible_token_count += len(visible_tokens)
        if visible_tokens:
            text_record_count += 1
        else:
            empty_record_count += 1

        for match in MARKER_RE.finditer(record.raw_payload):
            name = match.group(0)[1:].rstrip("*").casefold()
            payload_markers[name] += 1
            payload_classes[marker_class(name)] += 1

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            payload_nonempty_line_count += 1
            line_tokens = len(normalize_tokens(extract_visible_text(stripped)))
            marker = leading_marker(stripped)
            if marker is None:
                unmarked_payload_line_count += 1
                unmarked_line_local_token_count += line_tokens
                continue
            category = marker_class(marker)
            leading_marker_lines[marker] += 1
            leading_class_lines[category] += 1
            leading_class_line_local_tokens[category] += line_tokens

    return {
        "record_count": len(records),
        "text_record_count": text_record_count,
        "empty_record_count": empty_record_count,
        "payload_bytes": payload_bytes,
        "payload_line_count": payload_line_count,
        "payload_nonempty_line_count": payload_nonempty_line_count,
        "unmarked_payload_line_count": unmarked_payload_line_count,
        "unmarked_line_local_token_count": unmarked_line_local_token_count,
        "visible_token_count": visible_token_count,
        "tokens_per_record_milli": per_thousand(visible_token_count, len(records)),
        "payload_marker_count": sum(payload_markers.values()),
        "payload_marker_class_counts": counter_rows(payload_classes, MARKER_CLASS_ORDER),
        "leading_marker_line_count": sum(leading_marker_lines.values()),
        "leading_marker_class_line_counts": counter_rows(leading_class_lines, MARKER_CLASS_ORDER),
        "leading_marker_class_line_local_token_counts": counter_rows(
            leading_class_line_local_tokens, MARKER_CLASS_ORDER
        ),
        "top_payload_markers": top_counter_rows(payload_markers),
        "top_leading_payload_markers": top_counter_rows(leading_marker_lines),
    }


def analyze_translation(
    archive: zipfile.ZipFile,
    adapter: AsvUsfmAdapter | WebpUsfmAdapter,
    translation_id: str,
) -> dict[str, Any]:
    documents = source_documents(archive)
    records_by_book: dict[str, list[SourceRecord]] = defaultdict(list)
    for record in adapter.iter_records(archive):
        records_by_book[record.book_code].append(record)

    missing_documents = sorted(set(records_by_book) - set(documents), key=BOOK_INDEX.get)
    if missing_documents:
        raise ValueError(f"records have no source document: {missing_documents}")

    books: list[dict[str, Any]] = []
    for book_code in BOOK_ORDER:
        document = documents.get(book_code)
        if document is None:
            continue
        book = {"book_code": book_code}
        book.update(analyze_book_document(document))
        book.update(analyze_book_records(records_by_book.get(book_code, [])))
        books.append(book)

    return {
        "translation_id": translation_id,
        "book_count": len(books),
        "source_file_count": len(documents),
        "source_bytes": sum(book["source_bytes"] for book in books),
        "compressed_bytes": sum(book["compressed_bytes"] for book in books),
        "source_line_count": sum(book["source_line_count"] for book in books),
        "record_count": sum(book["record_count"] for book in books),
        "text_record_count": sum(book["text_record_count"] for book in books),
        "empty_record_count": sum(book["empty_record_count"] for book in books),
        "payload_line_count": sum(book["payload_line_count"] for book in books),
        "payload_marker_count": sum(book["payload_marker_count"] for book in books),
        "visible_token_count": sum(book["visible_token_count"] for book in books),
        "books": books,
    }


def rows_to_counter(rows: Sequence[dict[str, Any]]) -> Counter[str]:
    return Counter({row["name"]: row["count"] for row in rows})


def compare_marker_rows(
    asv_rows: Sequence[dict[str, Any]], webp_rows: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    asv = rows_to_counter(asv_rows)
    webp = rows_to_counter(webp_rows)
    names = list(MARKER_CLASS_ORDER)
    return [
        {
            "name": name,
            "asv_count": asv[name],
            "webp_count": webp[name],
            "delta": webp[name] - asv[name],
            "webp_to_asv_ratio_ppm": ratio_ppm(webp[name], asv[name]),
        }
        for name in names
        if asv[name] or webp[name]
    ]


def compact_book(book: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "book_code",
        "source_file",
        "source_bytes",
        "compressed_bytes",
        "crc32",
        "source_line_count",
        "source_marker_count",
        "record_count",
        "text_record_count",
        "empty_record_count",
        "payload_bytes",
        "payload_line_count",
        "payload_nonempty_line_count",
        "unmarked_payload_line_count",
        "unmarked_line_local_token_count",
        "visible_token_count",
        "tokens_per_record_milli",
        "payload_marker_count",
        "leading_marker_line_count",
        "source_marker_class_counts",
        "payload_marker_class_counts",
        "leading_marker_class_line_counts",
        "leading_marker_class_line_local_token_counts",
        "top_payload_markers",
        "top_leading_payload_markers",
    )
    return {key: book[key] for key in keys}


def compare_book(asv: dict[str, Any], webp: dict[str, Any]) -> dict[str, Any]:
    if asv["book_code"] != webp["book_code"]:
        raise ValueError("book comparison requires matching book codes")
    return {
        "book_code": asv["book_code"],
        "asv": compact_book(asv),
        "webp": compact_book(webp),
        "visible_token_delta": webp["visible_token_count"] - asv["visible_token_count"],
        "visible_token_ratio_ppm": ratio_ppm(
            webp["visible_token_count"], asv["visible_token_count"]
        ),
        "source_byte_ratio_ppm": ratio_ppm(webp["source_bytes"], asv["source_bytes"]),
        "source_line_ratio_ppm": ratio_ppm(
            webp["source_line_count"], asv["source_line_count"]
        ),
        "payload_line_ratio_ppm": ratio_ppm(
            webp["payload_line_count"], asv["payload_line_count"]
        ),
        "record_ratio_ppm": ratio_ppm(webp["record_count"], asv["record_count"]),
        "tokens_per_record_ratio_ppm": ratio_ppm(
            webp["tokens_per_record_milli"], asv["tokens_per_record_milli"]
        ),
        "payload_marker_ratio_ppm": ratio_ppm(
            webp["payload_marker_count"], asv["payload_marker_count"]
        ),
        "payload_marker_class_comparison": compare_marker_rows(
            asv["payload_marker_class_counts"], webp["payload_marker_class_counts"]
        ),
        "leading_marker_line_class_comparison": compare_marker_rows(
            asv["leading_marker_class_line_counts"],
            webp["leading_marker_class_line_counts"],
        ),
        "leading_marker_line_local_token_class_comparison": compare_marker_rows(
            asv["leading_marker_class_line_local_token_counts"],
            webp["leading_marker_class_line_local_token_counts"],
        ),
    }


def summarize_comparison(
    asv: dict[str, Any], webp: dict[str, Any]
) -> dict[str, Any]:
    asv_books = {book["book_code"]: book for book in asv["books"]}
    webp_books = {book["book_code"]: book for book in webp["books"]}
    shared = [book for book in BOOK_ORDER if book in asv_books and book in webp_books]
    comparisons = [compare_book(asv_books[book], webp_books[book]) for book in shared]
    rankings = sorted(
        comparisons,
        key=lambda row: (-row["visible_token_ratio_ppm"], BOOK_INDEX[row["book_code"]]),
    )
    focus = [row for row in comparisons if row["book_code"] in FOCUS_BOOKS]
    return {
        "diagnostic_contract": "usfm-source-and-parser-structure-counts-v1",
        "focus_books": list(FOCUS_BOOKS),
        "gospel_books": list(GOSPEL_BOOKS),
        "control_books": list(CONTROL_BOOKS),
        "shared_book_count": len(shared),
        "asv_corpus_totals": {key: value for key, value in asv.items() if key != "books"},
        "webp_corpus_totals": {key: value for key, value in webp.items() if key != "books"},
        "highest_visible_token_ratio_books": [
            {
                "book_code": row["book_code"],
                "asv_visible_token_count": row["asv"]["visible_token_count"],
                "webp_visible_token_count": row["webp"]["visible_token_count"],
                "visible_token_ratio_ppm": row["visible_token_ratio_ppm"],
                "source_line_ratio_ppm": row["source_line_ratio_ppm"],
                "payload_line_ratio_ppm": row["payload_line_ratio_ppm"],
                "tokens_per_record_ratio_ppm": row["tokens_per_record_ratio_ppm"],
            }
            for row in rankings[:12]
        ],
        "focus_book_comparisons": focus,
        "scripture_text_reported": False,
        "token_lists_reported": False,
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
            "ASV/WEBP Gospel structure diagnostic mismatch: "
            f"expected {len(expected_rendered)} canonical bytes, "
            f"observed {len(observed_rendered)} canonical bytes"
        )


def run(expected_path: Path | None = None) -> dict[str, Any]:
    asv_target = load_json(ASV_TARGET_PATH)
    asv_artifact = load_json(ASV_ARTIFACT_PATH)
    webp_target = load_json(WEBP_TARGET_PATH)
    webp_artifact = load_json(WEBP_ARTIFACT_PATH)

    with tempfile.TemporaryDirectory(prefix="bible-os-asv-webp-structure-") as temp_dir:
        temp_root = Path(temp_dir)
        asv_archive_path = temp_root / asv_artifact["filename"]
        webp_archive_path = temp_root / webp_artifact["filename"]
        download_verified_archive(asv_target, asv_archive_path)
        download_verified_archive(webp_target, webp_archive_path)
        with zipfile.ZipFile(asv_archive_path) as archive:
            asv = analyze_translation(archive, AsvUsfmAdapter(), "eng-asv")
        with zipfile.ZipFile(webp_archive_path) as archive:
            webp = analyze_translation(archive, WebpUsfmAdapter(), "eng-webp")

    comparison = summarize_comparison(asv, webp)
    if expected_path is not None:
        assert_expected(comparison, load_json(expected_path))
        profile_status = "matched"
    else:
        profile_status = "observed-unpinned"

    return {
        "status": "passed",
        "experiment": "asv-webp-gospel-structure-diagnostic-v1",
        "asv_artifact_sha256": asv_artifact["sha256"],
        "webp_artifact_sha256": webp_artifact["sha256"],
        "comparison": comparison,
        "profile_status": profile_status,
        "expected_profile": str(expected_path) if expected_path is not None else None,
        "corpus_bytes_committed": False,
        "scripture_text_reported": False,
        "token_lists_reported": False,
        "per_locator_text_digests_reported": False,
        "text_boundaries_defined": False,
        "mapping_authority": "none",
        "execution_eligible": False,
        "publication_eligible": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose ASV/WEBP Gospel token inflation without reporting scripture text"
    )
    parser.add_argument("--expected", type=Path)
    parser.add_argument("--report", type=Path, default=Path("asv-webp-gospel-structure-report.json"))
    args = parser.parse_args(argv)

    report = run(args.expected)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
