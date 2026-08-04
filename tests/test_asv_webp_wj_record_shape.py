from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from bible_os.importers.webp_usfm import WebpUsfmAdapter
from scripts.asv_webp_wj_record_shape_ci import (
    SourceShapeRecord,
    analyze_archive,
    assert_expected,
    classify_subsequent_line,
    iter_source_shape_records,
    record_shape,
    summarize_comparison,
    summarize_shape_records,
)


def shape_record(opening: str, *subsequent: str) -> SourceShapeRecord:
    return SourceShapeRecord(opening, tuple(subsequent))


def analysis(
    translation_id: str,
    summary: dict,
    *,
    book_code: str = "MAT",
) -> dict:
    book = {"book_code": book_code, **summary}
    return {
        "translation_id": translation_id,
        "book_count": 1,
        "corpus": summary,
        "books": [book],
        "books_with_subsequent_wj": (
            [book] if summary["records_with_subsequent_wj"] else []
        ),
    }


def test_source_parser_preserves_empty_verse_opening() -> None:
    records = list(
        iter_source_shape_records(
            "\\id MAT\n"
            "\\c 1\n"
            "\\v 1\n"
            "\\wj later words\\wj*\n"
            "\\v 2 opening words\n"
            "\\p\n"
            "continued words\n"
        )
    )

    assert records == [
        shape_record("", "\\wj later words\\wj*"),
        shape_record("opening words", "\\p", "continued words"),
    ]


def test_record_shape_categories_are_mechanical() -> None:
    assert record_shape(("opening",), True, False) == "opening-plus-wj"
    assert record_shape((), True, False) == "no-opening-wj-only"
    assert record_shape((), True, True) == "no-opening-wj-and-non-wj"
    assert record_shape(("opening",), False, True) == "opening-plus-non-wj"
    assert record_shape((), False, False) == "empty"


def test_exact_wj_line_classification_is_separate() -> None:
    assert classify_subsequent_line("\\wj words\\wj*") == "wj"
    assert classify_subsequent_line("\\p") == "other-marker"
    assert classify_subsequent_line("plain continuation") == "unmarked"


def test_summary_separates_opening_wj_and_other_subsequent_tokens() -> None:
    summary = summarize_shape_records(
        [
            shape_record("opening alpha", "\\wj quoted beta gamma\\wj*"),
            shape_record(
                "",
                "\\wj delta epsilon\\wj*",
                "\\p",
                "continued zeta",
            ),
        ]
    )

    assert summary["record_count"] == 2
    assert summary["opening_visible_token_count"] == 2
    assert summary["opening_zero_token_line_count"] == 1
    assert summary["subsequent_wj_line_count"] == 2
    assert summary["subsequent_wj_visible_token_count"] == 5
    assert summary["subsequent_other_marker_line_count"] == 1
    assert summary["subsequent_unmarked_line_count"] == 1
    assert summary["subsequent_unmarked_visible_token_count"] == 2
    assert summary["records_with_subsequent_wj"] == 2
    assert summary["wj_record_opening_visible_token_count"] == 2
    assert summary["wj_record_wj_visible_token_count"] == 5
    assert summary["wj_record_non_wj_subsequent_visible_token_count"] == 2
    assert summary["wj_record_adapter_visible_token_count"] == 9
    assert summary["token_reconciliation_delta"] == 0
    assert summary["record_shapes"] == [
        {"shape": "opening-plus-wj", "record_count": 1},
        {"shape": "no-opening-wj-and-non-wj", "record_count": 1},
    ]
    assert summary["subsequent_wj_lines_per_wj_record"] == [
        {"line_count": 1, "record_count": 2}
    ]


def test_multiple_wj_lines_are_histogrammed_without_locators() -> None:
    summary = summarize_shape_records(
        [
            shape_record(
                "opening",
                "\\wj first line\\wj*",
                "\\wj second line\\wj*",
            )
        ]
    )

    assert summary["records_with_multiple_subsequent_wj"] == 1
    assert summary["subsequent_wj_lines_per_wj_record"] == [
        {"line_count": 2, "record_count": 1}
    ]


def test_summary_is_independent_of_record_order() -> None:
    records = [
        shape_record("opening", "\\wj first line\\wj*"),
        shape_record("", "\\p", "continuation"),
    ]
    assert summarize_shape_records(records) == summarize_shape_records(
        list(reversed(records))
    )


def test_archive_analysis_reconciles_source_and_adapter_record_counts() -> None:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "MAT.usfm",
            "\\id MAT\n"
            "\\c 1\n"
            "\\v 1 opening words\n"
            "\\wj later words\\wj*\n"
            "\\v 2 second opening\n",
        )
    buffer.seek(0)

    with ZipFile(buffer) as archive:
        result = analyze_archive(archive, WebpUsfmAdapter(), "synthetic")

    assert result["book_count"] == 1
    assert result["corpus"]["record_count"] == 2
    assert result["corpus"]["records_with_subsequent_wj"] == 1
    assert result["corpus"]["adapter_visible_token_count"] == 6
    assert [row["book_code"] for row in result["books_with_subsequent_wj"]] == [
        "MAT"
    ]


def test_comparison_reports_only_aggregate_source_shape() -> None:
    asv_summary = summarize_shape_records([shape_record("Control wording")])
    webp_summary = summarize_shape_records(
        [shape_record("Private opening", "\\wj Private later wording\\wj*")]
    )
    comparison = summarize_comparison(
        analysis("eng-asv", asv_summary),
        analysis("eng-webp", webp_summary),
    )
    rendered = json.dumps(comparison, sort_keys=True)

    assert comparison["diagnostic_contract"] == "source-record-position-accounting-v1"
    assert comparison["scripture_text_reported"] is False
    assert comparison["token_lists_reported"] is False
    assert comparison["locator_identifiers_reported"] is False
    assert comparison["text_boundaries_defined"] is False
    assert comparison["parser_behavior_changed"] is False
    assert comparison["corpus_mutation"] == "not-performed"
    assert "Control wording" not in rendered
    assert "Private opening" not in rendered
    assert "Private later wording" not in rendered
    assert "raw_payload" not in rendered
    assert "source_sequence" not in rendered


def test_expected_profile_mismatch_fails_closed(tmp_path: Path) -> None:
    observed = {"contract": "v1", "count": 2}
    expected_path = tmp_path / "expected.json"
    expected_path.write_text(
        json.dumps({"contract": "v1", "count": 1}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="wj record-shape accounting mismatch"):
        assert_expected(
            observed,
            json.loads(expected_path.read_text(encoding="utf-8")),
        )
