from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from bible_os.identity import stable_id
from scripts.romans_doxology_mapping import (
    OBSERVATION_PATH,
    build_plan,
    load_json,
)


RELATION_NAMESPACE = "bible-os:reference-relation:v1"


def build_relations(observation: dict[str, Any]) -> list[dict[str, Any]]:
    plan = build_plan(observation)
    pair_relations = [pair["relation_type"] for pair in observation["reference_pairs"]]
    if pair_relations != [observation["relation_type"]] * len(plan):
        raise ValueError("reference-pair relation types must match the observation relation type")

    return [
        {
            "reference_relation_id": stable_id(
                "rrl",
                RELATION_NAMESPACE,
                (
                    f"{pair['source_reference_id']}|{pair['target_reference_id']}|"
                    f"{observation['relation_type']}"
                ),
            ),
            "source_reference_id": pair["source_reference_id"],
            "target_reference_id": pair["target_reference_id"],
            "source_reference": pair["source_reference"],
            "target_reference": pair["target_reference"],
            "relation_type": observation["relation_type"],
            "confidence": observation["confidence"],
        }
        for pair in plan
    ]


def materialize(
    database_url: str,
    observation: dict[str, Any],
    relations: list[dict[str, Any]],
) -> None:
    import psycopg
    from psycopg.types.json import Jsonb

    with psycopg.connect(database_url) as connection, connection.cursor() as cur:
        cur.executemany(
            """INSERT INTO reference_relation
               (reference_relation_id,source_reference_id,target_reference_id,
                relation_type,confidence,method,review_state,evidence,metadata)
               VALUES (%s,%s,%s,%s,%s,'reference-observation-v1','evidence-reviewed',%s,%s)""",
            [
                (
                    relation["reference_relation_id"],
                    relation["source_reference_id"],
                    relation["target_reference_id"],
                    relation["relation_type"],
                    relation["confidence"],
                    Jsonb(
                        [
                            {
                                "observation_id": observation["observation_id"],
                                "source_reference": relation["source_reference"],
                                "target_reference": relation["target_reference"],
                                "evidence": observation["evidence"],
                                "publication_eligible": False,
                            }
                        ]
                    ),
                    Jsonb(
                        {
                            "observation_status": observation["status"],
                            "canonical_mapping_status": observation["canonical_mapping_status"],
                            "publication_eligible": False,
                        }
                    ),
                )
                for relation in relations
            ],
        )


def validate(
    database_url: str,
    observation: dict[str, Any],
    relations: list[dict[str, Any]],
) -> dict[str, Any]:
    import psycopg

    failures: list[str] = []
    rows: list[dict[str, Any]] = []
    with psycopg.connect(database_url) as connection, connection.cursor() as cur:
        cur.execute(
            """SELECT rr.reference_relation_id,
                      sr.book_code || ' ' || sr.chapter || ':' || sr.verse,
                      tr.book_code || ' ' || tr.chapter || ':' || tr.verse,
                      rr.relation_type, rr.confidence, rr.review_state,
                      sm.passage_id, tm.passage_id,
                      rr.metadata->>'publication_eligible'
               FROM reference_relation rr
               JOIN versification_reference sr
                 ON sr.versification_reference_id=rr.source_reference_id
               JOIN versification_reference tr
                 ON tr.versification_reference_id=rr.target_reference_id
               JOIN passage_reference_mapping sm
                 ON sm.versification_reference_id=rr.source_reference_id
               JOIN passage_reference_mapping tm
                 ON tm.versification_reference_id=rr.target_reference_id
               ORDER BY sr.chapter, sr.verse"""
        )
        database_rows = cur.fetchall()
        if len(database_rows) != len(relations):
            failures.append(
                f"reference relations: expected {len(relations)}, got {len(database_rows)}"
            )

        for expected, observed in zip(relations, database_rows, strict=False):
            (
                relation_id,
                source_reference,
                target_reference,
                relation_type,
                confidence,
                review_state,
                source_passage_id,
                target_passage_id,
                publication_eligible,
            ) = observed
            expected_state = (
                expected["reference_relation_id"],
                expected["source_reference"],
                expected["target_reference"],
                expected["relation_type"],
                float(expected["confidence"]),
                "evidence-reviewed",
                "false",
            )
            observed_state = (
                relation_id,
                source_reference,
                target_reference,
                relation_type,
                float(confidence),
                review_state,
                publication_eligible,
            )
            if observed_state != expected_state:
                failures.append(
                    f"reference relation mismatch for {expected['source_reference']}: {observed_state}"
                )
            if source_passage_id != target_passage_id:
                failures.append(
                    f"reference pair does not share a passage: {source_reference} -> {target_reference}"
                )
            rows.append(
                {
                    "reference_relation_id": relation_id,
                    "source_reference": source_reference,
                    "target_reference": target_reference,
                    "relation_type": relation_type,
                    "review_state": review_state,
                    "shared_passage_id": source_passage_id,
                    "publication_eligible": False,
                }
            )

        cur.execute("SELECT count(*) FROM dataset_release")
        releases = cur.fetchone()[0]
        if releases != 0:
            failures.append(f"dataset releases: expected 0, got {releases}")

    report = {
        "status": "passed" if not failures else "failed",
        "observation_id": observation["observation_id"],
        "reference_relation_count": len(rows),
        "relations": rows,
        "shared_passage_identity_verified": not any(
            "does not share a passage" in failure for failure in failures
        ),
        "corpus_text_in_report": False,
        "publication_eligible": False,
        "dataset_releases": releases,
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
    relations = build_relations(observation)
    materialize(args.database_url, observation, relations)
    report = validate(args.database_url, observation, relations)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
