from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from bible_os.importers.webp_usfm import WebpUsfmAdapter
from scripts.asv_webp_wj_token_strata_ci import (
    assert_expected,
    build_stratified_records,
    opening_classes_by_locator,
    ratio_ppm,
    summarize_records,
)


def row(
    book_code: str,
    chapter: int,
    verse: int,
    text: str | None,
    realization_type: str = "text",
) -> dict:
    return {
        "book_code": book_code,
        "chapter": chapter,
        "verse": verse,
        "realization_type": realization_type,
        "source_text": text,
    }


def fixture_rows() -> tuple[list[dict], list[dict], dict[str, str]]:
    asv = [
        row("MAT", 1, 1, "one two"),
        row("MAT", 1, 2, "three equal words"),
        row("MAT", 1, 3, "four token source text"),
        row("MAT", 1, 4, None, "empty-placeholder"),
    ]
    webp = [
        row("MAT", 1, 1, "one two three four"),
        row("MAT", 1, 2, "three equal words"),
        row("MAT", 1, 3, "short text"),
        row("MAT", 1, 4, "present text"),
    ]
    classes = {
        "MAT 1:1": "wj",
        "MAT 1:2": "unmarked",
        "MAT 1:3": "other-marker",
        "MAT 1:4": "wj",
    }
    return asv, webp, classes


def test_ratio_ppm_is_uncapped_and_deterministic() -> None:
    assert ratio_ppm(4, 2) == 2_000_000
    assert ratio_ppm(5, 7) == 714_286
    assert ratio_ppm(0, 0) == 0
    assert ratio_ppm(3, 0) == 3_000_000


def test_opening_classes_align_to_adapter_locators() -> None:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "MAT.usfm",
            "\\id MAT\n"
            "\\c 1\n"
            "\\v 1 \\wj opening words\\wj*\n"
            "\\p\n"
            "\\v 2 ordinary words\n",
        )
    buffer.seek(0)

    with ZipFile(buffer) as archive:
        classes = opening_classes_by_locator(archive, WebpUsfmAdapter())

    assert classes == {"MAT 1:1": "wj", "MAT 1:2": "unmarked"}


def test_shared_text_records_are_stratified_by_webp_opening_class() -> None:
    asv, webp, classes = fixture_rows()
    records = build_stratified_records(asv, webp, classes)

    assert [record["locator"] for record in records] == [
        "MAT 1:1",
        "MAT 1:2",
        "MAT 1:3",
    ]
    assert records[0]["stratum"] == "webp-opening-wj"
    assert records[0]["webp_to_asv_token_ratio_ppm"] == 2_000_000
    assert records[0]["comparison_direction"] == "webp-longer"
    assert records[1]["stratum"] == "webp-non-wj"
    assert records[1]["comparison_direction"] == "equal"
    assert records[2]["comparison_direction"] == "asv-longer"


def test_summary_separates_wj_and_non_wj_token_surplus() -> None:
    asv, webp, classes = fixture_rows()
    summary = summarize_records(build_stratified_records(asv, webp, classes))
    wj, non_wj = summary["strata"]

    assert summary["shared_text_text_locator_count"] == 3
    assert wj["stratum"] == "webp-opening-wj"
    assert wj["locator_count"] == 1
    assert wj["asv_token_count"] == 2
    assert wj["webp_token_count"] == 4
    assert wj["token_count_delta"] == 2
    assert wj["webp_to_asv_total_token_ratio_ppm"] == 2_000_000
    assert non_wj["stratum"] == "webp-non-wj"
    assert non_wj["locator_count"] == 2
    assert non_wj["asv_token_count"] == 7
    assert non_wj["webp_token_count"] == 5
    assert non_wj["token_count_delta"] == -2
    assert non_wj["webp_to_asv_total_token_ratio_ppm"] == 714_286
    assert non_wj["webp_longer_count"] == 0
    assert non_wj["asv_longer_count"] == 1
    assert non_wj["equal_count"] == 1


def test_duplicate_locators_fail_closed() -> None:
    asv, webp, classes = fixture_rows()
    asv.append(dict(asv[0]))
    with pytest.raises(ValueError, match="duplicate ASV locator"):
        build_stratified_records(asv, webp, classes)


def test_opening_class_scope_must_match_all_webp_rows() -> None:
    asv, webp, classes = fixture_rows()
    classes.pop("MAT 1:4")
    with pytest.raises(ValueError, match="opening-class locator mismatch"):
        build_stratified_records(asv, webp, classes)


def test_text_realization_must_contain_nonempty_text() -> None:
    asv, webp, classes = fixture_rows()
    asv[0]["source_text"] = None
    with pytest.raises(ValueError, match="missing source text"):
        build_stratified_records(asv, webp, classes)


def test_record_stream_is_deterministic_under_input_order() -> None:
    asv, webp, classes = fixture_rows()
    forward = build_stratified_records(asv, webp, classes)
    reverse = build_stratified_records(
        list(reversed(asv)), list(reversed(webp)), classes
    )
    assert forward == reverse
    assert summarize_records(forward) == summarize_records(reverse)


def test_report_contains_no_source_wording_or_locator_list() -> None:
    asv, webp, classes = fixture_rows()
    summary = summarize_records(build_stratified_records(asv, webp, classes))
    rendered = json.dumps(summary, sort_keys=True)

    assert summary["scripture_text_reported"] is False
    assert summary["token_lists_reported"] is False
    assert summary["locator_identifiers_reported"] is False
    assert summary["parser_behavior_changed"] is False
    assert summary["text_boundaries_defined"] is False
    assert summary["corpus_mutation"] == "not-performed"
    assert "one two three four" not in rendered
    assert "three equal words" not in rendered
    assert "MAT 1:1" not in rendered
    assert "source_text" not in rendered


def test_expected_summary_mismatch_fails_closed(tmp_path: Path) -> None:
    observed = {"contract": "v1", "count": 2}
    expected = {"contract": "v1", "count": 1}
    with pytest.raises(ValueError, match="token stratification mismatch"):
        assert_expected(observed, expected)
