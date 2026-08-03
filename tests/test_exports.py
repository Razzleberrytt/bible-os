from __future__ import annotations

import json
from pathlib import Path

from bible_os.exports import canonical_ndjson_metrics, verify_reproducible_ndjson

ROOT = Path(__file__).resolve().parents[1]


def test_canonical_ndjson_ignores_mapping_key_order():
    first = canonical_ndjson_metrics([{"b": 2, "a": "α"}])
    second = canonical_ndjson_metrics([{"a": "α", "b": 2}])
    assert first == second
    assert first["record_count"] == 1
    assert first["byte_size"] > 0


def test_record_order_remains_semantically_significant():
    forward = canonical_ndjson_metrics([{"sequence": 1}, {"sequence": 2}])
    reverse = canonical_ndjson_metrics([{"sequence": 2}, {"sequence": 1}])
    assert forward["sha256"] != reverse["sha256"]


def test_reproducibility_requires_identical_full_passes():
    metrics = verify_reproducible_ndjson(
        [
            {"source_sequence": 1, "source_text": "Synthetic text."},
            {"source_sequence": 2, "source_text": None},
        ]
    )
    assert metrics["runs_compared"] == 2
    assert metrics["reproducibility_status"] == "verified"
    assert metrics["record_count"] == 2


def test_pinned_webp_export_profile_is_non_publishable_and_complete():
    profile = json.loads(
        (ROOT / "registry/import-profiles/engwebp-normalized-export.json").read_text(
            encoding="utf-8"
        )
    )
    assert profile["artifact_sha256"] == (
        "9b4330ba6baf9bd5fa8ea63a8ff255c9ab326da8c843f0355c23734e61ee6276"
    )
    assert profile["sha256"] == (
        "5d721a56a3ef94a914255617203460ebf8976cd845f40d47e2963be74fce6568"
    )
    assert profile["byte_size"] == 27_680_660
    assert profile["record_count"] == 31_103
    assert profile["runs_compared"] == 2
    assert profile["reproducibility_status"] == "verified"
    assert profile["publication_eligible"] is False
