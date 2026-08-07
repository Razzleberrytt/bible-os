from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.asv_webp_wj_token_strata_ci import (
    FOCUS_BOOKS,
    build_stratified_records,
    summarize_records,
)
from scripts.asv_webp_wj_token_strata_profile_ci import (
    assert_expected,
    build_profile,
    canonical_json_bytes,
)


def row(book_code: str, chapter: int, verse: int, text: str) -> dict:
    return {
        "book_code": book_code,
        "chapter": chapter,
        "verse": verse,
        "realization_type": "text",
        "source_text": text,
    }


def summary_fixture() -> dict:
    asv = [
        row("MAT", 1, 1, "one two"),
        row("ROM", 1, 1, "same tokens"),
    ]
    webp = [
        row("MAT", 1, 1, "one two three"),
        row("ROM", 1, 1, "same tokens"),
    ]
    classes = {"MAT 1:1": "wj", "ROM 1:1": "unmarked"}
    return summarize_records(build_stratified_records(asv, webp, classes))


def test_canonical_json_bytes_are_order_independent() -> None:
    left = {"b": 2, "a": {"d": 4, "c": 3}}
    right = {"a": {"c": 3, "d": 4}, "b": 2}
    assert canonical_json_bytes(left) == canonical_json_bytes(right)


def test_profile_hashes_full_summary_and_keeps_focus_metrics() -> None:
    summary = summary_fixture()
    profile = build_profile(summary)

    assert profile["profile_contract"] == "asv-webp-wj-token-strata-profile-v1"
    assert profile["summary_byte_size"] == len(canonical_json_bytes(summary))
    assert len(profile["summary_sha256"]) == 64
    assert profile["numeric_stream"]["record_count"] == 2
    assert profile["shared_text_text_locator_count"] == 2
    assert profile["focus_books"] == list(FOCUS_BOOKS)
    assert profile["books_with_opening_wj"] == ["MAT"]
    assert [row["book_code"] for row in profile["focus_book_profiles"]] == [
        "MAT",
        "ROM",
    ]
    matthew = profile["focus_book_profiles"][0]
    assert matthew["opening_wj"]["locator_count"] == 1
    assert matthew["opening_wj"]["token_count_delta"] == 1
    assert matthew["non_wj"]["locator_count"] == 0


def test_profile_hash_changes_when_hidden_book_metric_changes() -> None:
    summary = summary_fixture()
    changed = copy.deepcopy(summary)
    changed["book_summaries"][0]["strata"][0]["webp_token_count"] += 1

    assert build_profile(summary)["summary_sha256"] != build_profile(changed)[
        "summary_sha256"
    ]


def test_profile_contains_no_wording_or_locator_values() -> None:
    rendered = json.dumps(build_profile(summary_fixture()), sort_keys=True)

    assert "one two three" not in rendered
    assert "same tokens" not in rendered
    assert "MAT 1:1" not in rendered
    assert "source_text" not in rendered
    assert '"locator":' not in rendered


def test_profile_mismatch_fails_closed(tmp_path: Path) -> None:
    profile = build_profile(summary_fixture())
    expected = copy.deepcopy(profile)
    expected["summary_byte_size"] += 1
    expected_path = tmp_path / "expected.json"
    expected_path.write_text(json.dumps(expected), encoding="utf-8")

    with pytest.raises(ValueError, match="token strata profile mismatch"):
        assert_expected(
            profile,
            json.loads(expected_path.read_text(encoding="utf-8")),
        )
