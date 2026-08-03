from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from bible_os.identity import stable_id


RELATION_NAMESPACE = "bible-os:reference-relation:v1"


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


def build_materialization_plan(
    observation: dict[str, Any],
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    if profile["mapping_shape"] != "one-to-one-ordered":
        raise ValueError("only one-to-one-ordered materializer profiles are supported")
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
    if not source_references or len(source_references) != len(target_references):
        raise ValueError("ordered source and target reference arrays must have equal non-zero length")
    if len(reference_pairs) != len(source_references):
        raise ValueError("explicit reference-pair count does not match ordered arrays")

    expected_pairs = list(zip(source_references, target_references, strict=True))
    observed_pairs = [
        (pair["source_reference"], pair["target_reference"])
        for pair in reference_pairs
    ]
    if observed_pairs != expected_pairs:
        raise ValueError("explicit reference pairs do not match the ordered reference arrays")
    if any(pair["relation_type"] != observation["relation_type"] for pair in reference_pairs):
        raise ValueError("reference-pair relation types must match the observation relation type")

    allowed_books = set(profile["allowed_book_codes"])
    canonical = profile["canonical_identity"]
    source_system = profile["source_system"]
    target_system = profile["target_system"]
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
                "source_mapping_id": stable_id(
                    "prm",
                    canonical["namespace"],
                    f"{passage_id}|{source_reference_id}|equivalent",
                ),
                "target_mapping_id": stable_id(
                    "prm",
                    canonical["namespace"],
                    f"{passage_id}|{target_reference_id}|equivalent",
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
