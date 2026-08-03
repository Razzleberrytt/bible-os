from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "fixtures" / "bsb" / "bsb-100.fixture.json"

SOURCE_ID = "src_bsbshape0001"
ACQUISITION_ID = "acq_bsbshape0001"
ARTIFACT_ID = "art_bsbshape0001"
WORK_ID = "wrk_bible00000001"
BOOK_ID = "bok_genesis00001"
VERSIFICATION_ID = "vrs_bsbshape0001"
CORPUS_ID = "cor_bsbshape0001"


def stable_id(prefix: str, key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    token = base64.b32encode(digest).decode("ascii").lower().rstrip("=")[:20]
    return f"{prefix}_{token}"


def fixture() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    definition = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    sequence = 0
    for chapter in definition["chapters"]:
        for verse in range(1, chapter["verse_count"] + 1):
            sequence += 1
            reference = f"{definition['book']['name']} {chapter['chapter']}:{verse}"
            osis = f"{definition['book']['code']}.{chapter['chapter']}.{verse}"
            text = f"Synthetic fixture text for {osis}."
            rows.append(
                {
                    "sequence": sequence,
                    "reference": reference,
                    "osis": osis,
                    "chapter": chapter["chapter"],
                    "verse": verse,
                    "text": text,
                    "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "passage_id": stable_id("pas", f"passage|{osis}"),
                    "reference_id": stable_id("ref", f"reference|{osis}"),
                    "text_unit_id": stable_id("txt", f"text-unit|{CORPUS_ID}|{osis}"),
                }
            )

    if len(rows) != definition["expected_records"]:
        raise ValueError("Fixture record count does not match its definition.")
    if rows[0]["reference"] != definition["first_reference"]:
        raise ValueError("Fixture first reference does not match its definition.")
    if rows[-1]["reference"] != definition["last_reference"]:
        raise ValueError("Fixture last reference does not match its definition.")
    return definition, rows


def load(database_url: str) -> dict[str, int]:
    import psycopg
    from psycopg.types.json import Jsonb

    definition, rows = fixture()
    fixture_sha256 = hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest()

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cur:
            cur.execute(
                """INSERT INTO source
                   (source_id,name,source_type,authority_status,license_status,commercial_use,metadata)
                   VALUES (%s,%s,'metadata','unverified','rejected','prohibited',%s)
                   ON CONFLICT (source_id) DO NOTHING""",
                (
                    SOURCE_ID,
                    "Synthetic BSB-shaped loader fixture",
                    Jsonb(
                        {
                            "fixture_id": definition["fixture_id"],
                            "text_policy": definition["text_policy"],
                            "publication_policy": definition["publication_policy"],
                            "upstream_reference_only": definition["upstream_reference_only"],
                        }
                    ),
                ),
            )
            cur.execute(
                """INSERT INTO acquisition_event
                   (acquisition_event_id,source_id,requested_url,resolved_url,started_at,finished_at,
                    result,observed_sha256,observed_bytes,retrieval_tool)
                   VALUES (%s,%s,%s,%s,'2026-08-03T17:45:00Z','2026-08-03T17:45:01Z',
                           'rejected',%s,%s,%s)
                   ON CONFLICT (acquisition_event_id) DO NOTHING""",
                (
                    ACQUISITION_ID,
                    SOURCE_ID,
                    "https://github.com/Razzleberrytt/bible-os",
                    "https://github.com/Razzleberrytt/bible-os",
                    fixture_sha256,
                    FIXTURE_PATH.stat().st_size,
                    Jsonb({"name": "Bible OS synthetic fixture generator", "version": "0.1.0"}),
                ),
            )
            cur.execute(
                """INSERT INTO source_artifact
                   (artifact_id,source_id,acquisition_event_id,sha256,byte_size,media_type,
                    filename,archive_uri,verification_status,license_assertion)
                   VALUES (%s,%s,%s,%s,%s,'application/json',%s,%s,'rejected',%s)
                   ON CONFLICT (artifact_id) DO NOTHING""",
                (
                    ARTIFACT_ID,
                    SOURCE_ID,
                    ACQUISITION_ID,
                    fixture_sha256,
                    FIXTURE_PATH.stat().st_size,
                    FIXTURE_PATH.name,
                    f"artifact+sha256://{fixture_sha256}",
                    Jsonb(
                        {
                            "status": "rejected",
                            "commercial_use": "prohibited",
                            "evidence_urls": [],
                        }
                    ),
                ),
            )
            cur.execute(
                """INSERT INTO work (work_id,canonical_name,metadata)
                   VALUES (%s,'Synthetic Bible-shaped test work',%s)
                   ON CONFLICT (work_id) DO NOTHING""",
                (WORK_ID, Jsonb({"test_only": True})),
            )
            cur.execute(
                """INSERT INTO book (book_id,work_id,canonical_name,metadata)
                   VALUES (%s,%s,%s,%s) ON CONFLICT (book_id) DO NOTHING""",
                (
                    BOOK_ID,
                    WORK_ID,
                    definition["book"]["name"],
                    Jsonb({"book_code": definition["book"]["code"], "test_only": True}),
                ),
            )
            cur.execute(
                """INSERT INTO versification_system
                   (versification_system_id,name,version,authority)
                   VALUES (%s,'Synthetic BSB-shaped references','fixture-1','Bible OS tests')
                   ON CONFLICT (versification_system_id) DO NOTHING""",
                (VERSIFICATION_ID,),
            )
            cur.execute(
                """INSERT INTO corpus
                   (corpus_id,source_id,name,upstream_version,language_codes,metadata)
                   VALUES (%s,%s,%s,'fixture-1',%s,%s)
                   ON CONFLICT (corpus_id) DO NOTHING""",
                (
                    CORPUS_ID,
                    SOURCE_ID,
                    "Synthetic BSB-shaped loader fixture",
                    ["eng"],
                    Jsonb({"test_only": True, "fixture_id": definition["fixture_id"]}),
                ),
            )
            cur.execute(
                """INSERT INTO corpus_artifact (corpus_id,artifact_id)
                   VALUES (%s,%s) ON CONFLICT DO NOTHING""",
                (CORPUS_ID, ARTIFACT_ID),
            )

            for row in rows:
                cur.execute(
                    """INSERT INTO passage
                       (passage_id,book_id,parent_passage_id,passage_kind,sort_ordinal,metadata)
                       VALUES (%s,%s,NULL,'verse',%s,%s)
                       ON CONFLICT (passage_id) DO NOTHING""",
                    (
                        row["passage_id"],
                        BOOK_ID,
                        row["sequence"],
                        Jsonb({"osis": row["osis"], "test_only": True}),
                    ),
                )
                cur.execute(
                    """INSERT INTO versification_reference
                       (versification_reference_id,versification_system_id,book_code,chapter,verse,
                        subverse,display_reference,source_locator)
                       VALUES (%s,%s,%s,%s,%s,NULL,%s,%s)
                       ON CONFLICT (versification_reference_id) DO NOTHING""",
                    (
                        row["reference_id"],
                        VERSIFICATION_ID,
                        definition["book"]["code"],
                        row["chapter"],
                        row["verse"],
                        row["reference"],
                        Jsonb({"osis": row["osis"], "source_sequence": row["sequence"]}),
                    ),
                )
                cur.execute(
                    """INSERT INTO passage_reference_mapping
                       (passage_reference_mapping_id,passage_id,versification_reference_id,
                        relation_type,confidence,method,review_state,evidence)
                       VALUES (%s,%s,%s,'equivalent',1.0,'rule-based','machine-checked',%s)
                       ON CONFLICT (passage_reference_mapping_id) DO NOTHING""",
                    (
                        stable_id(
                            "prm",
                            f"{row['passage_id']}|{row['reference_id']}|equivalent",
                        ),
                        row["passage_id"],
                        row["reference_id"],
                        Jsonb([{"fixture_id": definition["fixture_id"], "test_only": True}]),
                    ),
                )
                cur.execute(
                    """INSERT INTO text_unit
                       (text_unit_id,corpus_id,passage_id,source_reference_id,realization_type,
                        source_text,normalized_text,source_sequence,metadata)
                       VALUES (%s,%s,%s,%s,'text',%s,%s,%s,%s)
                       ON CONFLICT (text_unit_id) DO NOTHING""",
                    (
                        row["text_unit_id"],
                        CORPUS_ID,
                        row["passage_id"],
                        row["reference_id"],
                        row["text"],
                        row["text"],
                        row["sequence"],
                        Jsonb({"source_text_sha256": row["text_sha256"], "test_only": True}),
                    ),
                )
    return {"rows_loaded": len(rows)}


def scalar(cur, query: str, params: tuple = ()):
    cur.execute(query, params)
    return cur.fetchone()[0]


def validate(database_url: str) -> dict[str, Any]:
    import psycopg

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cur:
            counts = {
                "books": scalar(cur, "SELECT count(*) FROM book"),
                "passages": scalar(cur, "SELECT count(*) FROM passage"),
                "references": scalar(cur, "SELECT count(*) FROM versification_reference"),
                "mappings": scalar(cur, "SELECT count(*) FROM passage_reference_mapping"),
                "text_units": scalar(
                    cur, "SELECT count(*) FROM text_unit WHERE corpus_id=%s", (CORPUS_ID,)
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
                """SELECT r.display_reference FROM text_unit t
                   JOIN versification_reference r
                     ON r.versification_reference_id=t.source_reference_id
                   WHERE t.corpus_id=%s ORDER BY t.source_sequence""",
                (CORPUS_ID,),
            )
            references = [record[0] for record in cur.fetchall()]
            synthetic_texts = scalar(
                cur,
                """SELECT count(*) FROM text_unit
                   WHERE corpus_id=%s AND source_text LIKE 'Synthetic fixture text for %%'""",
                (CORPUS_ID,),
            )

    mutation_rejected = False
    try:
        with psycopg.connect(database_url) as connection, connection.transaction():
            connection.execute(
                "UPDATE source_artifact SET filename=filename WHERE artifact_id=%s",
                (ARTIFACT_ID,),
            )
    except psycopg.Error:
        mutation_rejected = True

    expected = {
        "books": 1,
        "passages": 100,
        "references": 100,
        "mappings": 100,
        "text_units": 100,
        "orphans": 0,
    }
    failures = [
        f"{key}: expected {wanted}, got {counts[key]}"
        for key, wanted in expected.items()
        if counts[key] != wanted
    ]
    if sequence != {"min": 1, "max": 100, "distinct": 100}:
        failures.append(f"sequence: {sequence}")
    if references[:1] != ["Genesis 1:1"] or references[-1:] != ["Genesis 4:20"]:
        failures.append("reference bounds differ from Genesis 1:1–4:20")
    if synthetic_texts != 100:
        failures.append(f"expected 100 synthetic texts, got {synthetic_texts}")
    if not mutation_rejected:
        failures.append("source_artifact append-only trigger did not reject update")

    report = {
        "status": "passed" if not failures else "failed",
        "counts": counts,
        "sequence": sequence,
        "synthetic_texts": synthetic_texts,
        "source_artifact_mutation_rejected": mutation_rejected,
        "failures": failures,
    }
    if failures:
        raise SystemExit(json.dumps(report, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["load", "validate"])
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    result = load(args.database_url) if args.action == "load" else validate(args.database_url)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
