from __future__ import annotations

from bible_os.exports import canonical_ndjson_metrics, verify_reproducible_ndjson


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
