from __future__ import annotations

import json
from copy import deepcopy

import pytest

from scripts.asv_webp_gospel_structure_profile_ci import (
    assert_expected,
    build_profile,
    canonical_json_bytes,
)


def translation_book(token_count: int) -> dict:
    return {
        "book_code": "MAT",
        "source_file": "MAT.usfm",
        "source_bytes": 100,
        "compressed_bytes": 50,
        "crc32": "00000000",
        "source_line_count": 10,
        "source_marker_count": 7,
        "record_count": 2,
        "text_record_count": 2,
        "empty_record_count": 0,
        "payload_bytes": 80,
        "payload_line_count": 4,
        "payload_nonempty_line_count": 4,
        "unmarked_payload_line_count": 1,
        "unmarked_line_local_token_count": 2,
        "visible_token_count": token_count,
        "tokens_per_record_milli": token_count * 500,
        "payload_marker_count": 5,
        "leading_marker_line_count": 3,
        "source_marker_class_counts": [],
        "payload_marker_class_counts": [
            {"name": "chapter-verse", "count": 2},
            {"name": "heading-title", "count": 1},
        ],
        "leading_marker_class_line_counts": [
            {"name": "chapter-verse", "count": 2},
            {"name": "heading-title", "count": 1},
        ],
        "leading_marker_class_line_local_token_counts": [
            {"name": "chapter-verse", "count": token_count - 2},
            {"name": "heading-title", "count": 2},
        ],
        "top_payload_markers": [],
        "top_leading_payload_markers": [],
    }


def corpus_totals(translation_id: str, token_count: int) -> dict:
    return {
        "translation_id": translation_id,
        "book_count": 1,
        "source_file_count": 1,
        "source_bytes": 100,
        "compressed_bytes": 50,
        "source_line_count": 10,
        "record_count": 2,
        "text_record_count": 2,
        "empty_record_count": 0,
        "payload_line_count": 4,
        "payload_marker_count": 5,
        "visible_token_count": token_count,
    }


def comparison() -> dict:
    asv = translation_book(6)
    webp = translation_book(9)
    marker_comparison = [
        {
            "name": "chapter-verse",
            "asv_count": 2,
            "webp_count": 2,
            "delta": 0,
            "webp_to_asv_ratio_ppm": 1_000_000,
        }
    ]
    return {
        "diagnostic_contract": "usfm-source-and-parser-structure-counts-v1",
        "focus_books": ["MAT"],
        "gospel_books": ["MAT"],
        "control_books": [],
        "shared_book_count": 1,
        "asv_corpus_totals": corpus_totals("eng-asv", 6),
        "webp_corpus_totals": corpus_totals("eng-webp", 9),
        "highest_visible_token_ratio_books": [
            {
                "book_code": "MAT",
                "asv_visible_token_count": 6,
                "webp_visible_token_count": 9,
                "visible_token_ratio_ppm": 1_500_000,
                "source_line_ratio_ppm": 1_000_000,
                "payload_line_ratio_ppm": 1_000_000,
                "tokens_per_record_ratio_ppm": 1_500_000,
            }
        ],
        "focus_book_comparisons": [
            {
                "book_code": "MAT",
                "asv": asv,
                "webp": webp,
                "visible_token_delta": 3,
                "visible_token_ratio_ppm": 1_500_000,
                "source_byte_ratio_ppm": 1_000_000,
                "source_line_ratio_ppm": 1_000_000,
                "payload_line_ratio_ppm": 1_000_000,
                "record_ratio_ppm": 1_000_000,
                "tokens_per_record_ratio_ppm": 1_500_000,
                "payload_marker_ratio_ppm": 1_000_000,
                "payload_marker_class_comparison": marker_comparison,
                "leading_marker_line_class_comparison": marker_comparison,
                "leading_marker_line_local_token_class_comparison": marker_comparison,
            }
        ],
        "scripture_text_reported": False,
        "token_lists_reported": False,
        "per_locator_text_digests_reported": False,
        "text_boundaries_defined": False,
        "corpus_mutation": "not-performed",
        "mapping_authority": "none",
        "execution_eligible": False,
        "publication_eligible": False,
    }


def test_profile_is_deterministic_compact_and_text_private():
    source = comparison()
    first = build_profile(source)
    second = build_profile(deepcopy(source))

    assert first == second
    assert len(first["comparison_sha256"]) == 64
    assert first["comparison_byte_size"] == len(canonical_json_bytes(source))
    assert first["focus_book_profiles"][0]["visible_token_ratio_ppm"] == 1_500_000
    assert first["scripture_text_reported"] is False
    assert first["token_lists_reported"] is False
    assert first["text_boundaries_defined"] is False

    rendered = json.dumps(first, sort_keys=True).lower()
    for forbidden in ("scripture wording", "raw_payload", "source_text"):
        assert forbidden not in rendered


def test_profile_hash_pins_omitted_full_comparison_fields():
    source = comparison()
    first = build_profile(source)
    source["unreported_diagnostic_counter"] = 1
    second = build_profile(source)

    assert first["comparison_sha256"] != second["comparison_sha256"]
    assert first["comparison_byte_size"] != second["comparison_byte_size"]


def test_expected_profile_requires_exact_match():
    observed = build_profile(comparison())
    assert_expected(observed, deepcopy(observed))

    changed = deepcopy(observed)
    changed["comparison_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="profile mismatch"):
        assert_expected(observed, changed)
