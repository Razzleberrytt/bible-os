from __future__ import annotations

import argparse
import json
import os
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from bible_os.exports import verify_reproducible_ndjson
from bible_os.identity import stable_id
from bible_os.importers.webp_usfm import BOOK_ORDER
from scripts.asv_full_ci import (
    ARTIFACT_PATH as ASV_ARTIFACT_PATH,
    CORPUS_ID as ASV_CORPUS_ID,
    VERSIFICATION_ID as ASV_VERSIFICATION_ID,
    WORK_ID as ASV_WORK_ID,
    load_database as load_asv_database,
    source_rows as asv_source_rows,
)
from scripts.webp_adapter_smoke import download_verified_archive, load_json
from scripts.webp_db_load import (
    ARTIFACT_PATH as WEBP_ARTIFACT_PATH,
    CORPUS_ID as WEBP_CORPUS_ID,
    TARGET_PATH as WEBP_TARGET_PATH,
    VERSIFICATION_ID as WEBP_VERSIFICATION_ID,
    WORK_ID as WEBP_WORK_ID,
    load_database as load_webp_database,
    scalar,
    source_rows as webp_source_rows,
)


ROOT = Path(__file__).resolve().parents[1]
ASV_TARGET_PATH = ROOT / "registry" / "acquisitions" / "eng-asv-usfm.json"
CANDIDATE_NAMESPACE = "bible-os:asv-webp-locator-candidate:v1"
BOOK_INDEX = {code: index for index, code in enumerate(BOOK_ORDER)}


def locator(row: dict[str, Any]) -> str:
    return f"{row['book_code']} {row['chapter']}:{row['verse']}"


def locator_sort_key(value: str) -> tuple[int, int, int]:
    book, chapter_verse = value.split(" ", 1)
    chapter, verse = chapter_verse.split(":", 1)
    return BOOK_INDEX[book], int(chapter), int(verse)


def _side(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "reference_id": row["reference_id"],
        "passage_id": row["passage_id"],
        "realization_type": row["realization_type"],
    }


def build_candidate_records(
    asv_rows: list[dict[str, Any]], webp_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    asv_by_locator = {locator(row): row for row in asv_rows}
    webp_by_locator = {locator(row): row for row in webp_rows}
    if len(asv_by_locator) != len(asv_rows):
        raise ValueError("duplicate ASV locator detected")
    if len(webp_by_locator) != len(webp_rows):
        raise ValueError("duplicate WEBP locator detected")

    records: list[dict[str, Any]] = []
    for value in sorted(set(asv_by_locator) | set(webp_by_locator), key=locator_sort_key):
        asv = asv_by_locator.get(value)
        webp = webp_by_locator.get(value)
        if asv is None:
            candidate_class = "webp-only-locus"
            exceptional = True
        elif webp is None:
            candidate_class = "asv-only-locus"
            exceptional = True
        elif asv["realization_type"] != webp["realization_type"]:
            candidate_class = "realization-mismatch-observation"
            exceptional = True
        else:
            candidate_class = "same-locator-observation"
            exceptional = False

        records.append(
            {
                "candidate_version": "1.0.0",
                "candidate_id": stable_id(
                    "can", CANDIDATE_NAMESPACE, f"{value}|{candidate_class}"
                ),
                "candidate_class": candidate_class,
                "locator": value,
                "asv": _side(asv),
                "webp": _side(webp),
                "exceptional": exceptional,
                "suggested_review_kind": "uncertain",
                "queue_mutation": False,
                "mapping_authority": "none",
                "execution_eligible": False,
                "publication_eligible": False,
            }
        )
    return records


def summarize_candidates(records: list[dict[str, Any]]) -> dict[str, Any]:
    class_counts = Counter(record["candidate_class"] for record in records)
    realization_counts: Counter[str] = Counter()
    for record in records:
        asv = record["asv"]
        webp = record["webp"]
        if asv is not None and webp is not None:
            realization_counts[
                f"{asv['realization_type']}|{webp['realization_type']}"
            ] += 1

    fingerprint = verify_reproducible_ndjson(records)
    exceptions = [
        {
            "candidate_id": record["candidate_id"],
            "candidate_class": record["candidate_class"],
            "locator": record["locator"],
            "asv_realization_type": (
                record["asv"]["realization_type"] if record["asv"] else None
            ),
            "webp_realization_type": (
                record["webp"]["realization_type"] if record["webp"] else None
            ),
        }
        for record in records
        if record["exceptional"]
    ]
    return {
        **fingerprint,
        "candidate_namespace": CANDIDATE_NAMESPACE,
        "common_locator_count": (
            class_counts["same-locator-observation"]
            + class_counts["realization-mismatch-observation"]
        ),
        "same_locator_same_realization_count": class_counts[
            "same-locator-observation"
        ],
        "both_text_count": realization_counts["text|text"],
        "both_placeholder_count": realization_counts[
            "empty-placeholder|empty-placeholder"
        ],
        "asv_placeholder_webp_text_count": realization_counts[
            "empty-placeholder|text"
        ],
        "asv_text_webp_placeholder_count": realization_counts[
            "text|empty-placeholder"
        ],
        "realization_mismatch_count": class_counts[
            "realization-mismatch-observation"
        ],
        "asv_only_locator_count": class_counts["asv-only-locus"],
        "webp_only_locator_count": class_counts["webp-only-locus"],
        "exceptional_candidate_count": len(exceptions),
        "exceptional_candidates": exceptions,
        "queue_documents_written": False,
        "mapping_authority": "none",
        "execution_eligible": False,
        "publication_eligible": False,
        "retention": "candidate records fingerprinted in memory; only exceptional locator metadata is reported",
    }


def assert_expected(observed: dict[str, Any], expected: dict[str, Any]) -> None:
    for key, expected_value in expected.items():
        if key.startswith("_"):
            continue
        actual = observed.get(key)
        if actual != expected_value:
            raise ValueError(
                f"ASV/WEBP candidate profile mismatch for {key}: "
                f"expected {expected_value!r}, observed {actual!r}"
            )


def validate_combined_database(database_url: str) -> dict[str, Any]:
    import psycopg

    expected_total = 31_102 + 31_103
    expected_textual = 31_086 + 31_098
    expected_placeholders = 16 + 5

    with psycopg.connect(database_url) as connection, connection.cursor() as cur:
        counts = {
            "sources": scalar(cur, "SELECT count(*) FROM source"),
            "artifacts": scalar(cur, "SELECT count(*) FROM source_artifact"),
            "works": scalar(cur, "SELECT count(*) FROM work"),
            "books": scalar(cur, "SELECT count(*) FROM book"),
            "corpora": scalar(cur, "SELECT count(*) FROM corpus"),
            "passages": scalar(cur, "SELECT count(*) FROM passage"),
            "references": scalar(cur, "SELECT count(*) FROM versification_reference"),
            "internal_source_locus_mappings": scalar(
                cur, "SELECT count(*) FROM passage_reference_mapping"
            ),
            "text_units": scalar(cur, "SELECT count(*) FROM text_unit"),
            "textual": scalar(
                cur,
                "SELECT count(*) FROM text_unit WHERE realization_type='text'",
            ),
            "placeholders": scalar(
                cur,
                "SELECT count(*) FROM text_unit WHERE realization_type='empty-placeholder'",
            ),
            "shared_passage_identities": scalar(
                cur,
                """SELECT count(DISTINCT a.passage_id)
                   FROM text_unit a JOIN text_unit b ON b.passage_id=a.passage_id
                   WHERE a.corpus_id=%s AND b.corpus_id=%s""",
                (ASV_CORPUS_ID, WEBP_CORPUS_ID),
            ),
            "shared_reference_identities": scalar(
                cur,
                """SELECT count(DISTINCT a.source_reference_id)
                   FROM text_unit a JOIN text_unit b
                     ON b.source_reference_id=a.source_reference_id
                   WHERE a.corpus_id=%s AND b.corpus_id=%s""",
                (ASV_CORPUS_ID, WEBP_CORPUS_ID),
            ),
            "cross_translation_passage_mappings": scalar(
                cur,
                """SELECT count(*)
                   FROM passage_reference_mapping m
                   JOIN passage p ON p.passage_id=m.passage_id
                   JOIN book b ON b.book_id=p.book_id
                   JOIN versification_reference r
                     ON r.versification_reference_id=m.versification_reference_id
                   WHERE (b.work_id=%s AND r.versification_system_id<>%s)
                      OR (b.work_id=%s AND r.versification_system_id<>%s)""",
                (
                    ASV_WORK_ID,
                    ASV_VERSIFICATION_ID,
                    WEBP_WORK_ID,
                    WEBP_VERSIFICATION_ID,
                ),
            ),
            "reference_relations": scalar(cur, "SELECT count(*) FROM reference_relation"),
            "alignments": scalar(cur, "SELECT count(*) FROM alignment"),
            "releases": scalar(cur, "SELECT count(*) FROM dataset_release"),
            "publication_enabled": scalar(
                cur,
                "SELECT count(*) FROM corpus WHERE metadata->>'publication_eligible'='true'",
            ),
        }

    expected = {
        "sources": 2,
        "artifacts": 2,
        "works": 2,
        "books": 132,
        "corpora": 2,
        "passages": expected_total,
        "references": expected_total,
        "internal_source_locus_mappings": expected_total,
        "text_units": expected_total,
        "textual": expected_textual,
        "placeholders": expected_placeholders,
        "shared_passage_identities": 0,
        "shared_reference_identities": 0,
        "cross_translation_passage_mappings": 0,
        "reference_relations": 0,
        "alignments": 0,
        "releases": 0,
        "publication_enabled": 0,
    }
    if counts != expected:
        raise ValueError(
            f"combined ASV/WEBP database mismatch: expected {expected}, observed {counts}"
        )
    return {
        **counts,
        "asv_work_id": ASV_WORK_ID,
        "webp_work_id": WEBP_WORK_ID,
        "asv_versification_system_id": ASV_VERSIFICATION_ID,
        "webp_versification_system_id": WEBP_VERSIFICATION_ID,
        "asv_corpus_id": ASV_CORPUS_ID,
        "webp_corpus_id": WEBP_CORPUS_ID,
        "candidate_rows_persisted": 0,
        "queue_documents_written": False,
        "cross_translation_mappings_created": 0,
        "execution_eligible": False,
        "publication_eligible": False,
    }


def run(database_url: str, expected_path: Path | None = None) -> dict[str, Any]:
    asv_target = load_json(ASV_TARGET_PATH)
    asv_artifact = load_json(ASV_ARTIFACT_PATH)
    webp_target = load_json(WEBP_TARGET_PATH)
    webp_artifact = load_json(WEBP_ARTIFACT_PATH)

    with tempfile.TemporaryDirectory(prefix="bible-os-asv-webp-candidates-") as temp_dir:
        temp_root = Path(temp_dir)
        asv_archive_path = temp_root / asv_artifact["filename"]
        webp_archive_path = temp_root / webp_artifact["filename"]
        download_verified_archive(asv_target, asv_archive_path)
        download_verified_archive(webp_target, webp_archive_path)
        with zipfile.ZipFile(asv_archive_path) as archive:
            asv_rows = asv_source_rows(archive)
        with zipfile.ZipFile(webp_archive_path) as archive:
            webp_rows = webp_source_rows(archive)

    candidate_records = build_candidate_records(asv_rows, webp_rows)
    candidate_report = summarize_candidates(candidate_records)
    if expected_path is not None:
        assert_expected(candidate_report, load_json(expected_path))
        candidate_report["expected_profile"] = str(expected_path)
        candidate_report["profile_status"] = "matched"
    else:
        candidate_report["profile_status"] = "observed-unpinned"

    load_webp_database(database_url, webp_rows)
    load_asv_database(database_url, asv_rows)
    database_report = validate_combined_database(database_url)
    return {
        "status": "passed",
        "experiment": "asv-webp-source-locator-candidates-v1",
        "candidate_stream": candidate_report,
        "database": database_report,
        "corpus_bytes_committed": False,
        "scripture_text_reported": False,
        "queue_documents_written": False,
        "cross_translation_mappings_created": 0,
        "execution_eligible": False,
        "publication_eligible": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate inert ASV/WEBP locator candidates in a combined ephemeral database"
    )
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--expected", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")

    report = run(args.database_url, args.expected)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
