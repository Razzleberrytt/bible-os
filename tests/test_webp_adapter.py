from __future__ import annotations

import io
import zipfile

import pytest

from bible_os.importers.webp_usfm import WebpUsfmAdapter, extract_visible_text
from scripts.webp_adapter_smoke import compare_baseline


def make_archive(files: dict[str, str]) -> zipfile.ZipFile:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    buffer.seek(0)
    archive = zipfile.ZipFile(buffer)
    archive._fixture_buffer = buffer  # keep the in-memory file alive for the test
    return archive


def test_probe_and_records_use_canonical_book_order():
    archive = make_archive(
        {
            "z-gen.usfm": "\\id GEN Synthetic\n\\c 1\n\\v 1 first\ncontinued\n\\v 2 second\n",
            "a-exo.usfm": "\\id EXO Synthetic\n\\c 1\n\\v 1 exodus\n",
            "front.sfm": "\\id FRT Synthetic front matter\n",
        }
    )
    adapter = WebpUsfmAdapter()
    probe = adapter.probe(archive)
    records = list(adapter.iter_records(archive))

    assert probe.compatible is True
    assert probe.recognized_books == ("GEN", "EXO")
    assert probe.unrecognized_book_ids == ("FRT",)
    assert [record.source_locator for record in records] == [
        "GEN 1:1",
        "GEN 1:2",
        "EXO 1:1",
    ]
    assert records[0].raw_payload == "first\ncontinued"
    assert [record.source_sequence for record in records] == [1, 2, 3]


def test_visible_text_excludes_notes_and_control_markers():
    assert extract_visible_text(r"\f + \fr 16:25 \ft A relocation note.\f*") == ""
    assert extract_visible_text(r"\p") == ""
    assert extract_visible_text(r"\wj Lord\wj* spoke") == "Lord spoke"
    assert (
        extract_visible_text(r"Main text. \f + \fr 1:1 \ft Note text.\f*")
        == "Main text."
    )
    assert extract_visible_text(r"\w Word|lemma=G3056 strong=G3056\w*") == "Word"


def test_baseline_comparison_reports_reference_only_deltas():
    archive = make_archive(
        {
            "gen.usfm": "\\id GEN Synthetic\n\\c 1\n\\v 1 one\n\\v 2 two\n\\v 3 extra\n",
            "exo.usfm": "\\id EXO Synthetic\n\\c 1\n\\v 1 one\n",
        }
    )
    records = list(WebpUsfmAdapter().iter_records(archive))
    result = compare_baseline(
        records,
        {
            "name": "Synthetic baseline",
            "source_release": "synthetic",
            "reference_count": 3,
            "books": {"GEN": [2], "EXO": [1]},
        },
    )

    assert result["versification_delta_count"] == 1
    assert result["versification_deltas"] == [
        {
            "book": "GEN",
            "chapter": 1,
            "missing_labels": [],
            "extra_labels": [3],
        }
    ]
    assert result["non_numeric_verse_labels"] == []


def test_duplicate_book_ids_are_rejected():
    archive = make_archive(
        {
            "one.usfm": "\\id GEN Synthetic\n\\c 1\n\\v 1 one\n",
            "two.usfm": "\\id GEN Synthetic\n\\c 1\n\\v 2 two\n",
        }
    )
    with pytest.raises(ValueError, match="duplicate USFM book id"):
        WebpUsfmAdapter().probe(archive)


def test_duplicate_verse_loci_are_rejected():
    archive = make_archive(
        {
            "gen.usfm": "\\id GEN Synthetic\n\\c 1\n\\v 1 one\n\\v 1 duplicate\n",
        }
    )
    with pytest.raises(ValueError, match="duplicate verse locus"):
        list(WebpUsfmAdapter().iter_records(archive))


def test_verse_before_chapter_is_rejected():
    archive = make_archive(
        {"gen.usfm": "\\id GEN Synthetic\n\\v 1 no chapter\n"}
    )
    with pytest.raises(ValueError, match="verse before chapter"):
        list(WebpUsfmAdapter().iter_records(archive))
