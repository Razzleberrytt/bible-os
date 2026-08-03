from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from bible_os.identity import stable_id
from bible_os.importers.webp_usfm import BOOK_ORDER, WebpUsfmAdapter, extract_visible_text
from scripts.webp_adapter_smoke import download_verified_archive, load_json

ROOT = Path(__file__).resolve().parents[1]
TARGET_PATH = ROOT / "registry" / "acquisitions" / "engwebp-usfm.json"
SOURCE_PATH = ROOT / "registry" / "sources" / "engwebp.source.json"
EVENT_PATH = ROOT / "registry" / "acquisition-events" / "engwebp-usfm-20260803.json"
ARTIFACT_PATH = ROOT / "registry" / "artifacts" / "engwebp-usfm.artifact.json"
PROFILE_PATH = ROOT / "registry" / "import-profiles" / "engwebp-usfm-smoke.json"

IDENTITY_NAMESPACE = "bible-os:ephemeral-webp-source-locus:v1"
WORK_ID = stable_id("wrk", IDENTITY_NAMESPACE, "protestant-bible-66")
VERSIFICATION_ID = stable_id("vrs", IDENTITY_NAMESPACE, "engwebp-source-references")
CORPUS_ID = stable_id("cor", IDENTITY_NAMESPACE, "engwebp-parse-smoke")

BOOK_NAMES = {
    "GEN": "Genesis", "EXO": "Exodus", "LEV": "Leviticus", "NUM": "Numbers",
    "DEU": "Deuteronomy", "JOS": "Joshua", "JDG": "Judges", "RUT": "Ruth",
    "1SA": "1 Samuel", "2SA": "2 Samuel", "1KI": "1 Kings", "2KI": "2 Kings",
    "1CH": "1 Chronicles", "2CH": "2 Chronicles", "EZR": "Ezra", "NEH": "Nehemiah",
    "EST": "Esther", "JOB": "Job", "PSA": "Psalms", "PRO": "Proverbs",
    "ECC": "Ecclesiastes", "SNG": "Song of Songs", "ISA": "Isaiah", "JER": "Jeremiah",
    "LAM": "Lamentations", "EZK": "Ezekiel", "DAN": "Daniel", "HOS": "Hosea",
    "JOL": "Joel", "AMO": "Amos", "OBA": "Obadiah", "JON": "Jonah",
    "MIC": "Micah", "NAM": "Nahum", "HAB": "Habakkuk", "ZEP": "Zephaniah",
    "HAG": "Haggai", "ZEC": "Zechariah", "MAL": "Malachi", "MAT": "Matthew",
    "MRK": "Mark", "LUK": "Luke", "JHN": "John", "ACT": "Acts",
    "ROM": "Romans", "1CO": "1 Corinthians", "2CO": "2 Corinthians", "GAL": "Galatians",
    "EPH": "Ephesians", "PHP": "Philippians", "COL": "Colossians",
    "1TH": "1 Thessalonians", "2TH": "2 Thessalonians", "1TI": "1 Timothy",
    "2TI": "2 Timothy", "TIT": "Titus", "PHM": "Philemon", "HEB": "Hebrews",
    "JAS": "James", "1PE": "1 Peter", "2PE": "2 Peter", "1JN": "1 John",
    "2JN": "2 John", "3JN": "3 John", "JUD": "Jude", "REV": "Revelation",
}


def source_rows(archive: zipfile.ZipFile) -> list[dict[str, Any]]:
    adapter = WebpUsfmAdapter()
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


def load_registry(cur, *, source: dict[str, Any], event: dict[str, Any], artifact: dict[str, Any]) -> None:
    from psycopg.types.json import Jsonb

    cur.execute(
        """INSERT INTO source
           (source_id,name,source_type,authority_status,license_status,commercial_use,metadata)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (
            source["source_id"], source["name"], source["source_type"],
            source["authority_status"], source["license_status"], source["commercial_use"],
            Jsonb({
                "language_codes": source["language_codes"],
                "official_urls": source["official_urls"],
                "spdx_expression": source["spdx_expression"],
                "attribution_text": source["attribution_text"],
                "license_evidence_urls": source["license_evidence_urls"],
                "notes": source["notes"],
            }),
        ),
    )
    cur.execute(
        """INSERT INTO acquisition_event
           (acquisition_event_id,source_id,requested_url,resolved_url,started_at,finished_at,
            result,observed_sha256,observed_bytes,retrieval_tool,error)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            event["event_id"], event["source_id"], event["requested_url"], event["resolved_url"],
            event["started_at"], event["finished_at"], event["result"],
            event["observed_sha256"], event["observed_bytes"], Jsonb(event["retrieval_tool"]),
            event["error"],
        ),
    )
    cur.execute(
        """INSERT INTO source_artifact
           (artifact_id,source_id,acquisition_event_id,sha256,byte_size,media_type,
            filename,archive_uri,verification_status,license_assertion)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            artifact["artifact_id"], artifact["source_id"], artifact["acquisition_event_id"],
            artifact["sha256"], artifact["byte_size"], artifact["media_type"],
            artifact["filename"], artifact["archive_uri"], artifact["verification_status"],
            Jsonb(artifact["license_assertion"]),
        ),
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
            """INSERT INTO work (work_id,canonical_name,metadata)
               VALUES (%s,%s,%s)""",
            (
                WORK_ID,
                "Protestant Bible — provisional WEBP source-locus staging work",
                Jsonb({
                    "ephemeral": True,
                    "identity_status": "source-locus-only",
                    "publication_eligible": False,
                }),
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
                    Jsonb({
                        "book_code": code,
                        "ephemeral": True,
                        "identity_status": "source-locus-only",
                    }),
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
                "World English Bible Protestant Edition source references",
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
                "WEBP ephemeral parse-smoke corpus",
                artifact["upstream_version"],
                source["language_codes"],
                Jsonb({
                    "ephemeral": True,
                    "pipeline_stage": "parse-smoke",
                    "publication_eligible": False,
                    "adapter": "webp-usfm-v1",
                    "artifact_sha256": artifact["sha256"],
                }),
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
                    row["passage_id"], row["book_id"], row["sequence"],
                    Jsonb({
                        "osis": row["osis"],
                        "ephemeral": True,
                        "identity_status": "source-locus-only",
                        "publication_eligible": False,
                    }),
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
                    row["reference_id"], VERSIFICATION_ID, row["book_code"], row["chapter"],
                    row["verse"], row["display_reference"],
                    Jsonb({
                        "osis": row["osis"],
                        "source_sequence": row["sequence"],
                        "source_file": row["source_file"],
                    }),
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
                    row["mapping_id"], row["passage_id"], row["reference_id"],
                    Jsonb([{
                        "stage": "ephemeral-source-locus-load",
                        "reason": "canonical passage identity and cross-corpus mapping pending",
                        "publication_eligible": False,
                    }]),
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
                    row["text_unit_id"], CORPUS_ID, row["passage_id"], row["reference_id"],
                    row["realization_type"], row["source_text"], row["source_text"],
                    row["sequence"],
                    Jsonb({
                        "ephemeral": True,
                        "pipeline_stage": "parse-smoke",
                        "publication_eligible": False,
                        "source_file": row["source_file"],
                        "raw_payload_sha256": row["raw_payload_sha256"],
                        "source_text_sha256": row["source_text_sha256"],
                    }),
                )
                for row in rows
            ],
        )


def scalar(cur, query: str, params: tuple[Any, ...] = ()) -> Any:
    cur.execute(query, params)
    return cur.fetchone()[0]


def validate_database(database_url: str, profile: dict[str, Any], artifact_id: str) -> dict[str, Any]:
    import psycopg

    with psycopg.connect(database_url) as connection, connection.cursor() as cur:
        counts = {
            "books": scalar(cur, "SELECT count(*) FROM book WHERE work_id=%s", (WORK_ID,)),
            "passages": scalar(
                cur, "SELECT count(*) FROM passage WHERE metadata->>'ephemeral'='true'"
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
            "text_units": scalar(
                cur, "SELECT count(*) FROM text_unit WHERE corpus_id=%s", (CORPUS_ID,)
            ),
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
            "releases": scalar(cur, "SELECT count(*) FROM dataset_release"),
        }
        sequence = {
            "min": scalar(
                cur, "SELECT min(source_sequence) FROM text_unit WHERE corpus_id=%s", (CORPUS_ID,)
            ),
            "max": scalar(
                cur, "SELECT max(source_sequence) FROM text_unit WHERE corpus_id=%s", (CORPUS_ID,)
            ),
            "distinct": scalar(
                cur,
                "SELECT count(DISTINCT source_sequence) FROM text_unit WHERE corpus_id=%s",
                (CORPUS_ID,),
            ),
        }
        cur.execute(
            """SELECT r.book_code || ' ' || r.chapter || ':' || r.verse
               FROM text_unit t
               JOIN versification_reference r
                 ON r.versification_reference_id=t.source_reference_id
               WHERE t.corpus_id=%s AND t.realization_type='empty-placeholder'
               ORDER BY t.source_sequence""",
            (CORPUS_ID,),
        )
        marker_only = [row[0] for row in cur.fetchall()]
        cur.execute(
            """SELECT r.display_reference FROM text_unit t
               JOIN versification_reference r
                 ON r.versification_reference_id=t.source_reference_id
               WHERE t.corpus_id=%s ORDER BY t.source_sequence""",
            (CORPUS_ID,),
        )
        references = [row[0] for row in cur.fetchall()]
        non_provisional_mappings = scalar(
            cur,
            """SELECT count(*) FROM passage_reference_mapping m
               JOIN versification_reference r
                 ON r.versification_reference_id=m.versification_reference_id
               WHERE r.versification_system_id=%s
                 AND (m.relation_type<>'uncertain' OR m.review_state<>'unreviewed')""",
            (VERSIFICATION_ID,),
        )

    mutation_rejected = False
    try:
        with psycopg.connect(database_url) as connection, connection.transaction():
            connection.execute(
                "UPDATE source_artifact SET filename=filename WHERE artifact_id=%s",
                (artifact_id,),
            )
    except psycopg.Error:
        mutation_rejected = True

    expected_counts = {
        "books": 66,
        "passages": profile["verse_records"],
        "references": profile["verse_records"],
        "mappings": profile["verse_records"],
        "text_units": profile["verse_records"],
        "textual": profile["textual_records"],
        "placeholders": profile["marker_only_record_count"],
        "orphans": 0,
        "releases": 0,
    }
    failures = [
        f"{name}: expected {expected}, got {counts[name]}"
        for name, expected in expected_counts.items()
        if counts[name] != expected
    ]
    expected_sequence = {
        "min": 1,
        "max": profile["verse_records"],
        "distinct": profile["verse_records"],
    }
    if sequence != expected_sequence:
        failures.append(f"sequence mismatch: {sequence}")
    if marker_only != profile["marker_only_records"]:
        failures.append(f"marker-only loci mismatch: {marker_only}")
    if references[:1] != ["Genesis 1:1"] or references[-1:] != ["Revelation 22:21"]:
        failures.append("reference bounds differ from Genesis 1:1–Revelation 22:21")
    if non_provisional_mappings != 0:
        failures.append(f"expected only provisional mappings, got {non_provisional_mappings} promoted")
    if not mutation_rejected:
        failures.append("source_artifact append-only trigger did not reject update")

    report = {
        "status": "passed" if not failures else "failed",
        "counts": counts,
        "sequence": sequence,
        "marker_only_records": marker_only,
        "non_provisional_mappings": non_provisional_mappings,
        "source_artifact_mutation_rejected": mutation_rejected,
        "database_retention": "disposable GitHub Actions service container",
        "publication_eligible": False,
        "failures": failures,
    }
    if failures:
        raise SystemExit(json.dumps(report, indent=2, sort_keys=True))
    return report


def run(database_url: str) -> dict[str, Any]:
    target = load_json(TARGET_PATH)
    artifact = load_json(ARTIFACT_PATH)
    profile = load_json(PROFILE_PATH)

    with tempfile.TemporaryDirectory(prefix="bible-os-webp-db-") as temp_dir:
        archive_path = Path(temp_dir) / artifact["filename"]
        download_verified_archive(target, archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            rows = source_rows(archive)

    if len(rows) != profile["verse_records"]:
        raise ValueError(
            f"parsed row count mismatch: expected {profile['verse_records']}, got {len(rows)}"
        )
    load_database(database_url, rows)
    return validate_database(database_url, profile, artifact["artifact_id"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Load verified WEBP into a disposable database")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    print(json.dumps(run(args.database_url), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
