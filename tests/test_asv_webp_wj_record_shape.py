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
    classify_opening_payload,
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
        "books_with_opening_wj": (
            [book] if summary["records_with_opening_wj"] else []
        ),
        "books_with_opening_add": (
            [book] if summary["opening_add_line_count"] else []
        ),
    }


def test_source_parser_preserves_empty_verse_opening() -> None:
    records = list(
        iter_source_shape_records(
            "\\id MAT\n"
            "\\c 1\n"
            "\\v 1\n"
            "\\wj later control\\wj*\n"
            "\\v 2 \\wj opening words\\wj*\n"
            "\\p\n"
            "continued words\n"
        )
    )

    assert records == [
        shape_record("", "\\wj later control\\wj*"),
        shape_record("\\wj opening words\\wj*", "\\p", "continued words"),
    ]


def test_opening_payload_classification_is_exact() -> None:
    assert classify_opening_payload("") == "empty"
    assert classify_opening_payload("plain words") == "unmarked"
    assert classify_opening_payload("\\wj words\\wj*") == "wj"
    assert classify_opening_payload("\\add words\\add*") == "add"
    assert classify_opening_payload("\\qt words\\qt*") == "other-marker"


def test_subsequent_wj_remains_a_separate_control() -> None:
    assert classify_subsequent_line("\\wj words\\wj*") == "wj"
    assert classify_subsequent_line("\\p") == "other-marker"
    assert classify_subsequent_line("plain continuation") == "unmarked"


def test_record_shape_categories_use_opening_class_and_later_lines() -> None:
    assert record_shape("wj", False) == "opening-wj-only"
    assert record_shape("wj", True) == "opening-wj-plus-later"
    assert record_shape("add", False) == "opening-add-only"
    assert record_shape("unmarked", True) == "opening-unmarked-plus-later"
    assert record_shape("empty", False) == "empty"
    assert record_shape("empty", True) == "empty-plus-later"


def test_summary_separates_opening_wj_add_and_later_controls() -> None:
    summary = summarize_shape_records(
        [
            shape_record(
                "\\wj alpha beta\\wj*",
                "\\p",
                "continued gamma",
            ),
            shape_record("\\add supplied words\\add*"),
            shape_record("ordinary opening"),
            shape_record("", "\\wj later control\\wj*"),
        ]
    )

    assert summary["record_count"] == 4
    assert summary["opening_wj_line_count"] == 1
    assert summary["opening_wj_visible_token_count"] == 2
    assert summary["opening_add_line_count"] == 1
    assert summary["opening_add_visible_token_count"] == 2
    assert summary["opening_unmarked_line_count"] == 1
    assert summary["opening_unmarked_visible_token_count"] == 2
    assert summary["opening_zero_token_line_count"] == 1
    assert summary["subsequent_wj_line_count"] == 1
    assert summary["subsequent_wj_visible_token_count"] == 2
    assert summary["records_with_opening_wj"] == 1
    assert summary["records_with_opening_wj_and_subsequent_lines"] == 1
    assert summary["records_with_opening_wj_and_visible_subsequent_tokens"] == 1
    assert summary["opening_wj_record_opening_visible_token_count"] == 2
    assert summary["opening_wj_record_subsequent_visible_token_count"] == 1
    assert summary["opening_wj_record_adapter_visible_token_count"] == 3
    assert summary["opening_wj_record_opening_token_share_ppm"] == 666_667
    assert summary["opening_wj_record_subsequent_token_share_ppm"] == 333_333
    assert summary["token_reconciliation_delta"] == 0
    assert summary["record_shapes"] == [
        {"shape": "empty-plus-later", "record_count": 1},
        {"shape": "opening-unmarked-only", "record_count": 1},
        {"shape": "opening-wj-plus-later", "record_count": 1},
        {"shape": "opening-add-only", "record_count": 1},
    ]
    assert summary["subsequent_lines_per_opening_wj_record"] == [
        {"line_count": 2, "record_count": 1}
    ]


def test_marker_only_opening_is_zero_token_but_still_classified() -> None:
    summary = summarize_shape_records(
        [shape_record("\\wj*"), shape_record("\\add*")]
    )

    assert summary["opening_wj_line_count"] == 1
    assert summary["opening_wj_zero_token_line_count"] == 1
    assert summary["opening_add_line_count"] == 1
    assert summary["opening_add_zero_token_line_count"] == 1


def test_summary_is_independent_of_record_order() -> None:
    records = [
        shape_record("\\wj first line\\wj*"),
        shape_record("plain opening", "\\p"),
        shape_record("\\add supplied\\add*"),
    ]
    assert summarize_shape_records(records) == summarize_shape_records(
        list(reversed(records))
    )


def test_archive_analysis_finds_wj_on_verse_opening_payload() -> None:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "MAT.usfm",
            "\\id MAT\n"
            "\\c 1\n"
            "\\v 1 \\wj opening words\\wj*\n"
            "\\p\n"
            "\\v 2 plain opening\n",
        )
    buffer.seek(0)

    with ZipFile(buffer) as archive:
        result = analyze_archive(archive, WebpUsfmAdapter(), "synthetic")

    assert result["book_count"] == 1
    assert result["corpus"]["record_count"] == 2
    assert result["corpus"]["records_with_opening_wj"] == 1
    assert result["corpus"]["opening_wj_visible_token_count"] == 2
    assert result["corpus"]["subsequent_wj_line_count"] == 0
    assert result["corpus"]["adapter_visible_token_count"] == 4
    assert [row["book_code"] for row in result["books_with_opening_wj"]] == [
        "MAT"
    ]


def test_comparison_reports_only_aggregate_source_shape() -> None:
    asv_summary = summarize_shape_records(
        [shape_record("\\add Control wording\\add*")]
    )
    webp_summary = summarize_shape_records(
        [shape_record("\\wj Private opening wording\\wj*", "\\p")]
    )
    comparison = summarize_comparison(
        analysis("eng-asv", asv_summary),
        analysis("eng-webp", webp_summary),
    )
    rendered = json.dumps(comparison, sort_keys=True)

    assert comparison["diagnostic_contract"] == "source-verse-opening-marker-accounting-v2"
    assert comparison["scripture_text_reported"] is False
    assert comparison["token_lists_reported"] is False
    assert comparison["locator_identifiers_reported"] is False
    assert comparison["text_boundaries_defined"] is False
    assert comparison["parser_behavior_changed"] is False
    assert comparison["corpus_mutation"] == "not-performed"
    assert "Control wording" not in rendered
    assert "Private opening wording" not in rendered
    assert "raw_payload" not in rendered
    assert "source_sequence" not in rendered


def test_expected_profile_mismatch_fails_closed(tmp_path: Path) -> None:
    observed = {"contract": "v2", "count": 2}
    expected_path = tmp_path / "expected.json"
    expected_path.write_text(
        json.dumps({"contract": "v2", "count": 1}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="wj record-shape accounting mismatch"):
        assert_expected(
            observed,
            json.loads(expected_path.read_text(encoding="utf-8")),
        )
