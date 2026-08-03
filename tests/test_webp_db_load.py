from __future__ import annotations

import io
import re
import zipfile

from bible_os.identity import stable_id
from scripts.webp_db_load import CORPUS_ID, IDENTITY_NAMESPACE, source_rows


def make_archive(content: str) -> zipfile.ZipFile:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("synthetic.usfm", content)
    buffer.seek(0)
    archive = zipfile.ZipFile(buffer)
    archive._fixture_buffer = buffer
    return archive


def test_stable_ids_are_namespaced_and_reproducible():
    first = stable_id("pas", "namespace-v1", "GEN.1.1")
    assert first == stable_id("pas", "namespace-v1", "GEN.1.1")
    assert first != stable_id("pas", "namespace-v2", "GEN.1.1")
    assert first != stable_id("pas", "namespace-v1", "GEN.1.2")
    assert re.fullmatch(r"pas_[a-z2-7]{20}", first)


def test_source_rows_type_marker_only_payloads_without_publishing_ids():
    archive = make_archive(
        "\\id GEN Synthetic\n"
        "\\c 1\n"
        "\\v 1 Visible text.\n"
        "\\v 2 \\f + \\fr 1:2 \\ft Note only.\\f*\n"
    )
    rows = source_rows(archive)

    assert [row["realization_type"] for row in rows] == ["text", "empty-placeholder"]
    assert rows[0]["source_text"] == "Visible text."
    assert rows[1]["source_text"] is None
    assert rows[0]["text_unit_id"] == stable_id(
        "txt", IDENTITY_NAMESPACE, f"{CORPUS_ID}|GEN.1.1"
    )
    assert rows[0]["passage_id"] != rows[0]["reference_id"]


def test_source_rows_keep_all_mappings_provisional():
    archive = make_archive("\\id ROM Synthetic\n\\c 14\n\\v 24 Text.\n")
    row = source_rows(archive)[0]
    assert row["mapping_id"] == stable_id(
        "prm",
        IDENTITY_NAMESPACE,
        f"{row['passage_id']}|{row['reference_id']}|uncertain",
    )
