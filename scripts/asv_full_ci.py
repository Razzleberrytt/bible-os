from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from bible_os.exports import verify_reproducible_ndjson
from bible_os.identity import stable_id
from bible_os.importers.webp_usfm import BOOK_ORDER, extract_visible_text
from scripts.asv_adapter_smoke import AsvUsfmAdapter
from scripts.webp_adapter_smoke import download_verified_archive, load_json
from scripts.webp_db_load import BOOK_NAMES, load_registry, scalar

ROOT = Path(__file__).resolve().parents[1]
TARGET_PATH = ROOT / "registry" / "acquisitions" / "eng-asv-usfm.json"
SOURCE_PATH = ROOT / "registry" / "sources" / "eng-asv.source.json"
EVENT_PATH = ROOT / "registry" / "acquisition-events" / "eng-asv-usfm-20260803.json"
ARTIFACT_PATH = ROOT / "registry" / "artifacts" / "eng-asv-usfm.artifact.json"
PROFILE_PATH = ROOT / "registry" / "import-profiles" / "eng-asv-usfm-smoke.json"

IDENTITY_NAMESPACE = "bible-os:ephemeral-asv-source-locus:v1"
WORK_ID = stable_id("wrk", IDENTITY_NAMESPACE, "american-standard-version-1901-66")
VERSIFICATION_ID = stable_id("vrs", IDENTITY_NAMESPACE, "eng-asv-source-references")
CORPUS_ID = stable_id("cor", IDENTITY_NAMESPACE, "eng-asv-parse-smoke")


def source_rows(archive: zipfile.ZipFile) -> list[dict[str, Any]]:
    adapter = AsvUsfmAdapter()
    rows: list[dict[str, Any]] = []
    for record in adapter.iter_records(archive):
        if not record.verse_label.isdigit():
            raise ValueError(f"non-numeric verse label is not supported: {record.source_locator}")
        verse = int(record.verse_label)
        osis = f"{record.book_code}.{record.chapter}.{verse}"
        visible_text = extract_visible_text(record.raw_payload)
        realization_type = "text" if visible_text else "empty-placeholder"
        passage_id = stable_id("pas", IDENTITY_NAMESPACE, f"source-locus|{osis}")
        reference_id = stable_id("ref", IDENTITY_NAMESPACE, f"reference|{osis}")
        rows.append(
            {
                "sequence": record.source_sequence,
                "book_code": record.book_code,
                "book_id": stable_id("bok", IDENTITY_NAMESPACE, record.book_code),
                "chapter": record.chapter,
                "verse": verse,
                "osis": osis,
                "display_reference": f"{BOOK_NAMES[record.book_code]} {record.chapter}:{verse}",
                "passage_id": passage_id,
                "reference_id": reference_id,
                "mapping_id": stable_id(
                    "prm", IDENTITY_NAMESPACE, f"{passage_id}|{reference_id}|uncertain"
                ),
                "text_unit_id": stable_id("txt", IDENTITY_NAMESPACE, f"{CORPUS_ID}|{osis}"),
                "realization_type": realization_type,
                "source_text": visible_text or None,
                "raw_payload_sha256": hashlib.sha256(
                    record.raw_payload.encode("utf-8")
                ).hexdigest(),
                "source_text_sha256": (
                    hashlib.sha256(visible_text.encode("utf-8")).hexdigest()
                    if visible_text
                    else None
                ),
                "source_file": record.source_file,
            }
        )
    return rows


def export_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "schema_version": "0.1.0-parse-smoke",
            "identity_namespace": IDENTITY_NAMESPACE,
            "corpus_id": CORPUS_ID,
            "source_sequence": row["sequence"],
            "source_file": row["source_file"],
            "book_code": row["book_code"],
            "chapter": row["chapter"],
            "verse": row["verse"],
            "osis": row["osis"],
            "display_reference": row["display_reference"],
            "passage_id": row["passage_id"],
            "reference_id": row["reference_id"],
            "mapping_id": row["mapping_id"],
            "text_unit_id": row["text_unit_id"],
            "realization_type": row["realization_type"],
            "source_text": row["source_text"],
            "raw_payload_sha256": row["raw_payload_sha256"],
            "source_text_sha256": row["source_text_sha256"],
            "mapping_state": "uncertain/unreviewed",
            "publication_eligible": False,
        }
        for row in rows
    ]


def assert_expected(metrics: dict[str, Any], expected: dict[str, Any]) -> None:
    for key, expected_value in expected.items():
        if key.startswith("_"):
            continue
        observed = metrics.get(key)
        if observed != expected_value:
            raise ValueError(
                f"ASV normalized export fingerprint mismatch for {key}: "
                f"expected {expected_value!r}, observed {observed!r}"
            )


def load_database(database_url: str, rows: list[dict[str, Any]]) -> None:
    import psycopg
    from psycopg.types.json import Jsonb

    source = load_json(SOURCE_PATH)
    event = load_json(EVENT_PATH)
    artifact = load_json(ARTIFACT_PATH)

    with psycopg.connect(database_url) as connection, connection.cursor() as cur:
        load_registry(cur, source=source, event=event, artifact=artifact)
        cur.execute(
            "INSERT INTO work (work_id,canonical_name,metadata) VALUES (%s,%s,%s)",
            (
                WORK_ID,
                "American Standard Version (1901) — provisional source-locus staging work",
                Jsonb(
                    {
                        "ephemeral": True,
                        "identity_status": "asv-source-locus-only",
                        "cross_translation_identity": False,
                        "publication_eligible": False,
                    }
                ),
            ),
        )
        cur.executemany(
            """INSERT INTO book (book_id,work_id,canonical_name,metadata)
               VALUES (%s,%s,%s,%s)""",
            [
                (
                    stable_id("bok", IDENTITY_NAMESPACE, code),
                    WORK_ID,
                    BOOK_NAMES[code],
                    Jsonb(
                        {
                            "book_code": code,
                            "ephemeral": True,
                            "identity_status": "asv-source-locus-only",
                        }
                    ),
                )
                for code in BOOK_ORDER
            ],
        )
        cur.execute(
            """INSERT INTO versification_system
               (versification_system_id,name,version,authority)
               VALUES (%s,%s,%s,%s)""",
            (
                VERSIFICATION_ID,
                "American Standard Version (1901) source references",
                artifact["sha256"][:16],
                "eBible.org artifact registry",
            ),
        )
        cur.execute(
            """INSERT INTO corpus
               (corpus_id,source_id,name,upstream_version,language_codes,metadata)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (
                CORPUS_ID,
                source["source_id"],
                "ASV 1901 ephemeral parse-smoke corpus",
                artifact["upstream_version"],
                source["language_codes"],
                Jsonb(
                    {
                        "ephemeral": True,
                        "pipeline_stage": "parse-smoke",
                        "publication_eligible": False,
                        "adapter": "eng-asv-usfm-v1",
                        "artifact_sha256": artifact["sha256"],
                        "cross_translation_mappings": "none",
                    }
                ),
            ),
        )
        cur.execute(
            "INSERT INTO corpus_artifact (corpus_id,artifact_id) VALUES (%s,%s)",
            (CORPUS_ID, artifact["artifact_id"]),
        )
        cur.executemany(
            """INSERT INTO passage
               (passage_id,book_id,parent_passage_id,passage_kind,sort_ordinal,metadata)
               VALUES (%s,%s,NULL,'verse',%s,%s)""",
            [
                (
                    row["passage_id"],
                    row["book_id"],
                    row["sequence"],
                    Jsonb(
                        {
                            "osis": row["osis"],
                            "ephemeral": True,
                            "identity_status": "asv-source-locus-only",
                            "cross_translation_identity": False,
                            "publication_eligible": False,
                        }
                    ),
                )
                for row in rows
            ],
        )
        cur.executemany(
            """INSERT INTO versification_reference
               (versification_reference_id,versification_system_id,book_code,chapter,verse,
                subverse,display_reference,source_locator)
               VALUES (%s,%s,%s,%s,%s,NULL,%s,%s)""",
            [
                (
                    row["reference_id"],
                    VERSIFICATION_ID,
                    row["book_code"],
                    row["chapter"],
                    row["verse"],
                    row["display_reference"],
                    Jsonb(
                        {
                            "osis": row["osis"],
                            "source_sequence": row["sequence"],
                            "source_file": row["source_file"],
                        }
                    ),
                )
                for row in rows
            ],
        )
        cur.executemany(
            """INSERT INTO passage_reference_mapping
               (passage_reference_mapping_id,passage_id,versification_reference_id,
                relation_type,confidence,method,review_state,evidence)
               VALUES (%s,%s,%s,'uncertain',0.0,'rule-based','unreviewed',%s)""",
            [
                (
                    row["mapping_id"],
                    row["passage_id"],
                    row["reference_id"],
                    Jsonb(
                        [
                            {
                                "stage": "ephemeral-asv-source-locus-load",
                                "reason": "ASV-owned staging identity only; canonical and cross-translation mapping pending",
                                "cross_translation_mapping": False,
                                "publication_eligible": False,
                            }
                        ]
                    ),
                )
                for row in rows
            ],
        )
        cur.executemany(
            """INSERT INTO text_unit
               (text_unit_id,corpus_id,passage_id,source_reference_id,realization_type,
                source_text,normalized_text,source_sequence,metadata)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [
                (
                    row["text_unit_id"],
                    CORPUS_ID,
                    row["passage_id"],
                    row["reference_id"],
                    row["realization_type"],
                    row["source_text"],
                    row["source_text"],
                    row["sequence"],
                    Jsonb(
                        {
                            "ephemeral": True,
                            "pipeline_stage": "parse-smoke",
                            "publication_eligible": False,
                            "source_file": row["source_file"],
                            "raw_payload_sha256": row["raw_payload_sha256"],
                            "source_text_sha256": row["source_text_sha256"],
                        }
                    ),
                )
                for row in rows
            ],
        )


def validate_database(
    database_url: str, profile: dict[str, Any], artifact_id: str
) -> dict[str, Any]:
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cur:
        counts = {
            "sources": scalar(cur, "SELECT count(*) FROM source WHERE source_id=%s", ("src_engasv1901public",)),
            "artifacts": scalar(cur, "SELECT count(*) FROM source_artifact WHERE artifact_id=%s", (artifact_id,)),
            "books": scalar(cur, "SELECT count(*) FROM book WHERE work_id=%s", (WORK_ID,)),
            "passages": scalar(
                cur,
                """SELECT count(*) FROM passage p
                   JOIN book b ON b.book_id=p.book_id WHERE b.work_id=%s""",
                (WORK_ID,),
            ),
            "references": scalar(
                cur,
                "SELECT count(*) FROM versification_reference WHERE versification_system_id=%s",
                (VERSIFICATION_ID,),
            ),
            "mappings": scalar(
                cur,
                """SELECT count(*) FROM passage_reference_mapping m
                   JOIN versification_reference r
                     ON r.versification_reference_id=m.versification_reference_id
                   WHERE r.versification_system_id=%s""",
                (VERSIFICATION_ID,),
            ),
            "uncertain_unreviewed_mappings": scalar(
                cur,
                """SELECT count(*) FROM passage_reference_mapping m
                   JOIN versification_reference r
                     ON r.versification_reference_id=m.versification_reference_id
                   WHERE r.versification_system_id=%s
                     AND m.relation_type='uncertain' AND m.confidence=0
                     AND m.review_state='unreviewed'""",
                (VERSIFICATION_ID,),
            ),
            "text_units": scalar(cur, "SELECT count(*) FROM text_unit WHERE corpus_id=%s", (CORPUS_ID,)),
            "textual": scalar(
                cur,
                """SELECT count(*) FROM text_unit
                   WHERE corpus_id=%s AND realization_type='text'
                     AND source_text IS NOT NULL AND normalized_text IS NOT NULL""",
                (CORPUS_ID,),
            ),
            "placeholders": scalar(
                cur,
                """SELECT count(*) FROM text_unit
                   WHERE corpus_id=%s AND realization_type='empty-placeholder'
                     AND source_text IS NULL AND normalized_text IS NULL""",
                (CORPUS_ID,),
            ),
            "orphans": scalar(
                cur,
                """SELECT count(*) FROM text_unit t
                   LEFT JOIN passage p ON p.passage_id=t.passage_id
                   LEFT JOIN versification_reference r
                     ON r.versification_reference_id=t.source_reference_id
                   WHERE t.corpus_id=%s
                     AND (p.passage_id IS NULL OR r.versification_reference_id IS NULL)""",
                (CORPUS_ID,),
            ),
            "foreign_passage_links": scalar(
                cur,
                """SELECT count(*) FROM text_unit t
                   JOIN passage p ON p.passage_id=t.passage_id
                   JOIN book b ON b.book_id=p.book_id
                   WHERE t.corpus_id=%s AND b.work_id<>%s""",
                (CORPUS_ID, WORK_ID),
            ),
            "cross_corpus_passage_sharing": scalar(
                cur,
                """SELECT count(DISTINCT own.passage_id) FROM text_unit own
                   JOIN text_unit other ON other.passage_id=own.passage_id
                                      AND other.corpus_id<>own.corpus_id
                   WHERE own.corpus_id=%s""",
                (CORPUS_ID,),
            ),
            "reference_relations": scalar(
                cur,
                """SELECT count(*) FROM reference_relation rr
                   JOIN versification_reference s
                     ON s.versification_reference_id=rr.source_reference_id
                   JOIN versification_reference t
                     ON t.versification_reference_id=rr.target_reference_id
                   WHERE s.versification_system_id=%s OR t.versification_system_id=%s""",
                (VERSIFICATION_ID, VERSIFICATION_ID),
            ),
            "alignments": scalar(cur, "SELECT count(*) FROM alignment"),
            "releases": scalar(cur, "SELECT count(*) FROM dataset_release"),
            "artifact_links": scalar(
                cur,
                "SELECT count(*) FROM corpus_artifact WHERE corpus_id=%s AND artifact_id=%s",
                (CORPUS_ID, artifact_id),
            ),
            "raw_payload_hashes": scalar(
                cur,
                """SELECT count(*) FROM text_unit
                   WHERE corpus_id=%s AND metadata ? 'raw_payload_sha256'""",
                (CORPUS_ID,),
            ),
            "source_text_hashes": scalar(
                cur,
                """SELECT count(*) FROM text_unit
                   WHERE corpus_id=%s AND realization_type='text'
                     AND metadata->>'source_text_sha256' IS NOT NULL""",
                (CORPUS_ID,),
            ),
            "publication_enabled": scalar(
                cur,
                """SELECT count(*) FROM corpus
                   WHERE corpus_id=%s AND metadata->>'publication_eligible'='true'""",
                (CORPUS_ID,),
            ),
        }

    expected = {
        "sources": 1,
        "artifacts": 1,
        "books": len(BOOK_ORDER),
        "passages": profile["verse_records"],
        "references": profile["verse_records"],
        "mappings": profile["verse_records"],
        "uncertain_unreviewed_mappings": profile["verse_records"],
        "text_units": profile["verse_records"],
        "textual": profile["textual_records"],
        "placeholders": profile["marker_only_record_count"],
        "orphans": 0,
        "foreign_passage_links": 0,
        "cross_corpus_passage_sharing": 0,
        "reference_relations": 0,
        "alignments": 0,
        "releases": 0,
        "artifact_links": 1,
        "raw_payload_hashes": profile["verse_records"],
        "source_text_hashes": profile["textual_records"],
        "publication_enabled": 0,
    }
    if counts != expected:
        raise ValueError(f"ASV database validation mismatch: expected {expected}, observed {counts}")
    return {
        **counts,
        "work_id": WORK_ID,
        "versification_system_id": VERSIFICATION_ID,
        "corpus_id": CORPUS_ID,
        "identity_namespace": IDENTITY_NAMESPACE,
        "cross_translation_mappings_created": 0,
        "publication_eligible": False,
    }


def run(database_url: str, expected_path: Path | None = None) -> dict[str, Any]:
    target = load_json(TARGET_PATH)
    artifact = load_json(ARTIFACT_PATH)
    profile = load_json(PROFILE_PATH)

    with tempfile.TemporaryDirectory(prefix="bible-os-asv-full-ci-") as temp_dir:
        archive_path = Path(temp_dir) / artifact["filename"]
        download_verified_archive(target, archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            rows = source_rows(archive)

    if len(rows) != profile["verse_records"]:
        raise ValueError(
            f"parsed row count mismatch: expected {profile['verse_records']}, got {len(rows)}"
        )

    metrics = verify_reproducible_ndjson(export_records(rows))
    metrics.update(
        {
            "profile": "ASV 1901 provisional normalized export",
            "artifact_sha256": artifact["sha256"],
            "identity_namespace": IDENTITY_NAMESPACE,
            "publication_eligible": False,
            "retention": "serialized bytes hashed in memory and discarded",
        }
    )
    if expected_path is not None:
        assert_expected(metrics, load_json(expected_path))
        metrics["expected_profile"] = str(expected_path)
        metrics["profile_status"] = "matched"
    else:
        metrics["profile_status"] = "observed-unpinned"

    load_database(database_url, rows)
    database_report = validate_database(database_url, profile, artifact["artifact_id"])
    return {
        "status": "passed",
        "normalized_export": metrics,
        "database": database_report,
        "corpus_bytes_committed": False,
        "cross_translation_mappings_created": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fingerprint and load verified ASV 1901 without retaining corpus bytes"
    )
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--expected-export", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")

    report = run(args.database_url, args.expected_export)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
