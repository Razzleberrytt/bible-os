from __future__ import annotations

import json
from pathlib import Path

import pytest

from bible_os.importers.base import SourceRecord
from scripts.asv_webp_character_marker_accounting_ci import (
    analyze_translation,
    assert_expected,
    contains_contiguous,
    summarize_comparison,
    summarize_records,
)


def record(
    sequence: int,
    payload: str,
    *,
    book_code: str = "MAT",
    chapter: int = 1,
    verse_label: str | None = None,
) -> SourceRecord:
    return SourceRecord(
        source_file=f"{book_code}.usfm",
        book_code=book_code,
        chapter=chapter,
        verse_label=verse_label or str(sequence),
        source_sequence=sequence,
        raw_payload=payload,
    )


def row_by_marker(summary: dict, marker: str) -> dict:
    return next(row for row in summary["markers"] if row["marker"] == marker)


def test_contiguous_match_is_ordered_and_nonempty() -> None:
    assert contains_contiguous(("alpha", "beta"), ("before", "alpha", "beta", "after"))
    assert not contains_contiguous(("alpha", "beta"), ("beta", "alpha"))
    assert not contains_contiguous((), ("alpha",))
    assert not contains_contiguous(("alpha", "beta"), ("alpha",))


def test_marker_accounting_distinguishes_exact_contained_and_unique_lines() -> None:
    summary = summarize_records(
        [
            record(1, "Alpha beta\n\\wj Alpha beta\\wj*"),
            record(2, "Before gamma delta after\n\\wj gamma delta\\wj*"),
            record(3, "Ordinary material\n\\wj distinct words\\wj*"),
            record(4, "\\wj*"),
            record(5, "Inline \\wj ignored marker\\wj*"),
        ]
    )

    wj = row_by_marker(summary, "wj")
    assert summary["record_count"] == 5
    assert summary["records_with_character_style"] == 4
    assert wj["line_count"] == 4
    assert wj["record_count"] == 4
    assert wj["zero_token_line_count"] == 1
    assert wj["visible_token_count"] == 6
    assert wj["exact_duplicate_line_count"] == 1
    assert wj["exact_duplicate_token_count"] == 2
    assert wj["contained_duplicate_line_count"] == 2
    assert wj["contained_duplicate_token_count"] == 4
    assert wj["exact_duplicate_line_ratio_ppm"] == 250_000
    assert wj["contained_duplicate_line_ratio_ppm"] == 500_000


def test_multiple_lines_of_same_marker_count_one_record_once() -> None:
    summary = summarize_records(
        [record(1, "Base line\n\\wj first line\\wj*\n\\wj second line\\wj*")]
    )
    wj = row_by_marker(summary, "wj")
    assert wj["line_count"] == 2
    assert wj["record_count"] == 1
    assert summary["records_with_character_style"] == 1


def test_exact_marker_roots_are_kept_separate_and_sorted_deterministically() -> None:
    records = [
        record(1, "\\add one token\\add*"),
        record(2, "\\wj two visible tokens\\wj*"),
        record(3, "\\qt quoted words\\qt*"),
    ]
    forward = summarize_records(records)
    reverse = summarize_records(list(reversed(records)))

    assert forward == reverse
    assert [row["marker"] for row in forward["markers"]] == ["wj", "add", "qt"]


def test_translation_summary_is_book_ordered_and_focus_limited() -> None:
    analysis = analyze_translation(
        [
            record(3, "\\wj gospel words\\wj*", book_code="JHN"),
            record(1, "\\wj matthew words\\wj*", book_code="MAT"),
            record(2, "\\add acts words\\add*", book_code="ACT"),
            record(4, "\\wj revelation words\\wj*", book_code="REV"),
        ],
        "synthetic",
    )

    assert analysis["book_count"] == 4
    assert [row["book_code"] for row in analysis["books_with_character_style"]] == [
        "MAT",
        "JHN",
        "ACT",
        "REV",
    ]
    assert [row["book_code"] for row in analysis["focus_books"]] == ["MAT", "JHN", "ACT"]


def test_comparison_reports_only_aggregate_numeric_evidence() -> None:
    asv = analyze_translation(
        [record(1, "Control wording\n\\wj Control wording\\wj*")], "eng-asv"
    )
    webp = analyze_translation(
        [record(1, "Private example wording\n\\wj Private example wording\\wj*")],
        "eng-webp",
    )
    comparison = summarize_comparison(asv, webp)
    rendered = json.dumps(comparison, sort_keys=True)

    assert comparison["diagnostic_contract"] == "character-marker-same-record-accounting-v1"
    assert comparison["scripture_text_reported"] is False
    assert comparison["token_lists_reported"] is False
    assert comparison["locator_identifiers_reported"] is False
    assert comparison["text_boundaries_defined"] is False
    assert comparison["corpus_mutation"] == "not-performed"
    assert comparison["mapping_authority"] == "none"
    assert "Control wording" not in rendered
    assert "Private example wording" not in rendered
    assert "MAT 1:1" not in rendered
    assert "raw_payload" not in rendered
    assert "source_sequence" not in rendered


def test_focus_comparison_freezes_gospel_and_control_order() -> None:
    asv = analyze_translation(
        [
            record(1, "\\wj asv\\wj*", book_code="MAT"),
            record(2, "\\add asv\\add*", book_code="ACT"),
        ],
        "eng-asv",
    )
    webp = analyze_translation(
        [
            record(1, "\\wj webp words\\wj*", book_code="MAT"),
            record(2, "\\add webp\\add*", book_code="ACT"),
        ],
        "eng-webp",
    )
    comparison = summarize_comparison(asv, webp)

    assert [row["book_code"] for row in comparison["focus_book_comparisons"]] == [
        "MAT",
        "MRK",
        "LUK",
        "JHN",
        "ACT",
        "ROM",
    ]
    matthew = comparison["focus_book_comparisons"][0]
    assert matthew["visible_token_count_delta"] == 1
    assert matthew["marker_comparisons"][0]["marker"] == "wj"


def test_expected_profile_mismatch_fails_closed(tmp_path: Path) -> None:
    observed = {"contract": "v1", "count": 2}
    expected_path = tmp_path / "expected.json"
    expected_path.write_text(json.dumps({"contract": "v1", "count": 1}), encoding="utf-8")

    with pytest.raises(ValueError, match="character marker accounting mismatch"):
        assert_expected(observed, json.loads(expected_path.read_text(encoding="utf-8")))


def test_aggregate_output_is_independent_of_input_order() -> None:
    records = [
        record(1, "First\n\\wj First\\wj*", book_code="MAT"),
        record(2, "Second\n\\add Second\\add*", book_code="ACT"),
        record(3, "Third\n\\qt Third\\qt*", book_code="ROM"),
    ]
    forward = analyze_translation(records, "synthetic")
    reverse = analyze_translation(list(reversed(records)), "synthetic")
    assert forward == reverse
