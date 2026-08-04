from __future__ import annotations

import json

import pytest

from scripts.asv_webp_character_marker_accounting_ci import (
    analyze_translation,
    summarize_comparison,
)
from scripts.asv_webp_character_marker_profile_ci import (
    assert_expected,
    build_profile,
    canonical_json_bytes,
)
from tests.test_asv_webp_character_marker_accounting import record


def synthetic_comparison() -> dict:
    asv = analyze_translation(
        [
            record(1, "Base\n\\add Base\\add*", book_code="MAT"),
            record(2, "Control\n\\add Control\\add*", book_code="ACT"),
        ],
        "eng-asv",
    )
    webp = analyze_translation(
        [
            record(1, "Distinct\n\\wj gospel words\\wj*", book_code="MAT"),
            record(2, "Control\n\\wj Control\\wj*", book_code="ACT"),
            record(3, "Apocalypse\n\\wj final words\\wj*", book_code="REV"),
        ],
        "eng-webp",
    )
    return summarize_comparison(asv, webp)


def test_profile_pins_full_comparison_and_compact_evidence() -> None:
    comparison = synthetic_comparison()
    profile = build_profile(comparison)

    assert profile["profile_contract"] == "asv-webp-character-marker-profile-v1"
    assert profile["comparison_byte_size"] == len(canonical_json_bytes(comparison))
    assert len(profile["comparison_sha256"]) == 64
    assert profile["asv"]["markers"][0]["marker"] == "add"
    assert profile["webp"]["markers"][0]["marker"] == "wj"
    assert [row["book_code"] for row in profile["webp_books_with_character_style"]] == [
        "MAT",
        "ACT",
        "REV",
    ]
    assert [row["book_code"] for row in profile["focus_book_profiles"]] == [
        "MAT",
        "MRK",
        "LUK",
        "JHN",
        "ACT",
        "ROM",
    ]


def test_profile_is_deterministic_and_hash_sensitive() -> None:
    comparison = synthetic_comparison()
    first = build_profile(comparison)
    second = build_profile(json.loads(json.dumps(comparison)))
    assert first == second

    changed = json.loads(json.dumps(comparison))
    changed["webp"]["markers"][0]["visible_token_count"] += 1
    assert build_profile(changed)["comparison_sha256"] != first["comparison_sha256"]


def test_profile_preserves_privacy_and_authority_boundaries() -> None:
    profile = build_profile(synthetic_comparison())
    rendered = json.dumps(profile, sort_keys=True)

    assert profile["scripture_text_reported"] is False
    assert profile["token_lists_reported"] is False
    assert profile["locator_identifiers_reported"] is False
    assert profile["per_locator_text_digests_reported"] is False
    assert profile["text_boundaries_defined"] is False
    assert profile["corpus_mutation"] == "not-performed"
    assert profile["mapping_authority"] == "none"
    assert profile["execution_eligible"] is False
    assert profile["publication_eligible"] is False
    assert "gospel words" not in rendered
    assert "raw_payload" not in rendered
    assert "source_sequence" not in rendered


def test_profile_mismatch_fails_closed() -> None:
    profile = build_profile(synthetic_comparison())
    changed = json.loads(json.dumps(profile))
    changed["comparison_byte_size"] += 1

    with pytest.raises(ValueError, match="character marker profile mismatch"):
        assert_expected(profile, changed)
