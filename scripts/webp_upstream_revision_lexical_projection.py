from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from scripts.asv_full_ci import ARTIFACT_PATH as ASV_ARTIFACT_PATH
from scripts.asv_full_ci import source_rows as asv_source_rows
from scripts.asv_webp_lexical_fingerprint_ci import (
    ASV_TARGET_PATH,
    build_fingerprint_records,
    summarize_fingerprints,
)
from scripts.webp_adapter_smoke import download_verified_archive
from scripts.webp_db_load import source_rows as webp_source_rows
from scripts.webp_upstream_revision_impact import (
    DRIFT_EVENT_PATH,
    TARGET_PATH,
    download_quarantined_revision,
    load_json,
)

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "registry" / "experiments" / "asv-webp-lexical-fingerprints.json"
OFFICIAL_2026_08_05_WEBP_CANDIDATES = ("MIC 3:11", "DAN 4:19", "DAN 6:11", "NEH 13:5")


def compare_profile(observed: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    comparisons: dict[str, dict[str, Any]] = {}
    for key, baseline_value in baseline.items():
        if key.startswith("_"):
            continue
        observed_value = observed.get(key)
        comparisons[key] = {
            "baseline": baseline_value,
            "observed": observed_value,
            "matches": observed_value == baseline_value,
        }
    mismatched_keys = [key for key, item in comparisons.items() if not item["matches"]]
    return {
        "lexical_projection_equivalent": not mismatched_keys,
        "mismatched_keys": mismatched_keys,
        "comparisons": comparisons,
    }


def candidate_metrics(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_locator = {record["locator"]: record for record in records}
    result: list[dict[str, Any]] = []
    for locator in OFFICIAL_2026_08_05_WEBP_CANDIDATES:
        record = by_locator.get(locator)
        if record is None:
            raise ValueError(f"official WEBP update candidate missing from lexical projection: {locator}")
        result.append(
            {
                "locator": locator,
                "asv_token_count": record["asv_token_count"],
                "webp_token_count": record["webp_token_count"],
                "token_count_delta": record["token_count_delta"],
                "token_edit_distance": record["token_edit_distance"],
                "token_edit_distance_ppm": record["token_edit_distance_ppm"],
                "token_set_jaccard_distance_ppm": record["token_set_jaccard_distance_ppm"],
                "normalized_token_sequence_equal_to_asv": record[
                    "normalized_token_sequence_equal"
                ],
            }
        )
    return result


def run() -> dict[str, Any]:
    asv_target = load_json(ASV_TARGET_PATH)
    asv_artifact = load_json(ASV_ARTIFACT_PATH)
    webp_target = load_json(TARGET_PATH)
    drift_event = load_json(DRIFT_EVENT_PATH)
    baseline = load_json(BASELINE_PATH)

    with tempfile.TemporaryDirectory(prefix="bible-os-webp-drift-lexical-") as temp_dir:
        temp_root = Path(temp_dir)
        asv_path = temp_root / asv_artifact["filename"]
        webp_path = temp_root / "engwebp_usfm-quarantined.zip"
        download_verified_archive(asv_target, asv_path)
        webp_observation = download_quarantined_revision(webp_target, drift_event, webp_path)
        with zipfile.ZipFile(asv_path) as archive:
            asv_rows = asv_source_rows(archive)
        with zipfile.ZipFile(webp_path) as archive:
            webp_rows = webp_source_rows(archive)

    records = build_fingerprint_records(asv_rows, webp_rows)
    observed = summarize_fingerprints(records)
    projection = compare_profile(observed, baseline)
    return {
        "study_contract": "webp-upstream-revision-lexical-projection-v1",
        "asv_artifact_sha256": asv_artifact["sha256"],
        "registered_webp_sha256": webp_target["expected_sha256"],
        "quarantined_webp_sha256": webp_observation["observed_sha256"],
        "official_update_date": "2026-08-05",
        "official_update_candidates": list(OFFICIAL_2026_08_05_WEBP_CANDIDATES),
        "candidate_metrics": candidate_metrics(records),
        "lexical_projection": projection,
        "observed_summary": {
            "sha256": observed["sha256"],
            "byte_size": observed["byte_size"],
            "record_count": observed["record_count"],
            "shared_text_locator_count": observed["shared_text_locator_count"],
            "webp_total_token_count": observed["webp_total_token_count"],
            "normalized_equal_locator_count": observed["normalized_equal_locator_count"],
            "same_token_count_locator_count": observed["same_token_count_locator_count"],
        },
        "scripture_text_reported": False,
        "token_lists_reported": False,
        "per_locator_text_digests_reported": False,
        "corpus_bytes_retained": False,
        "registered_artifact_mutated": False,
        "baseline_mutated": False,
        "publication_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare quarantined WEBP lexical projection to the frozen ASV/WEBP profile"
    )
    parser.add_argument(
        "--report", type=Path, default=Path("webp-upstream-revision-lexical-projection.json")
    )
    args = parser.parse_args()
    report = run()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
