from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from scripts.asv_webp_wj_token_strata_ci import (
    FOCUS_BOOKS,
    run as run_full_analysis,
)
from scripts.webp_adapter_smoke import load_json


COMPACT_STRATUM_KEYS = (
    "locator_count",
    "asv_token_count",
    "webp_token_count",
    "token_count_delta",
    "webp_to_asv_total_token_ratio_ppm",
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


def rows_by_book(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["book_code"]: row for row in summary["book_summaries"]
    }


def compact_stratum(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "stratum": row["stratum"],
        **{key: int(row.get(key, 0)) for key in COMPACT_STRATUM_KEYS},
    }


def compact_book(row: dict[str, Any]) -> dict[str, Any]:
    strata = {item["stratum"]: item for item in row["strata"]}
    return {
        "book_code": row["book_code"],
        "locator_count": int(row["locator_count"]),
        "opening_wj": compact_stratum(strata["webp-opening-wj"]),
        "non_wj": compact_stratum(strata["webp-non-wj"]),
    }


def build_profile(summary: dict[str, Any]) -> dict[str, Any]:
    canonical = canonical_json_bytes(summary)
    books = rows_by_book(summary)
    books_with_opening_wj = [
        row["book_code"]
        for row in summary["book_summaries"]
        if row["strata"][0]["locator_count"]
    ]
    return {
        "profile_contract": "asv-webp-wj-token-strata-profile-v1",
        "analysis_contract": summary["analysis_contract"],
        "summary_sha256": hashlib.sha256(canonical).hexdigest(),
        "summary_byte_size": len(canonical),
        "numeric_stream": {
            "record_count": summary["record_count"],
            "byte_size": summary["byte_size"],
            "sha256": summary["sha256"],
        },
        "shared_text_text_locator_count": summary[
            "shared_text_text_locator_count"
        ],
        "strata": summary["strata"],
        "focus_books": list(FOCUS_BOOKS),
        "focus_book_profiles": [
            compact_book(books[book_code])
            for book_code in FOCUS_BOOKS
            if book_code in books
        ],
        "books_with_opening_wj": books_with_opening_wj,
        "normalization_contract": summary["normalization_contract"],
        "scripture_text_reported": summary["scripture_text_reported"],
        "token_lists_reported": summary["token_lists_reported"],
        "locator_identifiers_reported": summary[
            "locator_identifiers_reported"
        ],
        "per_locator_text_digests_reported": summary[
            "per_locator_text_digests_reported"
        ],
        "parser_behavior_changed": summary["parser_behavior_changed"],
        "text_boundaries_defined": summary["text_boundaries_defined"],
        "corpus_mutation": summary["corpus_mutation"],
        "mapping_authority": summary["mapping_authority"],
        "execution_eligible": summary["execution_eligible"],
        "publication_eligible": summary["publication_eligible"],
    }


def assert_expected(observed: dict[str, Any], expected: dict[str, Any]) -> None:
    if observed != expected:
        observed_bytes = canonical_json_bytes(observed)
        expected_bytes = canonical_json_bytes(expected)
        raise ValueError(
            "ASV/WEBP opening-wj token strata profile mismatch: "
            f"expected {len(expected_bytes)} canonical bytes, "
            f"observed {len(observed_bytes)} canonical bytes"
        )


def run(expected_path: Path | None = None) -> dict[str, Any]:
    full_report = run_full_analysis()
    profile = build_profile(full_report["summary"])

    if expected_path is None:
        profile_status = "observed-unpinned"
    else:
        assert_expected(profile, load_json(expected_path))
        profile_status = "matched"

    return {
        "status": "passed",
        "experiment": "asv-webp-wj-token-strata-v1",
        "asv_artifact_sha256": full_report["asv_artifact_sha256"],
        "webp_artifact_sha256": full_report["webp_artifact_sha256"],
        "profile": profile,
        "profile_status": profile_status,
        "expected_profile": (
            str(expected_path) if expected_path is not None else None
        ),
        "full_summary_reported": False,
        "corpus_bytes_committed": False,
        "scripture_text_reported": False,
        "token_lists_reported": False,
        "locator_identifiers_reported": False,
        "per_locator_text_digests_reported": False,
        "parser_behavior_changed": False,
        "text_boundaries_defined": False,
        "mapping_authority": "none",
        "execution_eligible": False,
        "publication_eligible": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reproduce a compact text-private ASV/WEBP opening-wj token "
            "stratification profile"
        )
    )
    parser.add_argument("--expected", type=Path)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("asv-webp-wj-token-strata-report.json"),
    )
    args = parser.parse_args(argv)

    report = run(args.expected)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
