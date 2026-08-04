from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from scripts.asv_webp_gospel_structure_ci import run as run_full_diagnostic
from scripts.webp_adapter_smoke import load_json


CORPUS_TOTAL_KEYS = (
    "translation_id",
    "book_count",
    "source_file_count",
    "source_bytes",
    "compressed_bytes",
    "source_line_count",
    "record_count",
    "text_record_count",
    "empty_record_count",
    "payload_line_count",
    "payload_marker_count",
    "visible_token_count",
)

BOOK_COUNT_KEYS = (
    "source_bytes",
    "compressed_bytes",
    "source_line_count",
    "source_marker_count",
    "record_count",
    "text_record_count",
    "empty_record_count",
    "payload_bytes",
    "payload_line_count",
    "payload_nonempty_line_count",
    "unmarked_payload_line_count",
    "unmarked_line_local_token_count",
    "visible_token_count",
    "tokens_per_record_milli",
    "payload_marker_count",
    "leading_marker_line_count",
)

BOOK_RATIO_KEYS = (
    "visible_token_delta",
    "visible_token_ratio_ppm",
    "source_byte_ratio_ppm",
    "source_line_ratio_ppm",
    "payload_line_ratio_ppm",
    "record_ratio_ppm",
    "tokens_per_record_ratio_ppm",
    "payload_marker_ratio_ppm",
)


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def compact_corpus_totals(totals: dict[str, Any]) -> dict[str, Any]:
    return {key: totals[key] for key in CORPUS_TOTAL_KEYS}


def compact_translation_book(book: dict[str, Any]) -> dict[str, Any]:
    compact = {key: book[key] for key in BOOK_COUNT_KEYS}
    compact["payload_marker_class_counts"] = book["payload_marker_class_counts"]
    compact["leading_marker_class_line_counts"] = book[
        "leading_marker_class_line_counts"
    ]
    compact["leading_marker_class_line_local_token_counts"] = book[
        "leading_marker_class_line_local_token_counts"
    ]
    return compact


def compact_focus_book(row: dict[str, Any]) -> dict[str, Any]:
    compact = {"book_code": row["book_code"]}
    compact.update({key: row[key] for key in BOOK_RATIO_KEYS})
    compact["asv"] = compact_translation_book(row["asv"])
    compact["webp"] = compact_translation_book(row["webp"])
    compact["payload_marker_class_comparison"] = row[
        "payload_marker_class_comparison"
    ]
    compact["leading_marker_line_class_comparison"] = row[
        "leading_marker_line_class_comparison"
    ]
    compact["leading_marker_line_local_token_class_comparison"] = row[
        "leading_marker_line_local_token_class_comparison"
    ]
    return compact


def build_profile(comparison: dict[str, Any]) -> dict[str, Any]:
    canonical = canonical_json_bytes(comparison)
    return {
        "profile_contract": "asv-webp-gospel-structure-profile-v1",
        "diagnostic_contract": comparison["diagnostic_contract"],
        "comparison_sha256": hashlib.sha256(canonical).hexdigest(),
        "comparison_byte_size": len(canonical),
        "shared_book_count": comparison["shared_book_count"],
        "focus_books": comparison["focus_books"],
        "gospel_books": comparison["gospel_books"],
        "control_books": comparison["control_books"],
        "asv_corpus_totals": compact_corpus_totals(
            comparison["asv_corpus_totals"]
        ),
        "webp_corpus_totals": compact_corpus_totals(
            comparison["webp_corpus_totals"]
        ),
        "highest_visible_token_ratio_books": comparison[
            "highest_visible_token_ratio_books"
        ],
        "focus_book_profiles": [
            compact_focus_book(row)
            for row in comparison["focus_book_comparisons"]
        ],
        "scripture_text_reported": comparison["scripture_text_reported"],
        "token_lists_reported": comparison["token_lists_reported"],
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
            "ASV/WEBP Gospel structure profile mismatch: "
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
        "experiment": "asv-webp-gospel-structure-diagnostic-v1",
        "asv_artifact_sha256": full_report["asv_artifact_sha256"],
        "webp_artifact_sha256": full_report["webp_artifact_sha256"],
        "profile": profile,
        "profile_status": profile_status,
        "expected_profile": str(expected_path) if expected_path is not None else None,
        "full_comparison_reported": False,
        "corpus_bytes_committed": False,
        "scripture_text_reported": False,
        "token_lists_reported": False,
        "per_locator_text_digests_reported": False,
        "text_boundaries_defined": False,
        "mapping_authority": "none",
        "execution_eligible": False,
        "publication_eligible": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reproduce a compact text-private ASV/WEBP Gospel structure profile"
    )
    parser.add_argument("--expected", type=Path)
    parser.add_argument(
        "--report", type=Path, default=Path("asv-webp-gospel-structure-report.json")
    )
    args = parser.parse_args(argv)

    report = run(args.expected)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
