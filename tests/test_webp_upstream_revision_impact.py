from __future__ import annotations

import json
from pathlib import Path

from scripts.webp_upstream_revision_impact import compare_export
from scripts.webp_upstream_revision_lexical_projection import (
    compare_profile,
    micah_3_11_legacy_bigram_diagnostic,
)

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_PATH = ROOT / "registry" / "experiments" / "webp-upstream-revision-impact-20260808.json"


def fingerprint(sha256: str = "a" * 64, byte_size: int = 100) -> dict:
    return {
        "format": "application/x-ndjson; charset=utf-8",
        "canonicalization": "json-sort-keys-compact-lf-v1",
        "sha256": sha256,
        "byte_size": byte_size,
        "record_count": 31_103,
    }


def test_compare_export_recognizes_equivalent_normalized_stream() -> None:
    baseline = fingerprint()
    comparison = compare_export(fingerprint(), baseline)

    assert comparison["normalized_export_equivalent"] is True
    assert all(item["matches"] for item in comparison["comparisons"].values())


def test_compare_export_detects_changed_normalized_stream() -> None:
    baseline = fingerprint()
    observed = fingerprint(sha256="b" * 64, byte_size=101)
    comparison = compare_export(observed, baseline)

    assert comparison["normalized_export_equivalent"] is False
    assert comparison["comparisons"]["sha256"]["matches"] is False
    assert comparison["comparisons"]["byte_size"]["matches"] is False
    assert comparison["comparisons"]["record_count"]["matches"] is True


def test_compare_profile_ignores_profile_metadata_and_matches_values() -> None:
    baseline = {"_profile_version": "1.0.0", "sha256": "a" * 64, "record_count": 10}
    observed = {"sha256": "a" * 64, "record_count": 10, "extra_runtime_metric": True}

    comparison = compare_profile(observed, baseline)

    assert comparison["lexical_projection_equivalent"] is True
    assert comparison["mismatched_keys"] == []


def test_compare_profile_reports_mismatched_keys() -> None:
    baseline = {"_profile_version": "1.0.0", "sha256": "a" * 64, "record_count": 10}
    observed = {"sha256": "b" * 64, "record_count": 10}

    comparison = compare_profile(observed, baseline)

    assert comparison["lexical_projection_equivalent"] is False
    assert comparison["mismatched_keys"] == ["sha256"]


def webp_row(source_text: str) -> dict:
    return {
        "book_code": "MIC",
        "chapter": 3,
        "verse": 11,
        "realization_type": "text",
        "source_text": source_text,
    }


def test_micah_diagnostic_detects_legacy_bigram_without_reporting_text() -> None:
    report = micah_3_11_legacy_bigram_diagnostic([webp_row("alpha of it omega")])

    assert report["legacy_bigram_present"] is True
    assert report["normalized_token_count"] == 4
    assert report["source_text_reported"] is False
    assert report["token_values_reported"] is False


def test_micah_diagnostic_confirms_legacy_bigram_absence() -> None:
    report = micah_3_11_legacy_bigram_diagnostic([webp_row("alpha omega")])

    assert report["legacy_bigram_present"] is False
    assert report["normalized_token_count"] == 2


def test_registered_revision_impact_preserves_epistemic_boundaries() -> None:
    experiment = json.loads(EXPERIMENT_PATH.read_text(encoding="utf-8"))

    assert experiment["quarantined_revision"]["accepted_as_registered_artifact"] is False
    assert experiment["normalized_export"]["byte_delta"] == -2
    assert experiment["normalized_export"]["record_count"] == 31_103
    assert experiment["lexical_projection"]["token_count_delta"] == -2
    assert experiment["micah_3_11_diagnostic"]["current_quarantined_normalized_token_count"] == 38
    assert (
        experiment["micah_3_11_diagnostic"][
            "legacy_two_token_signature_present_in_current_quarantined_revision"
        ]
        is False
    )
    assert experiment["interpretation"]["best_supported_localization"] == "MIC 3:11"
    assert experiment["interpretation"]["semantic_drift_claimed"] is False
    assert experiment["interpretation"]["meaning_change_claimed"] is False
    assert experiment["registered_artifact_mutated"] is False
    assert experiment["baseline_mutated"] is False
    assert experiment["publication_eligible"] is False
