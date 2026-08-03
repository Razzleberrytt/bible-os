from __future__ import annotations

import json
from pathlib import Path

from bible_os.identity import stable_id
from scripts.asv_full_ci import (
    ARTIFACT_PATH,
    CORPUS_ID,
    EVENT_PATH,
    IDENTITY_NAMESPACE,
    SOURCE_PATH,
    VERSIFICATION_ID,
    WORK_ID,
    export_records,
)
from scripts.webp_db_load import (
    CORPUS_ID as WEBP_CORPUS_ID,
    IDENTITY_NAMESPACE as WEBP_IDENTITY_NAMESPACE,
    VERSIFICATION_ID as WEBP_VERSIFICATION_ID,
    WORK_ID as WEBP_WORK_ID,
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_asv_registry_chain_is_internally_consistent():
    source = load(SOURCE_PATH)
    event = load(EVENT_PATH)
    artifact = load(ARTIFACT_PATH)

    assert source["source_id"] == "src_engasv1901public"
    assert event["source_id"] == source["source_id"]
    assert artifact["source_id"] == source["source_id"]
    assert artifact["acquisition_event_id"] == event["event_id"]
    assert artifact["sha256"] == event["observed_sha256"]
    assert artifact["byte_size"] == event["observed_bytes"]
    assert artifact["verification_status"] == "verified"
    assert artifact["license_assertion"]["status"] == "public-domain"


def test_asv_top_level_identities_are_disjoint_from_webp():
    assert IDENTITY_NAMESPACE != WEBP_IDENTITY_NAMESPACE
    assert WORK_ID != WEBP_WORK_ID
    assert VERSIFICATION_ID != WEBP_VERSIFICATION_ID
    assert CORPUS_ID != WEBP_CORPUS_ID


def test_same_locator_gets_source_owned_asv_identities():
    osis = "GEN.1.1"
    asv_passage = stable_id("pas", IDENTITY_NAMESPACE, f"source-locus|{osis}")
    webp_passage = stable_id("pas", WEBP_IDENTITY_NAMESPACE, f"source-locus|{osis}")
    asv_reference = stable_id("ref", IDENTITY_NAMESPACE, f"reference|{osis}")
    webp_reference = stable_id("ref", WEBP_IDENTITY_NAMESPACE, f"reference|{osis}")

    assert asv_passage != webp_passage
    assert asv_reference != webp_reference


def test_normalized_export_is_inert_and_source_owned():
    row = {
        "sequence": 1,
        "source_file": "01-GEN.usfm",
        "book_code": "GEN",
        "chapter": 1,
        "verse": 1,
        "osis": "GEN.1.1",
        "display_reference": "Genesis 1:1",
        "passage_id": stable_id("pas", IDENTITY_NAMESPACE, "source-locus|GEN.1.1"),
        "reference_id": stable_id("ref", IDENTITY_NAMESPACE, "reference|GEN.1.1"),
        "mapping_id": "prm_asvsynthetic01",
        "text_unit_id": stable_id("txt", IDENTITY_NAMESPACE, f"{CORPUS_ID}|GEN.1.1"),
        "realization_type": "text",
        "source_text": "synthetic fixture text",
        "raw_payload_sha256": "a" * 64,
        "source_text_sha256": "b" * 64,
    }

    exported = export_records([row])

    assert len(exported) == 1
    assert exported[0]["identity_namespace"] == IDENTITY_NAMESPACE
    assert exported[0]["corpus_id"] == CORPUS_ID
    assert exported[0]["mapping_state"] == "uncertain/unreviewed"
    assert exported[0]["publication_eligible"] is False
    assert row["source_text"] == "synthetic fixture text"
