from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from bible_os.identity import stable_id
from scripts.webp_db_load import CORPUS_ID, VERSIFICATION_ID


ROOT = Path(__file__).resolve().parents[1]
OBSERVATION_PATH = (
    ROOT
    / "registry"
    / "versification"
    / "observations"
    / "engwebp-bsb-romans-doxology.json"
)

MAPPING_NAMESPACE = "bible-os:versification-mapping:romans-doxology:v1"
BSB_VERSIFICATION_ID = stable_id(
    "vrs", MAPPING_NAMESPACE, "bsb-reference-alpha.1"
)
EXPECTED_SOURCE_SYSTEM = "engwebp-usfm-2026-07-28"
EXPECTED_TARGET_SYSTEM = "bsb-reference-alpha.1"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_reference(reference: str) -> tuple[str, int, int]:
    try:
        book, locus = reference.split(" ", 1)
        chapter_text, verse_text = locus.split(":", 1)
        chapter = int(chapter_text)
        verse = int(verse_text)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid reference: {reference!r}") from exc
    if not book or chapter < 1 or verse < 0:
        raise ValueError(f"invalid reference: {reference!r}")
    return book, chapter, verse


def build_plan(observation: dict[str, Any]) -> list[dict[str, Any]]:
    if observation["source_system"] != EXPECTED_SOURCE_SYSTEM:
        raise ValueError("unexpected source versification system")
    if observation["target_system"] != EXPECTED_TARGET_SYSTEM:
        raise ValueError("unexpected target versification system")
    if observation["relation_type"] != "relocated":
        raise ValueError("Romans doxology observation must be a relocation")
    if observation["status"] != "evidence-reviewed":
        raise ValueError("observation must be evidence-reviewed before materialization")
    if observation["canonical_mapping_status"] != "materialized":
        raise ValueError("observation must declare materialized canonical mappings")

    source_references = observation["source_references"]
    target_references = observation["target_references"]
    reference_pairs = observation["reference_pairs"]
    if len(source_references) != 3 or len(target_references) != 3:
        raise ValueError("Romans doxology mapping must contain exactly three references per system")
    if len(reference_pairs) != 3:
        raise ValueError("Romans doxology mapping must contain exactly three explicit pairs")

    expected_pairs = list(zip(source_references, target_references, strict=True))
    observed_pairs = [
        (pair["source_reference"], pair["target_reference"])
        for pair in reference_pairs
    ]
    if observed_pairs != expected_pairs:
        raise ValueError("explicit reference pairs do not match the ordered reference arrays")

    plan: list[dict[str, Any]] = []
    for ordinal, (source_reference, target_reference) in enumerate(expected_pairs, start=1):
        source_book, source_chapter, source_verse = parse_reference(source_reference)
        target_book, target_chapter, target_verse = parse_reference(target_reference)
        if source_book != "ROM" or target_book != "ROM":
            raise ValueError("Romans doxology mapping may only contain ROM references")
        canonical_key = f"romans-doxology-unit-{ordinal}"
        passage_id = stable_id("pas", MAPPING_NAMESPACE, canonical_key)
        source_reference_id = stable_id(
            "ref",
            "bible-os:ephemeral-webp-source-locus:v1",
            f"reference|{source_book}.{source_chapter}.{source_verse}",
        )
        target_reference_id = stable_id(
            "ref", MAPPING_NAMESPACE, f"bsb-reference|{target_reference}"
        )
        plan.append(
            {
                "ordinal": ordinal,
                "canonical_key": canonical_key,
                "passage_id": passage_id,
                "source_reference": source_reference,
                "source_book": source_book,
                "source_chapter": source_chapter,
                "source_verse": source_verse,
                "source_reference_id": source_reference_id,
                "target_reference": target_reference,
                "target_book": target_book,
                "target_chapter": target_chapter,
                "target_verse": target_verse,
                "target_reference_id": target_reference_id,
                "source_mapping_id": stable_id(
                    "prm",
                    MAPPING_NAMESPACE,
                    f"{passage_id}|{source_reference_id}|equivalent",
                ),
                "target_mapping_id": stable_id(
                    "prm",
                    MAPPING_NAMESPACE,
                    f"{passage_id}|{target_reference_id}|equivalent",
                ),
            }
        )
    return plan


def _mapping_evidence(observation: dict[str, Any], pair: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "observation_id": observation["observation_id"],
            "observation_status": observation["status"],
            "relation_type_between_references": observation["relation_type"],
            "source_reference": pair["source_reference"],
            "target_reference": pair["target_reference"],
            "evidence": observation["evidence"],
            "publication_eligible": False,
        }
    ]


def materialize(database_url: str, observation: dict[str, Any]) -> list[dict[str, Any]]:
    import psycopg
    from psycopg.types.json import Jsonb

    plan = build_plan(observation)
    with psycopg.connect(database_url) as connection, connection.cursor() as cur:
        cur.execute(
            """INSERT INTO versification_system
               (versification_system_id,name,version,authority)
               VALUES (%s,%s,%s,%s)""",
            (
                BSB_VERSIFICATION_ID,
                "BSB reference baseline",
                "alpha.1",
                "Bible OS pinned reference baseline",
            ),
        )

        for pair in plan:
            cur.execute(
                """SELECT r.versification_reference_id,
                          m.passage_reference_mapping_id,
                          p.passage_id,
                          p.book_id,
                          p.sort_ordinal,
                          p.metadata,
                          t.text_unit_id,
                          t.realization_type
                   FROM versification_reference r
                   JOIN passage_reference_mapping m
                     ON m.versification_reference_id=r.versification_reference_id
                   JOIN passage p ON p.passage_id=m.passage_id
                   JOIN text_unit t
                     ON t.passage_id=p.passage_id AND t.source_reference_id=r.versification_reference_id
                   WHERE r.versification_system_id=%s
                     AND r.book_code=%s AND r.chapter=%s AND r.verse=%s""",
                (
                    VERSIFICATION_ID,
                    pair["source_book"],
                    pair["source_chapter"],
                    pair["source_verse"],
                ),
            )
            source_row = cur.fetchone()
            if source_row is None:
                raise ValueError(f"source locus missing from database: {pair['source_reference']}")
            (
                observed_source_reference_id,
                old_mapping_id,
                old_passage_id,
                book_id,
                sort_ordinal,
                old_metadata,
                text_unit_id,
                realization_type,
            ) = source_row
            if observed_source_reference_id != pair["source_reference_id"]:
                raise ValueError(f"source reference identity drift: {pair['source_reference']}")
            if realization_type != "text":
                raise ValueError(f"relocated doxology source must contain text: {pair['source_reference']}")
            if old_metadata.get("identity_status") != "source-locus-only":
                raise ValueError(f"source passage is not provisional: {pair['source_reference']}")

            cur.execute(
                """INSERT INTO passage
                   (passage_id,book_id,parent_passage_id,passage_kind,sort_ordinal,metadata)
                   VALUES (%s,%s,NULL,'verse',%s,%s)""",
                (
                    pair["passage_id"],
                    book_id,
                    sort_ordinal,
                    Jsonb(
                        {
                            "canonical_key": pair["canonical_key"],
                            "identity_status": "canonicalized-by-reference-observation",
                            "observation_id": observation["observation_id"],
                            "source_reference": pair["source_reference"],
                            "target_reference": pair["target_reference"],
                            "ephemeral": True,
                            "publication_eligible": False,
                        }
                    ),
                ),
            )
            cur.execute(
                "UPDATE text_unit SET passage_id=%s WHERE text_unit_id=%s",
                (pair["passage_id"], text_unit_id),
            )
            cur.execute(
                "DELETE FROM passage_reference_mapping WHERE passage_reference_mapping_id=%s",
                (old_mapping_id,),
            )
            cur.execute("DELETE FROM passage WHERE passage_id=%s", (old_passage_id,))

            evidence = Jsonb(_mapping_evidence(observation, pair))
            cur.execute(
                """INSERT INTO passage_reference_mapping
                   (passage_reference_mapping_id,passage_id,versification_reference_id,
                    relation_type,confidence,method,review_state,evidence)
                   VALUES (%s,%s,%s,'equivalent',1.0,'reference-observation-v1',
                           'evidence-reviewed',%s)""",
                (
                    pair["source_mapping_id"],
                    pair["passage_id"],
                    pair["source_reference_id"],
                    evidence,
                ),
            )
            cur.execute(
                """INSERT INTO versification_reference
                   (versification_reference_id,versification_system_id,book_code,chapter,verse,
                    subverse,display_reference,source_locator)
                   VALUES (%s,%s,%s,%s,%s,NULL,%s,%s)""",
                (
                    pair["target_reference_id"],
                    BSB_VERSIFICATION_ID,
                    pair["target_book"],
                    pair["target_chapter"],
                    pair["target_verse"],
                    pair["target_reference"],
                    Jsonb(
                        {
                            "observation_id": observation["observation_id"],
                            "baseline": observation["target_system"],
                            "source_reference": pair["source_reference"],
                            "publication_eligible": False,
                        }
                    ),
                ),
            )
            cur.execute(
                """INSERT INTO passage_reference_mapping
                   (passage_reference_mapping_id,passage_id,versification_reference_id,
                    relation_type,confidence,method,review_state,evidence)
                   VALUES (%s,%s,%s,'equivalent',1.0,'reference-observation-v1',
                           'evidence-reviewed',%s)""",
                (
                    pair["target_mapping_id"],
                    pair["passage_id"],
                    pair["target_reference_id"],
                    evidence,
                ),
            )
    return plan


def scalar(cur: Any, query: str, params: tuple[Any, ...] = ()) -> Any:
    cur.execute(query, params)
    return cur.fetchone()[0]


def validate(database_url: str, observation: dict[str, Any], plan: list[dict[str, Any]]) -> dict[str, Any]:
    import psycopg

    failures: list[str] = []
    pair_reports: list[dict[str, Any]] = []
    with psycopg.connect(database_url) as connection, connection.cursor() as cur:
        counts = {
            "passages": scalar(cur, "SELECT count(*) FROM passage"),
            "references": scalar(cur, "SELECT count(*) FROM versification_reference"),
            "mappings": scalar(cur, "SELECT count(*) FROM passage_reference_mapping"),
            "text_units": scalar(cur, "SELECT count(*) FROM text_unit WHERE corpus_id=%s", (CORPUS_ID,)),
            "bsb_references": scalar(
                cur,
                "SELECT count(*) FROM versification_reference WHERE versification_system_id=%s",
                (BSB_VERSIFICATION_ID,),
            ),
            "evidence_reviewed_mappings": scalar(
                cur,
                "SELECT count(*) FROM passage_reference_mapping WHERE review_state='evidence-reviewed'",
            ),
            "releases": scalar(cur, "SELECT count(*) FROM dataset_release"),
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

        expected_counts = {
            "passages": 31103,
            "references": 31106,
            "mappings": 31106,
            "text_units": 31103,
            "bsb_references": 3,
            "evidence_reviewed_mappings": 6,
            "releases": 0,
            "orphans": 0,
        }
        for name, expected in expected_counts.items():
            if counts[name] != expected:
                failures.append(f"{name}: expected {expected}, got {counts[name]}")

        for pair in plan:
            cur.execute(
                """SELECT p.passage_id,
                          p.metadata->>'identity_status',
                          p.metadata->>'publication_eligible',
                          sm.relation_type, sm.review_state, sm.confidence,
                          tm.relation_type, tm.review_state, tm.confidence,
                          t.realization_type
                   FROM passage p
                   JOIN passage_reference_mapping sm
                     ON sm.passage_id=p.passage_id
                    AND sm.versification_reference_id=%s
                   JOIN passage_reference_mapping tm
                     ON tm.passage_id=p.passage_id
                    AND tm.versification_reference_id=%s
                   JOIN text_unit t
                     ON t.passage_id=p.passage_id AND t.source_reference_id=%s
                   WHERE p.passage_id=%s""",
                (
                    pair["source_reference_id"],
                    pair["target_reference_id"],
                    pair["source_reference_id"],
                    pair["passage_id"],
                ),
            )
            row = cur.fetchone()
            if row is None:
                failures.append(
                    f"shared canonical passage missing for {pair['source_reference']} -> {pair['target_reference']}"
                )
                continue
            (
                passage_id,
                identity_status,
                publication_eligible,
                source_relation,
                source_review,
                source_confidence,
                target_relation,
                target_review,
                target_confidence,
                realization_type,
            ) = row
            expected = (
                "canonicalized-by-reference-observation",
                "false",
                "equivalent",
                "evidence-reviewed",
                1.0,
                "equivalent",
                "evidence-reviewed",
                1.0,
                "text",
            )
            observed = (
                identity_status,
                publication_eligible,
                source_relation,
                source_review,
                float(source_confidence),
                target_relation,
                target_review,
                float(target_confidence),
                realization_type,
            )
            if observed != expected:
                failures.append(f"mapping state mismatch for {pair['source_reference']}: {observed}")
            pair_reports.append(
                {
                    "source_reference": pair["source_reference"],
                    "target_reference": pair["target_reference"],
                    "passage_id": passage_id,
                    "mapping_state": "evidence-reviewed",
                    "publication_eligible": False,
                }
            )

        cur.execute(
            """SELECT p.passage_id, t.realization_type,
                      p.metadata->>'identity_status'
               FROM versification_reference r
               JOIN text_unit t ON t.source_reference_id=r.versification_reference_id
               JOIN passage p ON p.passage_id=t.passage_id
               WHERE r.versification_system_id=%s
                 AND r.book_code='ROM' AND r.chapter=16 AND r.verse=25""",
            (VERSIFICATION_ID,),
        )
        placeholder = cur.fetchone()
        if placeholder is None:
            failures.append("WEBP ROM 16:25 placeholder is missing")
        else:
            placeholder_passage_id, realization_type, identity_status = placeholder
            if realization_type != "empty-placeholder":
                failures.append("WEBP ROM 16:25 is no longer an empty placeholder")
            if identity_status != "source-locus-only":
                failures.append("WEBP ROM 16:25 placeholder was incorrectly canonicalized")
            if placeholder_passage_id == plan[0]["passage_id"]:
                failures.append("WEBP ROM 16:25 placeholder collapsed into BSB ROM 16:25")

        target_text_units = scalar(
            cur,
            """SELECT count(*) FROM text_unit t
               JOIN versification_reference r
                 ON r.versification_reference_id=t.source_reference_id
               WHERE r.versification_system_id=%s""",
            (BSB_VERSIFICATION_ID,),
        )
        if target_text_units != 0:
            failures.append(f"BSB reference-only system unexpectedly owns {target_text_units} text units")

    report = {
        "status": "passed" if not failures else "failed",
        "observation_id": observation["observation_id"],
        "observation_status": observation["status"],
        "canonical_mapping_status": observation["canonical_mapping_status"],
        "relation_type_between_reference_systems": observation["relation_type"],
        "counts": counts,
        "reference_pairs": pair_reports,
        "webp_rom_16_25_placeholder_preserved": placeholder is not None and not any(
            "ROM 16:25" in failure for failure in failures
        ),
        "corpus_text_in_report": False,
        "publication_eligible": False,
        "failures": failures,
    }
    if failures:
        raise SystemExit(json.dumps(report, indent=2, sort_keys=True))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--observation", type=Path, default=OBSERVATION_PATH)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")

    observation = load_json(args.observation)
    plan = materialize(args.database_url, observation)
    report = validate(args.database_url, observation, plan)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
