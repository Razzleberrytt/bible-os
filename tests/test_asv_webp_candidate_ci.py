from __future__ import annotations

import json

import pytest

from scripts.asv_webp_candidate_ci import (
    assert_expected,
    build_candidate_records,
    summarize_candidates,
)


def row(
    book_code: str,
    chapter: int,
    verse: int,
    realization_type: str,
    namespace: str,
) -> dict:
    locator = f"{book_code}.{chapter}.{verse}"
    return {
        "book_code": book_code,
        "chapter": chapter,
        "verse": verse,
        "reference_id": f"ref_{namespace}_{locator}",
        "passage_id": f"pas_{namespace}_{locator}",
        "realization_type": realization_type,
        "source_text": "must never enter candidate output",
        "source_text_sha256": "f" * 64,
        "raw_payload_sha256": "e" * 64,
    }


def synthetic_rows() -> tuple[list[dict], list[dict]]:
    asv = [
        row("GEN", 1, 1, "text", "asv"),
        row("GEN", 1, 2, "empty-placeholder", "asv"),
        row("GEN", 1, 3, "text", "asv"),
        row("EXO", 1, 1, "empty-placeholder", "asv"),
    ]
    webp = [
        row("GEN", 1, 1, "text", "webp"),
        row("GEN", 1, 2, "text", "webp"),
        row("GEN", 1, 4, "empty-placeholder", "webp"),
        row("EXO", 1, 1, "empty-placeholder", "webp"),
    ]
    return asv, webp


def test_candidate_stream_is_deterministic_and_canonically_ordered():
    asv, webp = synthetic_rows()
    first = build_candidate_records(asv, webp)
    second = build_candidate_records(list(reversed(asv)), list(reversed(webp)))
    assert first == second
    assert [record["locator"] for record in first] == [
        "GEN 1:1",
        "GEN 1:2",
        "GEN 1:3",
        "GEN 1:4",
        "EXO 1:1",
    ]


def test_candidates_classify_same_mismatch_and_exclusive_loci():
    asv, webp = synthetic_rows()
    records = build_candidate_records(asv, webp)
    classes = {record["locator"]: record["candidate_class"] for record in records}
    assert classes == {
        "GEN 1:1": "same-locator-observation",
        "GEN 1:2": "realization-mismatch-observation",
        "GEN 1:3": "asv-only-locus",
        "GEN 1:4": "webp-only-locus",
        "EXO 1:1": "same-locator-observation",
    }


def test_candidate_records_exclude_scripture_text_and_hashes():
    asv, webp = synthetic_rows()
    rendered = json.dumps(build_candidate_records(asv, webp), sort_keys=True)
    for forbidden in [
        "source_text",
        "normalized_text",
        "source_text_sha256",
        "raw_payload_sha256",
        "must never enter candidate output",
    ]:
        assert forbidden not in rendered


def test_every_candidate_is_inert_and_non_authoritative():
    asv, webp = synthetic_rows()
    for record in build_candidate_records(asv, webp):
        assert record["queue_mutation"] is False
        assert record["mapping_authority"] == "none"
        assert record["execution_eligible"] is False
        assert record["publication_eligible"] is False
        assert record["suggested_review_kind"] == "uncertain"


def test_summary_exposes_only_exception_metadata():
    asv, webp = synthetic_rows()
    report = summarize_candidates(build_candidate_records(asv, webp))
    assert report["record_count"] == 5
    assert report["common_locator_count"] == 3
    assert report["same_locator_same_realization_count"] == 2
    assert report["both_text_count"] == 1
    assert report["both_placeholder_count"] == 1
    assert report["asv_placeholder_webp_text_count"] == 1
    assert report["asv_text_webp_placeholder_count"] == 0
    assert report["realization_mismatch_count"] == 1
    assert report["asv_only_locator_count"] == 1
    assert report["webp_only_locator_count"] == 1
    assert report["exceptional_candidate_count"] == 3
    assert [item["locator"] for item in report["exceptional_candidates"]] == [
        "GEN 1:2",
        "GEN 1:3",
        "GEN 1:4",
    ]
    assert "asv" not in report["exceptional_candidates"][0]
    assert "webp" not in report["exceptional_candidates"][0]


def test_duplicate_source_locators_are_rejected():
    asv, webp = synthetic_rows()
    with pytest.raises(ValueError, match="duplicate ASV locator"):
        build_candidate_records(asv + [dict(asv[0])], webp)
    with pytest.raises(ValueError, match="duplicate WEBP locator"):
        build_candidate_records(asv, webp + [dict(webp[0])])


def test_expected_profile_mismatch_fails_closed():
    asv, webp = synthetic_rows()
    report = summarize_candidates(build_candidate_records(asv, webp))
    assert_expected(report, {"record_count": 5})
    with pytest.raises(ValueError, match="candidate profile mismatch"):
        assert_expected(report, {"record_count": 6})
