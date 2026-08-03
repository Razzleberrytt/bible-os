from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any


def canonical_ndjson_metrics(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Hash canonical UTF-8 NDJSON without retaining the serialized dataset."""

    digest = hashlib.sha256()
    byte_size = 0
    record_count = 0
    for record in records:
        encoded = (
            json.dumps(
                dict(record),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        digest.update(encoded)
        byte_size += len(encoded)
        record_count += 1
    return {
        "format": "application/x-ndjson; charset=utf-8",
        "canonicalization": "json-sort-keys-compact-lf-v1",
        "sha256": digest.hexdigest(),
        "byte_size": byte_size,
        "record_count": record_count,
    }


def verify_reproducible_ndjson(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    first = canonical_ndjson_metrics(records)
    second = canonical_ndjson_metrics(records)
    if first != second:
        raise ValueError(f"canonical NDJSON fingerprint changed between runs: {first} != {second}")
    return {**first, "runs_compared": 2, "reproducibility_status": "verified"}
