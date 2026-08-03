from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence


COORDINATE_SYSTEM = "unicode-codepoint-index-v1"


def text_sha256(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _validate_common(policy: Mapping[str, Any], operation: str) -> None:
    if policy.get("operation") != operation:
        raise ValueError(f"text boundary policy must declare operation {operation!r}")
    if policy.get("coordinate_system") != COORDINATE_SYSTEM:
        raise ValueError(f"unsupported coordinate system: {policy.get('coordinate_system')!r}")
    if policy.get("publication_eligible") is not False:
        raise ValueError("text boundary policies must remain non-publishable")
    if not policy.get("review_state"):
        raise ValueError("text boundary policy review_state is required")


def apply_split_policy(source_text: str, policy: Mapping[str, Any]) -> list[dict[str, Any]]:
    _validate_common(policy, "split")
    if policy.get("coverage") != "full-no-gaps-no-overlap":
        raise ValueError("split policy must require full coverage with no gaps or overlap")
    observed_source_hash = text_sha256(source_text)
    if observed_source_hash != policy.get("source_text_sha256"):
        raise ValueError("split source text hash mismatch")

    components = list(policy.get("components", []))
    if len(components) < 2:
        raise ValueError("split policy requires at least two components")

    output: list[dict[str, Any]] = []
    expected_start = 0
    for expected_ordinal, component in enumerate(components, start=1):
        ordinal = component.get("ordinal")
        start = component.get("start")
        end = component.get("end")
        if ordinal != expected_ordinal:
            raise ValueError("split component ordinals must be contiguous and one-based")
        if not isinstance(start, int) or not isinstance(end, int):
            raise ValueError("split component offsets must be integers")
        if start != expected_start:
            raise ValueError("split component ranges must be contiguous with no gaps or overlap")
        if end <= start or end > len(source_text):
            raise ValueError("split component range is outside the source text")
        component_text = source_text[start:end]
        component_hash = text_sha256(component_text)
        if component_hash != component.get("text_sha256"):
            raise ValueError(f"split component text hash mismatch at ordinal {ordinal}")
        output.append(
            {
                "ordinal": ordinal,
                "target_reference": component["target_reference"],
                "start": start,
                "end": end,
                "text": component_text,
                "text_sha256": component_hash,
            }
        )
        expected_start = end

    if expected_start != len(source_text):
        raise ValueError("split component ranges do not cover the complete source text")
    return output


def apply_join_policy(
    source_texts: Mapping[str, str],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    _validate_common(policy, "join")
    sources = list(policy.get("sources", []))
    if len(sources) < 2:
        raise ValueError("join policy requires at least two ordered sources")

    ordered_texts: list[str] = []
    ordered_references: list[str] = []
    for expected_ordinal, source in enumerate(sources, start=1):
        if source.get("ordinal") != expected_ordinal:
            raise ValueError("join source ordinals must be contiguous and one-based")
        reference = source.get("source_reference")
        if reference not in source_texts:
            raise ValueError(f"join source text is missing: {reference}")
        text = source_texts[reference]
        if text_sha256(text) != source.get("text_sha256"):
            raise ValueError(f"join source text hash mismatch: {reference}")
        ordered_references.append(reference)
        ordered_texts.append(text)

    if set(source_texts) != set(ordered_references):
        raise ValueError("join source set does not exactly match the reviewed policy")

    separator = policy.get("separator")
    if not isinstance(separator, str):
        raise ValueError("join separator must be a string")
    output_text = separator.join(ordered_texts)
    output_hash = text_sha256(output_text)
    if output_hash != policy.get("output_text_sha256"):
        raise ValueError("joined output text hash mismatch")

    return {
        "target_reference": policy["target_reference"],
        "source_references": ordered_references,
        "separator": separator,
        "text": output_text,
        "text_sha256": output_hash,
    }
