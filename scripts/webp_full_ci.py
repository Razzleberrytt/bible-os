from __future__ import annotations

import argparse
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from bible_os.exports import verify_reproducible_ndjson
from scripts.webp_adapter_smoke import download_verified_archive, load_json
from scripts.webp_db_load import (
    ARTIFACT_PATH,
    CORPUS_ID,
    IDENTITY_NAMESPACE,
    PROFILE_PATH,
    TARGET_PATH,
    load_database,
    source_rows,
    validate_database,
)


def export_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "schema_version": "0.1.0-parse-smoke",
            "identity_namespace": IDENTITY_NAMESPACE,
            "corpus_id": CORPUS_ID,
            "source_sequence": row["sequence"],
            "source_file": row["source_file"],
            "book_code": row["book_code"],
            "chapter": row["chapter"],
            "verse": row["verse"],
            "osis": row["osis"],
            "display_reference": row["display_reference"],
            "passage_id": row["passage_id"],
            "reference_id": row["reference_id"],
            "mapping_id": row["mapping_id"],
            "text_unit_id": row["text_unit_id"],
            "realization_type": row["realization_type"],
            "source_text": row["source_text"],
            "raw_payload_sha256": row["raw_payload_sha256"],
            "source_text_sha256": row["source_text_sha256"],
            "mapping_state": "uncertain/unreviewed",
            "publication_eligible": False,
        }
        for row in rows
    ]


def assert_expected(metrics: dict[str, Any], expected: dict[str, Any]) -> None:
    for key, expected_value in expected.items():
        if key.startswith("_"):
            continue
        observed = metrics.get(key)
        if observed != expected_value:
            raise ValueError(
                f"normalized export fingerprint mismatch for {key}: "
                f"expected {expected_value!r}, observed {observed!r}"
            )


def run(database_url: str, expected_path: Path | None = None) -> dict[str, Any]:
    target = load_json(TARGET_PATH)
    artifact = load_json(ARTIFACT_PATH)
    profile = load_json(PROFILE_PATH)

    with tempfile.TemporaryDirectory(prefix="bible-os-webp-full-ci-") as temp_dir:
        archive_path = Path(temp_dir) / artifact["filename"]
        download_verified_archive(target, archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            rows = source_rows(archive)

    if len(rows) != profile["verse_records"]:
        raise ValueError(
            f"parsed row count mismatch: expected {profile['verse_records']}, got {len(rows)}"
        )

    metrics = verify_reproducible_ndjson(export_records(rows))
    metrics.update(
        {
            "profile": "WEBP provisional normalized export",
            "artifact_sha256": artifact["sha256"],
            "publication_eligible": False,
            "retention": "serialized bytes hashed in memory and discarded",
        }
    )
    if expected_path is not None:
        assert_expected(metrics, load_json(expected_path))
        metrics["expected_profile"] = str(expected_path)
        metrics["profile_status"] = "matched"
    else:
        metrics["profile_status"] = "observed-unpinned"

    load_database(database_url, rows)
    database_report = validate_database(database_url, profile, artifact["artifact_id"])
    return {
        "status": "passed",
        "normalized_export": metrics,
        "database": database_report,
        "corpus_bytes_committed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fingerprint and load the verified WEBP corpus without retaining corpus bytes"
    )
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--expected-export", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")

    report = run(args.database_url, args.expected_export)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
