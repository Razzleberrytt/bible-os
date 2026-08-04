from __future__ import annotations

import json
from copy import deepcopy

import pytest

from scripts.asv_webp_lexical_fingerprint_ci import (
    build_fingerprint_records,
    distance_band,
    nearest_rank,
    normalize_tokens,
    ratio_ppm,
    summarize_fingerprints,
    token_edit_distance,
    token_set_jaccard_distance_ppm,
)


def row(
    book_code: str,
    chapter: int,
    verse: int,
    text: str | None,
    *,
    realization_type: str = "text",
) -> dict:
    return {
        "book_code": book_code,
        "chapter": chapter,
        "verse": verse,
        "realization_type": realization_type,
        "source_text": text,
    }


def test_token_normalization_is_case_punctuation_and_apostrophe_stable():
    assert normalize_tokens("  LORD’S, mercies—don't END.  ") == (
        "lord's",
        "mercies",
        "don't",
        "end",
    )
    assert normalize_tokens("ＡＢＣ １２３") == ("abc", "123")


def test_integer_distance_primitives_are_deterministic():
    left = ("in", "the", "beginning")
    right = ("at", "beginning")

    assert token_edit_distance(left, right) == 2
    assert token_edit_distance(right, left) == 2
    assert ratio_ppm(2, 3) == 666_667
    assert token_set_jaccard_distance_ppm(left, right) == 750_000
    assert distance_band(0) == "exact"
    assert distance_band(100_000) == "very-low"
    assert distance_band(100_001) == "low"


def test_nearest_rank_uses_fixed_integer_semantics():
    values = [1, 2, 3, 4, 5]
    assert nearest_rank(values, 50) == 3
    assert nearest_rank(values, 90) == 5
    with pytest.raises(ValueError, match="at least one"):
        nearest_rank([], 50)


def test_fingerprint_records_are_numeric_only_and_exclude_placeholders():
    asv = [
        row("GEN", 1, 1, "In the beginning"),
        row("GEN", 1, 2, "The earth was empty"),
        row("GEN", 1, 3, None, realization_type="empty-placeholder"),
    ]
    webp = [
        row("GEN", 1, 1, "In the beginning"),
        row("GEN", 1, 2, "Earth was unformed"),
        row("GEN", 1, 3, "Words here"),
    ]

    records = build_fingerprint_records(asv, webp)
    assert [record["locator"] for record in records] == ["GEN 1:1", "GEN 1:2"]
    exact, changed = records

    assert exact["normalized_token_sequence_equal"] is True
    assert exact["token_edit_distance"] == 0
    assert exact["token_edit_distance_ppm"] == 0

    assert changed["asv_token_count"] == 4
    assert changed["webp_token_count"] == 3
    assert changed["token_count_delta"] == -1
    assert changed["token_count_abs_delta"] == 1
    assert changed["token_count_delta_ppm"] == 250_000
    # Delete "the", then substitute "empty" with "unformed".
    assert changed["token_edit_distance"] == 2
    assert changed["token_edit_distance_ppm"] == 500_000

    rendered = json.dumps(records, sort_keys=True).lower()
    for forbidden in (
        '"source_text"',
        '"raw_payload"',
        '"source_text_sha256"',
        "in the beginning",
        "earth was unformed",
    ):
        assert forbidden not in rendered


def test_duplicate_source_locators_fail_closed():
    duplicate = [row("GEN", 1, 1, "One"), row("GEN", 1, 1, "Two")]
    with pytest.raises(ValueError, match="duplicate ASV locator"):
        build_fingerprint_records(duplicate, [row("GEN", 1, 1, "One")])
    with pytest.raises(ValueError, match="duplicate WEBP locator"):
        build_fingerprint_records([row("GEN", 1, 1, "One")], duplicate)


def test_missing_text_and_zero_token_text_fail_closed():
    with pytest.raises(ValueError, match="missing source text"):
        build_fingerprint_records(
            [row("GEN", 1, 1, None)],
            [row("GEN", 1, 1, "One")],
        )
    with pytest.raises(ValueError, match="zero tokens"):
        build_fingerprint_records(
            [row("GEN", 1, 1, "---")],
            [row("GEN", 1, 1, "One")],
        )


def test_summary_is_reproducible_and_contains_only_metadata():
    asv = [
        row("GEN", 1, 1, "In the beginning"),
        row("GEN", 1, 2, "The earth was empty"),
        row("EXO", 1, 1, "These are the names"),
    ]
    webp = [
        row("GEN", 1, 1, "In the beginning"),
        row("GEN", 1, 2, "Earth was unformed"),
        row("EXO", 1, 1, "Now these are names"),
    ]
    records = build_fingerprint_records(asv, webp)

    first = summarize_fingerprints(records)
    second = summarize_fingerprints(deepcopy(records))
    assert first == second
    assert first["record_count"] == 3
    assert first["shared_text_locator_count"] == 3
    assert first["normalized_equal_locator_count"] == 1
    assert first["asv_total_token_count"] == 11
    assert first["webp_total_token_count"] == 10
    assert [book["book_code"] for book in first["book_summaries"]] == [
        "GEN",
        "EXO",
    ]
    assert len(first["highest_distance_locators"]) == 3
    assert first["source_text_retained"] is False
    assert first["token_lists_reported"] is False
    assert first["per_locator_text_digests_reported"] is False
    assert first["corpus_mutation"] == "not-performed"
    assert first["mapping_authority"] == "none"
    assert first["execution_eligible"] is False
    assert first["publication_eligible"] is False

    rendered = json.dumps(first, sort_keys=True).lower()
    for forbidden in (
        "in the beginning",
        "earth was unformed",
        "these are the names",
        '"source_text": "',
        '"tokens": [',
        '"source_text_sha256"',
        '"raw_payload"',
    ):
        assert forbidden not in rendered


def test_input_order_does_not_change_numeric_stream():
    asv = [row("GEN", 1, 1, "One two"), row("EXO", 1, 1, "Three four")]
    webp = [row("GEN", 1, 1, "One too"), row("EXO", 1, 1, "Three four")]

    forward = build_fingerprint_records(asv, webp)
    reverse = build_fingerprint_records(list(reversed(asv)), list(reversed(webp)))
    assert forward == reverse
    assert summarize_fingerprints(forward) == summarize_fingerprints(reverse)


def test_summary_rejects_empty_stream():
    with pytest.raises(ValueError, match="must not be empty"):
        summarize_fingerprints([])
