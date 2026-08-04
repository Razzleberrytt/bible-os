from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from scripts.asv_webp_character_marker_accounting_ci import run as run_full_diagnostic
from scripts.webp_adapter_smoke import load_json


COUNT_KEYS = (
    "line_count",
    "record_count",
    "zero_token_line_count",
    "visible_token_count",
    "exact_duplicate_line_count",
    "exact_duplicate_token_count",
    "contained_duplicate_line_count",
    "contained_duplicate_token_count",
)


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def compact_counts(row: dict[str, Any], prefix: str = "") -> dict[str, int]:
    return {key: int(row.get(f"{prefix}{key}", 0)) for key in COUNT_KEYS}


def compact_marker(row: dict[str, Any]) -> dict[str, Any]:
    return {"marker": row["marker"], **compact_counts(row)}


def compact_translation(translation: dict[str, Any]) -> dict[str, Any]:
    return {
        "translation_id": translation["translation_id"],
        "book_count": translation["book_count"],
        "record_count": translation["record_count"],
        "records_with_character_style": translation[
            "records_with_character_style"
        ],
        "markers": [compact_marker(row) for row in translation["markers"]],
    }


def compact_marker_comparison(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "marker": row["marker"],
        "asv": compact_counts(row, "asv_"),
        "webp": compact_counts(row, "webp_"),
    }


def compact_focus_book(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "book_code": row["book_code"],
        "asv": compact_counts(row, "asv_"),
        "webp": compact_counts(row, "webp_"),
        "marker_comparisons": [
            compact_marker_comparison(marker_row)
            for marker_row in row["marker_comparisons"]
        ],
    }


def compact_book(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "book_code": row["book_code"],
        "record_count": row["record_count"],
        "records_with_character_style": row["records_with_character_style"],
        **compact_counts(row),
    }


def build_profile(comparison: dict[str, Any]) -> dict[str, Any]:
    canonical = canonical_json_bytes(comparison)
    return {
        "profile_contract": "asv-webp-character-marker-profile-v1",
        "diagnostic_contract": comparison["diagnostic_contract"],
        "comparison_sha256": hashlib.sha256(canonical).hexdigest(),
        "comparison_byte_size": len(canonical),
        "duplicate_definition": comparison["duplicate_definition"],
        "exact_duplicate_definition": comparison["exact_duplicate_definition"],
        "focus_books": comparison["focus_books"],
        "gospel_books": comparison["gospel_books"],
        "control_books": comparison["control_books"],
        "asv": compact_translation(comparison["asv"]),
        "webp": compact_translation(comparison["webp"]),
        "webp_books_with_character_style": [
            compact_book(row)
            for row in comparison["webp"]["books_with_character_style"]
        ],
        "focus_book_profiles": [
            compact_focus_book(row)
            for row in comparison["focus_book_comparisons"]
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
            "ASV/WEBP character marker profile mismatch: "
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
        "experiment": "asv-webp-character-marker-accounting-v1",
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
        "mapping_authority": "none",
        "execution_eligible": False,
        "publication_eligible": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reproduce a compact text-private ASV/WEBP character marker profile"
    )
    parser.add_argument("--expected", type=Path)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("asv-webp-character-marker-accounting-report.json"),
    )
    args = parser.parse_args(argv)

    report = run(args.expected)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
