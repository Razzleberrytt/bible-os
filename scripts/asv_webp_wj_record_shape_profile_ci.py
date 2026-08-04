from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from scripts.asv_webp_wj_record_shape_ci import (
    FOCUS_BOOKS,
    run as run_full_diagnostic,
)
from scripts.webp_adapter_smoke import load_json


CORPUS_COUNT_KEYS = (
    "record_count",
    "source_position_token_count",
    "adapter_visible_token_count",
    "token_reconciliation_delta",
    "opening_wj_line_count",
    "opening_wj_zero_token_line_count",
    "opening_wj_visible_token_count",
    "opening_add_line_count",
    "opening_add_zero_token_line_count",
    "opening_add_visible_token_count",
    "subsequent_wj_line_count",
    "subsequent_wj_visible_token_count",
    "records_with_opening_wj",
    "records_with_opening_wj_and_subsequent_lines",
    "records_with_opening_wj_and_visible_subsequent_tokens",
    "opening_wj_record_opening_visible_token_count",
    "opening_wj_record_subsequent_visible_token_count",
    "opening_wj_record_adapter_visible_token_count",
    "opening_wj_record_opening_token_share_ppm",
    "opening_wj_record_subsequent_token_share_ppm",
    "source_position_to_adapter_token_ratio_ppm",
)
BOOK_COUNT_KEYS = (
    "opening_wj_line_count",
    "opening_wj_visible_token_count",
    "opening_add_line_count",
    "opening_add_visible_token_count",
    "subsequent_wj_line_count",
    "subsequent_wj_visible_token_count",
    "records_with_opening_wj_and_subsequent_lines",
    "records_with_opening_wj_and_visible_subsequent_tokens",
    "opening_wj_record_subsequent_visible_token_count",
)


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def select_counts(summary: dict[str, Any], keys: Sequence[str]) -> dict[str, int]:
    return {key: int(summary.get(key, 0)) for key in keys}


def compact_translation(translation: dict[str, Any]) -> dict[str, Any]:
    return {
        "translation_id": translation["translation_id"],
        "book_count": translation["book_count"],
        "corpus": select_counts(translation["corpus"], CORPUS_COUNT_KEYS),
    }


def compact_book(book: dict[str, Any]) -> dict[str, Any]:
    return {
        "book_code": book["book_code"],
        **select_counts(book, BOOK_COUNT_KEYS),
    }


def build_profile(comparison: dict[str, Any]) -> dict[str, Any]:
    canonical = canonical_json_bytes(comparison)
    return {
        "profile_contract": "asv-webp-wj-record-shape-profile-v2",
        "diagnostic_contract": comparison["diagnostic_contract"],
        "comparison_sha256": hashlib.sha256(canonical).hexdigest(),
        "comparison_byte_size": len(canonical),
        "focus_books": list(FOCUS_BOOKS),
        "verse_opening_definition": comparison["verse_opening_definition"],
        "opening_wj_definition": comparison["opening_wj_definition"],
        "opening_add_definition": comparison["opening_add_definition"],
        "subsequent_line_definition": comparison["subsequent_line_definition"],
        "token_reconciliation_definition": comparison[
            "token_reconciliation_definition"
        ],
        "asv": compact_translation(comparison["asv"]),
        "webp": compact_translation(comparison["webp"]),
        "webp_books_with_opening_wj": [
            compact_book(book)
            for book in comparison["webp"]["books_with_opening_wj"]
        ],
        "asv_books_with_opening_add": [
            compact_book(book)
            for book in comparison["asv"]["books_with_opening_add"]
        ],
        "scripture_text_reported": comparison["scripture_text_reported"],
        "token_lists_reported": comparison["token_lists_reported"],
        "locator_identifiers_reported": comparison[
            "locator_identifiers_reported"
        ],
        "per_locator_text_digests_reported": comparison[
            "per_locator_text_digests_reported"
        ],
        "text_boundaries_defined": comparison["text_boundaries_defined"],
        "parser_behavior_changed": comparison["parser_behavior_changed"],
        "corpus_mutation": comparison["corpus_mutation"],
        "mapping_authority": comparison["mapping_authority"],
        "execution_eligible": comparison["execution_eligible"],
        "publication_eligible": comparison["publication_eligible"],
    }


def assert_expected(observed: dict[str, Any], expected: dict[str, Any]) -> None:
    if observed != expected:
        observed_bytes = canonical_json_bytes(observed)
        expected_bytes = canonical_json_bytes(expected)
        raise ValueError(
            "ASV/WEBP wj record-shape profile mismatch: "
            f"expected {len(expected_bytes)} canonical bytes, "
            f"observed {len(observed_bytes)} canonical bytes"
        )


def run(expected_path: Path | None = None) -> dict[str, Any]:
    full_report = run_full_diagnostic()
    profile = build_profile(full_report["comparison"])

    if expected_path is None:
        profile_status = "observed-unpinned"
    else:
        assert_expected(profile, load_json(expected_path))
        profile_status = "matched"

    return {
        "status": "passed",
        "experiment": "asv-webp-wj-record-shape-v2",
        "asv_artifact_sha256": full_report["asv_artifact_sha256"],
        "webp_artifact_sha256": full_report["webp_artifact_sha256"],
        "profile": profile,
        "profile_status": profile_status,
        "expected_profile": str(expected_path) if expected_path is not None else None,
        "full_comparison_reported": False,
        "corpus_bytes_committed": False,
        "scripture_text_reported": False,
        "token_lists_reported": False,
        "locator_identifiers_reported": False,
        "per_locator_text_digests_reported": False,
        "text_boundaries_defined": False,
        "parser_behavior_changed": False,
        "mapping_authority": "none",
        "execution_eligible": False,
        "publication_eligible": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reproduce a compact text-private ASV/WEBP verse-opening wj profile"
        )
    )
    parser.add_argument("--expected", type=Path)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("asv-webp-wj-record-shape-report.json"),
    )
    args = parser.parse_args(argv)

    report = run(args.expected)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
