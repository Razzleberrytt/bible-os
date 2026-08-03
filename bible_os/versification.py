from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from bible_os.identity import stable_id


RELATION_NAMESPACE = "bible-os:reference-relation:v1"
ALIGNMENT_NAMESPACE = "bible-os:reference-alignment:v1"
SUPPORTED_MAPPING_SHAPES = {
    "one-to-one-ordered",
    "one-to-many-split",
    "many-to-one-join",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_reference(reference: str) -> tuple[str, int, int]:
    try:
        book, locus = reference.split(" ", 1)
        chapter_text, verse_text = locus.split(":", 1)
        chapter = int(chapter_text)
        verse = int(verse_text)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid reference: {reference!r}") from exc
    if not book or chapter < 1 or verse < 0:
        raise ValueError(f"invalid reference: {reference!r}")
    return book, chapter, verse


def _render(template: str, context: Mapping[str, Any]) -> str:
    try:
        rendered = template.format_map(dict(context))
    except (KeyError, ValueError) as exc:
        raise ValueError(f"invalid identity template {template!r}") from exc
    if not rendered:
        raise ValueError("identity template rendered an empty key")
    return rendered


def _reference_context(reference: str) -> dict[str, Any]:
    book, chapter, verse = parse_reference(reference)
    return {
        "reference": reference,
        "book": book,
        "chapter": chapter,
        "verse": verse,
        "osis": f"{book}.{chapter}.{verse}",
    }


def _ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _expected_pairs(
    mapping_shape: str,
    source_references: list[str],
    target_references: list[str],
) -> list[tuple[str, str]]:
    if mapping_shape == "one-to-one-ordered":
        if (
            not source_references
            or len(source_references) != len(target_references)
            or len(set(source_references)) != len(source_references)
            or len(set(target_references)) != len(target_references)
        ):
            raise ValueError(
                "one-to-one ordered arrays must be equal, non-empty, and duplicate-free"
            )
        return list(zip(source_references, target_references, strict=True))

    if mapping_shape == "one-to-many-split":
        if len(source_references) != 1 or len(target_references) < 2:
            raise ValueError(
                "split materializers require one source reference and at least two targets"
            )
        if len(set(target_references)) != len(target_references):
            raise ValueError("split target references must be duplicate-free")
        return [(source_references[0], target) for target in target_references]

    if mapping_shape == "many-to-one-join":
        if len(source_references) < 2 or len(target_references) != 1:
            raise ValueError(
                "join materializers require at least two source references and one target"
            )
        if len(set(source_references)) != len(source_references):
            raise ValueError("join source references must be duplicate-free")
        return [(source, target_references[0]) for source in source_references]

    raise ValueError(f"unsupported mapping shape: {mapping_shape}")


def _mapping_relations(mapping_shape: str) -> tuple[str, str]:
    if mapping_shape == "one-to-many-split":
        return "split", "equivalent"
    if mapping_shape == "many-to-one-join":
        return "equivalent", "join"
    return "equivalent", "equivalent"


def build_materialization_plan(
    observation: dict[str, Any],
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    mapping_shape = profile["mapping_shape"]
    if mapping_shape not in SUPPORTED_MAPPING_SHAPES:
        raise ValueError(f"unsupported materializer mapping shape: {mapping_shape}")
    if profile["publication_eligible"] is not False:
        raise ValueError("reference observation materializers must remain non-publishable")
    if profile["observation_id"] != observation["observation_id"]:
        raise ValueError("materializer profile observation_id mismatch")
    if profile["source_system"]["system_key"] != observation["source_system"]:
        raise ValueError("materializer source system mismatch")
    if profile["target_system"]["system_key"] != observation["target_system"]:
        raise ValueError("materializer target system mismatch")
    if observation["status"] != profile["mapping_state"]["review_state"]:
        raise ValueError("observation status does not match materializer review state")
    if observation["canonical_mapping_status"] != "materialized":
        raise ValueError("observation must declare materialized canonical mappings")

    source_references = observation["source_references"]
    target_references = observation["target_references"]
    reference_pairs = observation["reference_pairs"]
    expected_pairs = _expected_pairs(
        mapping_shape,
        source_references,
        target_references,
    )
    if len(reference_pairs) != len(expected_pairs):
        raise ValueError("explicit reference-pair count does not match mapping shape")

    observed_pairs = [
        (pair["source_reference"], pair["target_reference"])
        for pair in reference_pairs
    ]
    if observed_pairs != expected_pairs:
        raise ValueError("explicit reference pairs do not match the mapping shape")
    if any(pair["relation_type"] != observation["relation_type"] for pair in reference_pairs):
        raise ValueError("reference-pair relation types must match the observation relation type")
    if mapping_shape == "one-to-many-split" and observation["relation_type"] != "split":
        raise ValueError("split materializers require relation_type 'split'")
    if mapping_shape == "many-to-one-join" and observation["relation_type"] != "join":
        raise ValueError("join materializers require relation_type 'join'")

    allowed_books = set(profile["allowed_book_codes"])
    canonical = profile["canonical_identity"]
    source_system = profile["source_system"]
    target_system = profile["target_system"]
    source_mapping_relation, target_mapping_relation = _mapping_relations(mapping_shape)
    plan: list[dict[str, Any]] = []

    for ordinal, (source_reference, target_reference) in enumerate(expected_pairs, start=1):
        source_context = _reference_context(source_reference)
        target_context = _reference_context(target_reference)
        if source_context["book"] not in allowed_books:
            raise ValueError(f"source book is not allowed by profile: {source_context['book']}")
        if target_context["book"] not in allowed_books:
            raise ValueError(f"target book is not allowed by profile: {target_context['book']}")

        canonical_context = {
            **source_context,
            "ordinal": ordinal,
            "mapping_shape": mapping_shape,
            "source_reference": source_reference,
            "target_reference": target_reference,
        }
        canonical_key = _render(canonical["passage_key_template"], canonical_context)
        passage_id = stable_id("pas", canonical["namespace"], canonical_key)
        source_reference_key = _render(
            source_system["reference_key_template"], source_context
        )
        target_reference_key = _render(
            target_system["reference_key_template"], target_context
        )
        source_reference_id = stable_id(
            "ref", source_system["reference_id_namespace"], source_reference_key
        )
        target_reference_id = stable_id(
            "ref", target_system["reference_id_namespace"], target_reference_key
        )
        relation_type = observation["relation_type"]

        plan.append(
            {
                "ordinal": ordinal,
                "mapping_shape": mapping_shape,
                "canonical_key": canonical_key,
                "passage_id": passage_id,
                "source_reference": source_reference,
                "source_book": source_context["book"],
                "source_chapter": source_context["chapter"],
                "source_verse": source_context["verse"],
                "source_osis": source_context["osis"],
                "source_reference_id": source_reference_id,
                "target_reference": target_reference,
                "target_book": target_context["book"],
                "target_chapter": target_context["chapter"],
                "target_verse": target_context["verse"],
                "target_osis": target_context["osis"],
                "target_reference_id": target_reference_id,
                "source_mapping_relation": source_mapping_relation,
                "target_mapping_relation": target_mapping_relation,
                "source_mapping_id": stable_id(
                    "prm",
                    canonical["namespace"],
                    f"{passage_id}|{source_reference_id}|{source_mapping_relation}",
                ),
                "target_mapping_id": stable_id(
                    "prm",
                    canonical["namespace"],
                    f"{passage_id}|{target_reference_id}|{target_mapping_relation}",
                ),
                "reference_relation_id": stable_id(
                    "rrl",
                    RELATION_NAMESPACE,
                    f"{source_reference_id}|{target_reference_id}|{relation_type}",
                ),
                "relation_type": relation_type,
                "confidence": observation["confidence"],
            }
        )

    return plan


def build_group_alignment_plan(
    observation: dict[str, Any],
    profile: dict[str, Any],
    plan: list[dict[str, Any]],
) -> dict[str, Any]:
    if not plan:
        raise ValueError("alignment plan requires at least one component")
    source_reference_ids = _ordered_unique(
        [pair["source_reference_id"] for pair in plan]
    )
    target_reference_ids = _ordered_unique(
        [pair["target_reference_id"] for pair in plan]
    )
    key = (
        f"{profile['source_system']['versification_system_id']}|"
        f"{'|'.join(source_reference_ids)}|"
        f"{profile['target_system']['versification_system_id']}|"
        f"{'|'.join(target_reference_ids)}|"
        f"{observation['relation_type']}"
    )
    return {
        "alignment_id": stable_id("aln", ALIGNMENT_NAMESPACE, key),
        "alignment_level": "passage",
        "source_ids": source_reference_ids,
        "target_ids": target_reference_ids,
        "relation_type": observation["relation_type"],
        "method": profile["mapping_state"]["method"],
        "review_state": profile["mapping_state"]["review_state"],
        "confidence": observation["confidence"],
        "provenance": {
            "observation_id": observation["observation_id"],
            "materializer_id": profile["materializer_id"],
            "mapping_shape": profile["mapping_shape"],
            "id_kind": "versification_reference",
            "publication_eligible": False,
        },
    }
