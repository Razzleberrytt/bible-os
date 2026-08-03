from __future__ import annotations

from bible_os.importers.base import SourceRecord
from scripts.asv_adapter_smoke import AsvUsfmAdapter, compare_locator_sets


def record(sequence: int, locator: tuple[str, int, str], text: str) -> SourceRecord:
    book, chapter, verse = locator
    return SourceRecord(
        source_file=f"{book}.usfm",
        book_code=book,
        chapter=chapter,
        verse_label=verse,
        source_sequence=sequence,
        raw_payload=text,
    )


def test_asv_adapter_has_source_specific_identity():
    assert AsvUsfmAdapter().name == "eng-asv-usfm-v1"


def test_locator_comparison_is_deterministic_and_text_free():
    asv_records = [
        record(1, ("GEN", 1, "1"), "ASV first text"),
        record(2, ("GEN", 1, "2"), "ASV second text"),
        record(3, ("ROM", 16, "25"), "ASV-only text"),
    ]
    webp_records = [
        record(1, ("GEN", 1, "1"), "WEBP first text"),
        record(2, ("GEN", 1, "2"), "WEBP second text"),
        record(3, ("ROM", 14, "24"), "WEBP-only text"),
    ]

    report = compare_locator_sets(asv_records, webp_records)

    assert report["common_locator_count"] == 2
    assert report["asv_only_locator_count"] == 1
    assert report["asv_only_locators"] == ["ROM 16:25"]
    assert report["webp_only_locator_count"] == 1
    assert report["webp_only_locators"] == ["ROM 14:24"]

    rendered = repr(report)
    assert "ASV first text" not in rendered
    assert "ASV-only text" not in rendered
    assert "WEBP first text" not in rendered
    assert "WEBP-only text" not in rendered


def test_locator_comparison_preserves_source_order_for_differences():
    asv_records = [
        record(1, ("GEN", 1, "1"), "one"),
        record(2, ("GEN", 1, "3"), "three"),
        record(3, ("GEN", 1, "2"), "two"),
    ]
    webp_records = [record(1, ("GEN", 1, "1"), "one")]

    report = compare_locator_sets(asv_records, webp_records)

    assert report["asv_only_locators"] == ["GEN 1:3", "GEN 1:2"]
    assert report["comparison_text_retention"].startswith("locator identities only")
