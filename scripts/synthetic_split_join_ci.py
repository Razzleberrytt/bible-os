from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from bible_os.identity import stable_id
from bible_os.versification import (
    build_group_alignment_plan,
    build_materialization_plan,
    load_json,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_NAMESPACE = "bible-os:synthetic-split-join:v1"
SOURCE_ID = stable_id("src", FIXTURE_NAMESPACE, "source")
WORK_ID = stable_id("wrk", FIXTURE_NAMESPACE, "work")
BOOK_ID = stable_id("bok", FIXTURE_NAMESPACE, "book:SYN")
CORPUS_ID = stable_id("cor", FIXTURE_NAMESPACE, "corpus")
SCENARIOS = (
    (
        ROOT / "registry/versification/observations/synthetic-split.json",
        ROOT / "registry/versification/materializers/synthetic-split.json",
    ),
    (
        ROOT / "registry/versification/observations/synthetic-join.json",
        ROOT / "registry/versification/materializers/synthetic-join.json",
    ),
)


def scalar(cur: Any, query: str, params: tuple[Any, ...] = ()) -> Any:
    cur.execute(query, params)
    return cur.fetchone()[0]


def _reference_rows(
    plan: list[dict[str, Any]],
    profile: dict[str, Any],
) -> list[tuple[Any, ...]]:
    systems = (
        ("source", profile["source_system"]),
        ("target", profile["target_system"]),
    )
    rows: dict[str, tuple[Any, ...]] = {}
    for side, system in systems:
        for pair in plan:
            reference_id = pair[f"{side}_reference_id"]
            rows[reference_id] = (
                reference_id,
                system["versification_system_id"],
                pair[f"{side}_book"],
                pair[f"{side}_chapter"],
                pair[f"{side}_verse"],
                pair[f"{side}_reference"],
                {
                    "synthetic_fixture": True,
                    "materializer_id": profile["materializer_id"],
                    "publication_eligible": False,
                },
            )
    return list(rows.values())


def materialize(database_url: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    import psycopg
    from psycopg.types.json import Jsonb

    scenario_states: list[dict[str, Any]] = []
    plans: list[dict[str, Any]] = []
    for observation_path, profile_path in SCENARIOS:
        observation = load_json(observation_path)
        profile = load_json(profile_path)
        plan = build_materialization_plan(observation, profile)
        alignment = build_group_alignment_plan(observation, profile, plan)
        scenario_states.append(
            {
                "observation": observation,
                "profile": profile,
                "plan": plan,
                "alignment": alignment,
            }
        )
        plans.extend(plan)

    with psycopg.connect(database_url) as connection, connection.cursor() as cur:
        cur.execute(
            """INSERT INTO source
               (source_id,name,source_type,authority_status,license_status,
                commercial_use,metadata)
               VALUES (%s,'Bible OS synthetic split/join fixture','synthetic',
                       'internal-test','internal-test','not-applicable',%s)""",
            (SOURCE_ID, Jsonb({"synthetic_fixture": True, "publication_eligible": False})),
        )
        cur.execute(
            """INSERT INTO work (work_id,canonical_name,metadata)
               VALUES (%s,'Synthetic versification work',%s)""",
            (WORK_ID, Jsonb({"synthetic_fixture": True, "publication_eligible": False})),
        )
        cur.execute(
            """INSERT INTO book (book_id,work_id,canonical_name,metadata)
               VALUES (%s,%s,'Synthetic',%s)""",
            (
                BOOK_ID,
                WORK_ID,
                Jsonb({"book_code": "SYN", "synthetic_fixture": True, "publication_eligible": False}),
            ),
        )
        cur.execute(
            """INSERT INTO corpus
               (corpus_id,source_id,name,upstream_version,language_codes,metadata)
               VALUES (%s,%s,'Synthetic split/join corpus','1',ARRAY['zxx'],%s)""",
            (
                CORPUS_ID,
                SOURCE_ID,
                Jsonb({"synthetic_fixture": True, "publication_eligible": False}),
            ),
        )

        for state in scenario_states:
            profile = state["profile"]
            for system in (profile["source_system"], profile["target_system"]):
                cur.execute(
                    """INSERT INTO versification_system
                       (versification_system_id,name,version,authority)
                       VALUES (%s,%s,%s,%s)""",
                    (
                        system["versification_system_id"],
                        system["name"],
                        system["version"],
                        system["authority"],
                    ),
                )

        source_sequence = 0
        for scenario_index, state in enumerate(scenario_states, start=1):
            observation = state["observation"]
            profile = state["profile"]
            plan = state["plan"]
            alignment = state["alignment"]
            mapping_state = profile["mapping_state"]
            canonical = profile["canonical_identity"]

            for row in _reference_rows(plan, profile):
                cur.execute(
                    """INSERT INTO versification_reference
                       (versification_reference_id,versification_system_id,book_code,
                        chapter,verse,subverse,display_reference,source_locator)
                       VALUES (%s,%s,%s,%s,%s,NULL,%s,%s)""",
                    (*row[:-1], Jsonb(row[-1])),
                )

            for pair in plan:
                source_sequence += 1
                cur.execute(
                    """INSERT INTO passage
                       (passage_id,book_id,parent_passage_id,passage_kind,sort_ordinal,metadata)
                       VALUES (%s,%s,NULL,'segment',%s,%s)""",
                    (
                        pair["passage_id"],
                        BOOK_ID,
                        scenario_index * 100 + pair["ordinal"],
                        Jsonb(
                            {
                                "canonical_key": pair["canonical_key"],
                                "identity_status": canonical["identity_status"],
                                "observation_id": observation["observation_id"],
                                "materializer_id": profile["materializer_id"],
                                "mapping_shape": profile["mapping_shape"],
                                "synthetic_fixture": True,
                                "publication_eligible": False,
                            }
                        ),
                    ),
                )
                evidence = Jsonb(
                    [
                        {
                            "observation_id": observation["observation_id"],
                            "materializer_id": profile["materializer_id"],
                            "source_reference": pair["source_reference"],
                            "target_reference": pair["target_reference"],
                            "synthetic_fixture": True,
                            "publication_eligible": False,
                        }
                    ]
                )
                cur.execute(
                    """INSERT INTO passage_reference_mapping
                       (passage_reference_mapping_id,passage_id,versification_reference_id,
                        relation_type,confidence,method,review_state,evidence)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        pair["source_mapping_id"],
                        pair["passage_id"],
                        pair["source_reference_id"],
                        pair["source_mapping_relation"],
                        pair["confidence"],
                        mapping_state["method"],
                        mapping_state["review_state"],
                        evidence,
                    ),
                )
                cur.execute(
                    """INSERT INTO passage_reference_mapping
                       (passage_reference_mapping_id,passage_id,versification_reference_id,
                        relation_type,confidence,method,review_state,evidence)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        pair["target_mapping_id"],
                        pair["passage_id"],
                        pair["target_reference_id"],
                        pair["target_mapping_relation"],
                        pair["confidence"],
                        mapping_state["method"],
                        mapping_state["review_state"],
                        evidence,
                    ),
                )
                text_unit_id = stable_id(
                    "txt",
                    FIXTURE_NAMESPACE,
                    f"{profile['materializer_id']}|{pair['passage_id']}",
                )
                synthetic_text = (
                    f"synthetic {profile['mapping_shape']} component {pair['ordinal']}"
                )
                cur.execute(
                    """INSERT INTO text_unit
                       (text_unit_id,corpus_id,passage_id,source_reference_id,
                        realization_type,source_text,normalized_text,source_sequence,metadata)
                       VALUES (%s,%s,%s,%s,'text',%s,%s,%s,%s)""",
                    (
                        text_unit_id,
                        CORPUS_ID,
                        pair["passage_id"],
                        pair["source_reference_id"],
                        synthetic_text,
                        synthetic_text,
                        source_sequence,
                        Jsonb(
                            {
                                "synthetic_fixture": True,
                                "materializer_id": profile["materializer_id"],
                                "publication_eligible": False,
                            }
                        ),
                    ),
                )
                cur.execute(
                    """INSERT INTO reference_relation
                       (reference_relation_id,source_reference_id,target_reference_id,
                        relation_type,confidence,method,review_state,evidence,metadata)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        pair["reference_relation_id"],
                        pair["source_reference_id"],
                        pair["target_reference_id"],
                        pair["relation_type"],
                        pair["confidence"],
                        mapping_state["method"],
                        mapping_state["review_state"],
                        evidence,
                        Jsonb(
                            {
                                "synthetic_fixture": True,
                                "mapping_shape": profile["mapping_shape"],
                                "publication_eligible": False,
                            }
                        ),
                    ),
                )

            cur.execute(
                """INSERT INTO alignment
                   (alignment_id,alignment_level,source_ids,target_ids,relation_type,
                    method,algorithm_version,confidence,review_state,provenance)
                   VALUES (%s,%s,%s,%s,%s,%s,'split-join-v1',%s,%s,%s)""",
                (
                    alignment["alignment_id"],
                    alignment["alignment_level"],
                    alignment["source_ids"],
                    alignment["target_ids"],
                    alignment["relation_type"],
                    alignment["method"],
                    alignment["confidence"],
                    alignment["review_state"],
                    Jsonb(alignment["provenance"]),
                ),
            )

    return scenario_states, plans


def validate(
    database_url: str,
    scenario_states: list[dict[str, Any]],
    plans: list[dict[str, Any]],
) -> dict[str, Any]:
    import psycopg

    failures: list[str] = []
    scenario_reports: list[dict[str, Any]] = []
    expected_counts = {
        "passages": 4,
        "references": 6,
        "mappings": 8,
        "text_units": 4,
        "reference_relations": 4,
        "alignments": 2,
        "releases": 0,
    }

    with psycopg.connect(database_url) as connection, connection.cursor() as cur:
        observed_counts = {
            "passages": scalar(cur, "SELECT count(*) FROM passage"),
            "references": scalar(cur, "SELECT count(*) FROM versification_reference"),
            "mappings": scalar(cur, "SELECT count(*) FROM passage_reference_mapping"),
            "text_units": scalar(cur, "SELECT count(*) FROM text_unit"),
            "reference_relations": scalar(cur, "SELECT count(*) FROM reference_relation"),
            "alignments": scalar(cur, "SELECT count(*) FROM alignment"),
            "releases": scalar(cur, "SELECT count(*) FROM dataset_release"),
        }
        for name, expected in expected_counts.items():
            if observed_counts[name] != expected:
                failures.append(f"{name}: expected {expected}, got {observed_counts[name]}")

        orphan_passages = scalar(
            cur,
            """SELECT count(*) FROM passage p
               WHERE NOT EXISTS (
                 SELECT 1 FROM passage_reference_mapping m WHERE m.passage_id=p.passage_id
               )""",
        )
        if orphan_passages:
            failures.append(f"orphan passages: expected 0, got {orphan_passages}")

        invalid_mapping_cardinality = scalar(
            cur,
            """SELECT count(*) FROM (
                 SELECT passage_id FROM passage_reference_mapping
                 GROUP BY passage_id HAVING count(*) <> 2
               ) invalid""",
        )
        if invalid_mapping_cardinality:
            failures.append(
                f"passages with invalid mapping cardinality: {invalid_mapping_cardinality}"
            )

        invalid_text_cardinality = scalar(
            cur,
            """SELECT count(*) FROM (
                 SELECT p.passage_id
                 FROM passage p
                 LEFT JOIN text_unit t ON t.passage_id=p.passage_id
                 GROUP BY p.passage_id HAVING count(t.text_unit_id) <> 1
               ) invalid""",
        )
        if invalid_text_cardinality:
            failures.append(
                f"passages with invalid text-unit cardinality: {invalid_text_cardinality}"
            )

        non_synthetic_books = scalar(
            cur,
            "SELECT count(*) FROM versification_reference WHERE book_code <> 'SYN'",
        )
        if non_synthetic_books:
            failures.append(f"non-synthetic references present: {non_synthetic_books}")

        non_private_passages = scalar(
            cur,
            """SELECT count(*) FROM passage
               WHERE metadata->>'publication_eligible' IS DISTINCT FROM 'false'""",
        )
        if non_private_passages:
            failures.append(
                f"publishable or unmarked synthetic passages: {non_private_passages}"
            )

        non_private_relations = scalar(
            cur,
            """SELECT count(*) FROM reference_relation
               WHERE metadata->>'publication_eligible' IS DISTINCT FROM 'false'""",
        )
        if non_private_relations:
            failures.append(
                f"publishable or unmarked reference relations: {non_private_relations}"
            )

        for state in scenario_states:
            observation = state["observation"]
            profile = state["profile"]
            plan = state["plan"]
            alignment = state["alignment"]
            source_system_id = profile["source_system"]["versification_system_id"]
            target_system_id = profile["target_system"]["versification_system_id"]
            shape = profile["mapping_shape"]
            pair_count = len(plan)

            source_reference_count = scalar(
                cur,
                """SELECT count(*) FROM versification_reference
                   WHERE versification_system_id=%s""",
                (source_system_id,),
            )
            target_reference_count = scalar(
                cur,
                """SELECT count(*) FROM versification_reference
                   WHERE versification_system_id=%s""",
                (target_system_id,),
            )
            expected_source_count = len(observation["source_references"])
            expected_target_count = len(observation["target_references"])
            if source_reference_count != expected_source_count:
                failures.append(
                    f"{shape} source references: expected {expected_source_count}, "
                    f"got {source_reference_count}"
                )
            if target_reference_count != expected_target_count:
                failures.append(
                    f"{shape} target references: expected {expected_target_count}, "
                    f"got {target_reference_count}"
                )

            expected_source_relation = (
                "split" if shape == "one-to-many-split" else "equivalent"
            )
            expected_target_relation = (
                "join" if shape == "many-to-one-join" else "equivalent"
            )
            source_mapping_count = scalar(
                cur,
                """SELECT count(*) FROM passage_reference_mapping m
                   JOIN versification_reference r
                     ON r.versification_reference_id=m.versification_reference_id
                   WHERE r.versification_system_id=%s AND m.relation_type=%s""",
                (source_system_id, expected_source_relation),
            )
            target_mapping_count = scalar(
                cur,
                """SELECT count(*) FROM passage_reference_mapping m
                   JOIN versification_reference r
                     ON r.versification_reference_id=m.versification_reference_id
                   WHERE r.versification_system_id=%s AND m.relation_type=%s""",
                (target_system_id, expected_target_relation),
            )
            if source_mapping_count != pair_count:
                failures.append(
                    f"{shape} source mappings: expected {pair_count}, got {source_mapping_count}"
                )
            if target_mapping_count != pair_count:
                failures.append(
                    f"{shape} target mappings: expected {pair_count}, got {target_mapping_count}"
                )

            relation_count = scalar(
                cur,
                """SELECT count(*) FROM reference_relation
                   WHERE relation_type=%s AND review_state=%s""",
                (observation["relation_type"], profile["mapping_state"]["review_state"]),
            )
            if relation_count != pair_count:
                failures.append(
                    f"{shape} reference relations: expected {pair_count}, got {relation_count}"
                )

            cur.execute(
                """SELECT source_ids,target_ids,relation_type,review_state,
                          provenance->>'publication_eligible'
                   FROM alignment WHERE alignment_id=%s""",
                (alignment["alignment_id"],),
            )
            alignment_row = cur.fetchone()
            expected_alignment = (
                alignment["source_ids"],
                alignment["target_ids"],
                observation["relation_type"],
                profile["mapping_state"]["review_state"],
                "false",
            )
            if alignment_row != expected_alignment:
                failures.append(f"{shape} alignment mismatch: {alignment_row}")

            target_text_units = scalar(
                cur,
                """SELECT count(*) FROM text_unit t
                   JOIN versification_reference r
                     ON r.versification_reference_id=t.source_reference_id
                   WHERE r.versification_system_id=%s""",
                (target_system_id,),
            )
            if target_text_units != 0:
                failures.append(
                    f"{shape} target system unexpectedly owns {target_text_units} text units"
                )

            for pair in plan:
                cur.execute(
                    """SELECT count(*) FROM passage_reference_mapping
                       WHERE passage_id=%s
                         AND versification_reference_id IN (%s,%s)""",
                    (
                        pair["passage_id"],
                        pair["source_reference_id"],
                        pair["target_reference_id"],
                    ),
                )
                if cur.fetchone()[0] != 2:
                    failures.append(
                        f"component passage mapping mismatch: {pair['passage_id']}"
                    )

            scenario_reports.append(
                {
                    "materializer_id": profile["materializer_id"],
                    "observation_id": observation["observation_id"],
                    "mapping_shape": shape,
                    "source_reference_count": source_reference_count,
                    "target_reference_count": target_reference_count,
                    "component_passage_ids": [pair["passage_id"] for pair in plan],
                    "reference_relation_ids": [
                        pair["reference_relation_id"] for pair in plan
                    ],
                    "alignment_id": alignment["alignment_id"],
                    "publication_eligible": False,
                }
            )

    report = {
        "status": "passed" if not failures else "failed",
        "synthetic_fixture": True,
        "mapping_shapes": ["one-to-many-split", "many-to-one-join"],
        "counts": observed_counts,
        "orphan_passages": orphan_passages,
        "scenarios": scenario_reports,
        "dataset_releases": observed_counts["releases"],
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
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")

    scenario_states, plans = materialize(args.database_url)
    report = validate(args.database_url, scenario_states, plans)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
