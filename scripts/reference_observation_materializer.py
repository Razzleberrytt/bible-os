from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from bible_os.versification import build_materialization_plan, load_json, parse_reference


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OBSERVATION_PATH = (
    ROOT
    / "registry"
    / "versification"
    / "observations"
    / "engwebp-bsb-romans-doxology.json"
)
DEFAULT_PROFILE_PATH = (
    ROOT
    / "registry"
    / "versification"
    / "materializers"
    / "engwebp-bsb-romans-doxology.json"
)


def scalar(cur: Any, query: str, params: tuple[Any, ...] = ()) -> Any:
    cur.execute(query, params)
    return cur.fetchone()[0]


def database_counts(cur: Any) -> dict[str, int]:
    return {
        "passages": scalar(cur, "SELECT count(*) FROM passage"),
        "references": scalar(cur, "SELECT count(*) FROM versification_reference"),
        "mappings": scalar(cur, "SELECT count(*) FROM passage_reference_mapping"),
        "text_units": scalar(cur, "SELECT count(*) FROM text_unit"),
        "releases": scalar(cur, "SELECT count(*) FROM dataset_release"),
    }


def mapping_evidence(
    observation: dict[str, Any],
    profile: dict[str, Any],
    pair: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        {
            "observation_id": observation["observation_id"],
            "materializer_id": profile["materializer_id"],
            "observation_status": observation["status"],
            "relation_type_between_references": observation["relation_type"],
            "source_reference": pair["source_reference"],
            "target_reference": pair["target_reference"],
            "evidence": observation["evidence"],
            "publication_eligible": False,
        }
    ]


def materialize(
    database_url: str,
    observation: dict[str, Any],
    profile: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    import psycopg
    from psycopg.types.json import Jsonb

    plan = build_materialization_plan(observation, profile)
    source_system = profile["source_system"]
    target_system = profile["target_system"]
    canonical = profile["canonical_identity"]
    mapping_state = profile["mapping_state"]

    with psycopg.connect(database_url) as connection, connection.cursor() as cur:
        before = database_counts(cur)
        cur.execute(
            """SELECT name, version FROM versification_system
               WHERE versification_system_id=%s""",
            (source_system["versification_system_id"],),
        )
        if cur.fetchone() is None:
            raise ValueError("source versification system is missing from the database")

        cur.execute(
            """INSERT INTO versification_system
               (versification_system_id,name,version,authority)
               VALUES (%s,%s,%s,%s)""",
            (
                target_system["versification_system_id"],
                target_system["name"],
                target_system["version"],
                target_system["authority"],
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
                     ON t.passage_id=p.passage_id
                    AND t.source_reference_id=r.versification_reference_id
                   WHERE r.versification_system_id=%s
                     AND r.versification_reference_id=%s
                     AND r.book_code=%s AND r.chapter=%s AND r.verse=%s""",
                (
                    source_system["versification_system_id"],
                    pair["source_reference_id"],
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
                raise ValueError(
                    f"materialized source reference must contain text: {pair['source_reference']}"
                )
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
                            "identity_status": canonical["identity_status"],
                            "observation_id": observation["observation_id"],
                            "materializer_id": profile["materializer_id"],
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

            evidence = Jsonb(mapping_evidence(observation, profile, pair))
            cur.execute(
                """INSERT INTO passage_reference_mapping
                   (passage_reference_mapping_id,passage_id,versification_reference_id,
                    relation_type,confidence,method,review_state,evidence)
                   VALUES (%s,%s,%s,'equivalent',1.0,%s,%s,%s)""",
                (
                    pair["source_mapping_id"],
                    pair["passage_id"],
                    pair["source_reference_id"],
                    mapping_state["method"],
                    mapping_state["review_state"],
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
                    target_system["versification_system_id"],
                    pair["target_book"],
                    pair["target_chapter"],
                    pair["target_verse"],
                    pair["target_reference"],
                    Jsonb(
                        {
                            "observation_id": observation["observation_id"],
                            "materializer_id": profile["materializer_id"],
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
                   VALUES (%s,%s,%s,'equivalent',1.0,%s,%s,%s)""",
                (
                    pair["target_mapping_id"],
                    pair["passage_id"],
                    pair["target_reference_id"],
                    mapping_state["method"],
                    mapping_state["review_state"],
                    evidence,
                ),
            )

    return plan, before


def validate_preservation_checks(
    cur: Any,
    profile: dict[str, Any],
    plan: list[dict[str, Any]],
) -> list[str]:
    failures: list[str] = []
    systems = {
        "source": profile["source_system"],
        "target": profile["target_system"],
    }
    canonical_passage_ids = {pair["passage_id"] for pair in plan}

    for check in profile["preservation_checks"]:
        system = systems[check["system"]]
        book, chapter, verse = parse_reference(check["reference"])
        cur.execute(
            """SELECT p.passage_id, t.realization_type,
                      p.metadata->>'identity_status'
               FROM versification_reference r
               JOIN text_unit t ON t.source_reference_id=r.versification_reference_id
               JOIN passage p ON p.passage_id=t.passage_id
               WHERE r.versification_system_id=%s
                 AND r.book_code=%s AND r.chapter=%s AND r.verse=%s""",
            (system["versification_system_id"], book, chapter, verse),
        )
        row = cur.fetchone()
        if row is None:
            failures.append(f"preservation locus missing: {check['reference']}")
            continue
        passage_id, realization_type, identity_status = row
        if realization_type != check["realization_type"]:
            failures.append(
                f"preservation realization mismatch for {check['reference']}: {realization_type}"
            )
        if identity_status != check["identity_status"]:
            failures.append(
                f"preservation identity mismatch for {check['reference']}: {identity_status}"
            )
        if passage_id in canonical_passage_ids:
            failures.append(
                f"preservation locus collapsed into a materialized passage: {check['reference']}"
            )
    return failures


def validate(
    database_url: str,
    observation: dict[str, Any],
    profile: dict[str, Any],
    plan: list[dict[str, Any]],
    before: dict[str, int],
) -> dict[str, Any]:
    import psycopg

    failures: list[str] = []
    pair_reports: list[dict[str, Any]] = []
    source_system = profile["source_system"]
    target_system = profile["target_system"]
    canonical = profile["canonical_identity"]
    mapping_state = profile["mapping_state"]
    pair_count = len(plan)

    with psycopg.connect(database_url) as connection, connection.cursor() as cur:
        after = database_counts(cur)
        expected_after = {
            "passages": before["passages"],
            "references": before["references"] + pair_count,
            "mappings": before["mappings"] + pair_count,
            "text_units": before["text_units"],
            "releases": before["releases"],
        }
        for name, expected in expected_after.items():
            if after[name] != expected:
                failures.append(f"{name}: expected {expected}, got {after[name]}")
        if after["releases"] != 0:
            failures.append(f"dataset releases: expected 0, got {after['releases']}")

        target_reference_count = scalar(
            cur,
            "SELECT count(*) FROM versification_reference WHERE versification_system_id=%s",
            (target_system["versification_system_id"],),
        )
        if target_reference_count != pair_count:
            failures.append(
                f"target references: expected {pair_count}, got {target_reference_count}"
            )

        reviewed_mapping_count = scalar(
            cur,
            """SELECT count(*) FROM passage_reference_mapping m
               JOIN versification_reference r
                 ON r.versification_reference_id=m.versification_reference_id
               WHERE r.versification_system_id IN (%s,%s)
                 AND m.review_state=%s
                 AND m.method=%s""",
            (
                source_system["versification_system_id"],
                target_system["versification_system_id"],
                mapping_state["review_state"],
                mapping_state["method"],
            ),
        )
        if reviewed_mapping_count != pair_count * 2:
            failures.append(
                f"reviewed mappings: expected {pair_count * 2}, got {reviewed_mapping_count}"
            )

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
                    f"shared passage missing for {pair['source_reference']} -> {pair['target_reference']}"
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
            expected = (
                canonical["identity_status"],
                "false",
                "equivalent",
                mapping_state["review_state"],
                1.0,
                "equivalent",
                mapping_state["review_state"],
                1.0,
                "text",
            )
            if observed != expected:
                failures.append(f"mapping state mismatch for {pair['source_reference']}: {observed}")
            pair_reports.append(
                {
                    "source_reference": pair["source_reference"],
                    "target_reference": pair["target_reference"],
                    "passage_id": passage_id,
                    "mapping_state": mapping_state["review_state"],
                    "publication_eligible": False,
                }
            )

        failures.extend(validate_preservation_checks(cur, profile, plan))
        target_text_units = scalar(
            cur,
            """SELECT count(*) FROM text_unit t
               JOIN versification_reference r
                 ON r.versification_reference_id=t.source_reference_id
               WHERE r.versification_system_id=%s""",
            (target_system["versification_system_id"],),
        )
        if target_text_units != 0:
            failures.append(
                f"target reference-only system unexpectedly owns {target_text_units} text units"
            )

    report = {
        "status": "passed" if not failures else "failed",
        "materializer_id": profile["materializer_id"],
        "profile_version": profile["profile_version"],
        "mapping_shape": profile["mapping_shape"],
        "observation_id": observation["observation_id"],
        "observation_status": observation["status"],
        "canonical_mapping_status": observation["canonical_mapping_status"],
        "relation_type_between_reference_systems": observation["relation_type"],
        "counts_before": before,
        "counts_after": after,
        "reference_pairs": pair_reports,
        "preservation_checks_passed": not any(
            "preservation" in failure for failure in failures
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
    parser.add_argument("--observation", type=Path, default=DEFAULT_OBSERVATION_PATH)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE_PATH)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")

    observation = load_json(args.observation)
    profile = load_json(args.profile)
    plan, before = materialize(args.database_url, observation, profile)
    report = validate(args.database_url, observation, profile, plan, before)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
