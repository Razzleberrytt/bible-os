from __future__ import annotations

import io
import json
import zipfile

import pytest

from bible_os.importers.base import SourceRecord
from scripts.asv_adapter_smoke import AsvUsfmAdapter
from scripts.asv_webp_gospel_structure_ci import (
    analyze_book_records,
    analyze_translation,
    assert_expected,
    leading_marker,
    marker_class,
    ratio_ppm,
    source_documents,
    summarize_comparison,
)
from bible_os.importers.webp_usfm import WebpUsfmAdapter


def record(payload: str, *, book: str = "MAT", verse: str = "1") -> SourceRecord:
    return SourceRecord(
        source_file=f"{book}.usfm",
        book_code=book,
        chapter=1,
        verse_label=verse,
        source_sequence=int(verse),
        raw_payload=payload,
    )


def archive_bytes(files: list[tuple[str, str]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files:
            archive.writestr(name, content)
    return buffer.getvalue()


def open_archive(payload: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(payload))


def test_marker_classes_are_explicit_and_stable():
    assert marker_class("v") == "chapter-verse"
    assert marker_class("fqa") == "note-cross-reference"
    assert marker_class("w") == "word-attribute"
    assert marker_class("wj") == "character-style"
    assert marker_class("s2") == "heading-title"
    assert marker_class("q1") == "paragraph-poetry-list"
    assert marker_class("zaln-s") == "milestone"
    assert marker_class("id") == "metadata"
    assert marker_class("zz") == "other"
    assert leading_marker("  \\s1 Heading") == "s1"
    assert leading_marker("ordinary words") is None


def test_ratio_ppm_can_express_inflation_above_one():
    assert ratio_ppm(2, 1) == 2_000_000
    assert ratio_ppm(3, 2) == 1_500_000
    assert ratio_ppm(0, 0) == 0
    with pytest.raises(ValueError, match="nonnegative"):
        ratio_ppm(-1, 1)


def test_record_analysis_separates_marker_led_and_unmarked_lines():
    metrics = analyze_book_records(
        [
            record(
                "Main visible words\n"
                "\\s Section heading words\n"
                "\\p\n"
                "Continued words\n"
                "\\f + \\ft hidden note words\\f*"
            )
        ]
    )

    assert metrics["record_count"] == 1
    assert metrics["text_record_count"] == 1
    assert metrics["visible_token_count"] == 8
    assert metrics["payload_line_count"] == 5
    assert metrics["unmarked_payload_line_count"] == 2
    assert metrics["unmarked_line_local_token_count"] == 5
    assert metrics["leading_marker_line_count"] == 3

    class_lines = {
        row["name"]: row["count"]
        for row in metrics["leading_marker_class_line_counts"]
    }
    class_tokens = {
        row["name"]: row["count"]
        for row in metrics["leading_marker_class_line_local_token_counts"]
    }
    assert class_lines == {
        "note-cross-reference": 1,
        "heading-title": 1,
        "paragraph-poetry-list": 1,
    }
    assert class_tokens == {"heading-title": 3}

    rendered = json.dumps(metrics, sort_keys=True).lower()
    for forbidden in (
        "main visible words",
        "section heading words",
        "continued words",
        "hidden note words",
        "raw_payload",
    ):
        assert forbidden not in rendered


def test_source_documents_are_sorted_and_duplicate_ids_fail_closed():
    payload = archive_bytes(
        [
            ("z/ACT.usfm", "\\id ACT\n\\c 1\n\\v 1 Acts words\n"),
            ("a/MAT.usfm", "\\id MAT\n\\c 1\n\\v 1 Matthew words\n"),
        ]
    )
    with open_archive(payload) as archive:
        documents = source_documents(archive)
    assert list(documents) == ["MAT", "ACT"]
    assert documents["MAT"]["source_file"] == "a/MAT.usfm"
    assert "Matthew words" in documents["MAT"]["text"]

    duplicate = archive_bytes(
        [
            ("a.usfm", "\\id MAT\n\\c 1\n\\v 1 One\n"),
            ("b.usfm", "\\id MAT\n\\c 1\n\\v 1 Two\n"),
        ]
    )
    with open_archive(duplicate) as archive:
        with pytest.raises(ValueError, match="duplicate USFM book id"):
            source_documents(archive)


def test_translation_analysis_and_comparison_are_text_private_and_deterministic():
    asv_payload = archive_bytes(
        [
            (
                "MAT.usfm",
                "\\id MAT\n\\c 1\n\\v 1 Alpha beta\n\\s Short heading\n\\v 2 Gamma delta\n",
            ),
            (
                "ACT.usfm",
                "\\id ACT\n\\c 1\n\\v 1 Epsilon zeta\n\\v 2 Eta theta\n",
            ),
        ]
    )
    webp_payload = archive_bytes(
        [
            (
                "ACT.usfm",
                "\\id ACT\n\\c 1\n\\v 1 Epsilon zeta\n\\v 2 Eta theta\n",
            ),
            (
                "MAT.usfm",
                "\\id MAT\n\\c 1\n\\v 1 Alpha beta extra words\n"
                "\\s Longer structural heading words\n"
                "\\v 2 Gamma delta extra words\n",
            ),
        ]
    )

    with open_archive(asv_payload) as archive:
        asv = analyze_translation(archive, AsvUsfmAdapter(), "eng-asv")
    with open_archive(webp_payload) as archive:
        webp = analyze_translation(archive, WebpUsfmAdapter(), "eng-webp")

    first = summarize_comparison(asv, webp)
    second = summarize_comparison(asv, webp)
    assert first == second
    assert first["shared_book_count"] == 2
    assert [row["book_code"] for row in first["highest_visible_token_ratio_books"]] == [
        "MAT",
        "ACT",
    ]
    assert [row["book_code"] for row in first["focus_book_comparisons"]] == [
        "MAT",
        "ACT",
    ]

    matthew = first["focus_book_comparisons"][0]
    assert matthew["visible_token_ratio_ppm"] > 1_000_000
    assert matthew["record_ratio_ppm"] == 1_000_000
    assert matthew["webp"]["record_count"] == matthew["asv"]["record_count"] == 2
    assert first["scripture_text_reported"] is False
    assert first["token_lists_reported"] is False
    assert first["text_boundaries_defined"] is False
    assert first["corpus_mutation"] == "not-performed"

    rendered = json.dumps(first, sort_keys=True).lower()
    for forbidden in (
        "alpha beta",
        "gamma delta",
        "epsilon zeta",
        "short heading",
        "longer structural heading",
        "source_text",
        "raw_payload",
    ):
        assert forbidden not in rendered


def test_expected_profile_requires_exact_structural_observation():
    observed = {"shared_book_count": 2, "scripture_text_reported": False}
    assert_expected(observed, dict(observed))
    with pytest.raises(ValueError, match="diagnostic mismatch"):
        assert_expected(observed, {"shared_book_count": 3})
