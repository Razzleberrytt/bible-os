from __future__ import annotations

from scripts.webp_upstream_revision_impact import compare_export
from scripts.webp_upstream_revision_lexical_projection import compare_profile


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
