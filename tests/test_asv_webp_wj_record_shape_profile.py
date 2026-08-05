from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.asv_webp_wj_record_shape_ci import (
    FOCUS_BOOKS,
    SourceShapeRecord,
    summarize_comparison,
    summarize_shape_records,
)
from scripts.asv_webp_wj_record_shape_profile_ci import (
    assert_expected,
    build_profile,
    canonical_json_bytes,
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


def comparison_fixture() -> dict:
    asv = analysis(
        "eng-asv",
        summarize_shape_records(
            [shape_record("\\add control opening\\add*")]
        ),
    )
    webp = analysis(
        "eng-webp",
        summarize_shape_records(
            [shape_record("\\wj private opening words\\wj*", "\\p")]
        ),
    )
    return summarize_comparison(asv, webp)


def test_canonical_json_bytes_are_order_independent() -> None:
    left = {"b": 2, "a": {"d": 4, "c": 3}}
    right = {"a": {"c": 3, "d": 4}, "b": 2}
    assert canonical_json_bytes(left) == canonical_json_bytes(right)


def test_profile_hashes_full_comparison_and_preserves_compact_counters() -> None:
    comparison = comparison_fixture()
    profile = build_profile(comparison)

    assert profile["profile_contract"] == "asv-webp-wj-record-shape-profile-v2"
    assert profile["focus_books"] == list(FOCUS_BOOKS)
    assert profile["comparison_byte_size"] == len(
        canonical_json_bytes(comparison)
    )
    assert len(profile["comparison_sha256"]) == 64
    assert profile["asv"]["corpus"]["opening_add_line_count"] == 1
    assert profile["webp"]["corpus"]["records_with_opening_wj"] == 1
    assert profile["webp"]["corpus"]["opening_wj_visible_token_count"] == 3
    assert profile["webp_books_with_opening_wj"][0]["book_code"] == "MAT"
    assert "asv_books_with_opening_add" not in profile


def test_profile_hash_changes_when_internal_counter_changes() -> None:
    comparison = comparison_fixture()
    changed = copy.deepcopy(comparison)
    changed["webp"]["corpus"]["opening_wj_visible_token_count"] += 1

    assert build_profile(comparison)["comparison_sha256"] != build_profile(changed)[
        "comparison_sha256"
    ]


def test_profile_contains_no_scripture_wording_or_locators() -> None:
    rendered = json.dumps(build_profile(comparison_fixture()), sort_keys=True)

    assert "control opening" not in rendered
    assert "private opening words" not in rendered
    assert "raw_payload" not in rendered
    assert "source_sequence" not in rendered
    assert "verse_label" not in rendered


def test_profile_mismatch_fails_closed(tmp_path: Path) -> None:
    profile = build_profile(comparison_fixture())
    expected = copy.deepcopy(profile)
    expected["comparison_byte_size"] += 1
    expected_path = tmp_path / "expected.json"
    expected_path.write_text(json.dumps(expected), encoding="utf-8")

    with pytest.raises(ValueError, match="wj record-shape profile mismatch"):
        assert_expected(
            profile,
            json.loads(expected_path.read_text(encoding="utf-8")),
        )
