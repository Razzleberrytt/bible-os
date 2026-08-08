from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from bible_os.exports import verify_reproducible_ndjson
from scripts.probe_acquisition import CHUNK_SIZE, MAX_SIZE_MARGIN, USER_AGENT, safe_zip_members
from scripts.webp_db_load import source_rows
from scripts.webp_full_ci import export_records

ROOT = Path(__file__).resolve().parents[1]
TARGET_PATH = ROOT / "registry" / "acquisitions" / "engwebp-usfm.json"
DRIFT_EVENT_PATH = ROOT / "registry" / "acquisition-events" / "engwebp-usfm-20260808-drift.json"
BASELINE_PATH = ROOT / "registry" / "import-profiles" / "engwebp-normalized-export.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def download_quarantined_revision(
    target: dict[str, Any], drift_event: dict[str, Any], destination: Path
) -> dict[str, Any]:
    expected_bytes = int(target["expected_bytes"])
    quarantine_bytes = int(drift_event["observed_bytes"])
    quarantine_sha256 = drift_event["observed_sha256"]
    request = urllib.request.Request(
        target["requested_url"],
        headers={"User-Agent": USER_AGENT, "Accept": "application/zip,*/*;q=0.1"},
    )
    digest = hashlib.sha256()
    observed_bytes = 0

    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
        response_headers = {
            "content_length": response.headers.get("Content-Length", ""),
            "last_modified": response.headers.get("Last-Modified", ""),
            "etag": response.headers.get("ETag", ""),
            "resolved_url": response.geturl(),
        }
        while chunk := response.read(CHUNK_SIZE):
            observed_bytes += len(chunk)
            if observed_bytes > max(expected_bytes, quarantine_bytes) + MAX_SIZE_MARGIN:
                raise ValueError("download exceeded the registered drift-study safety margin")
            digest.update(chunk)
            output.write(chunk)

    observed_sha256 = digest.hexdigest()
    if observed_bytes != quarantine_bytes or observed_sha256 != quarantine_sha256:
        raise ValueError(
            "live WEBP archive no longer matches the quarantined revision under study: "
            f"expected {quarantine_bytes} bytes/{quarantine_sha256}, "
            f"observed {observed_bytes} bytes/{observed_sha256}"
        )
    return {
        "observed_bytes": observed_bytes,
        "observed_sha256": observed_sha256,
        "response_headers": response_headers,
    }


def compare_export(metrics: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    keys = ("format", "canonicalization", "sha256", "byte_size", "record_count")
    comparisons = {
        key: {
            "baseline": baseline[key],
            "observed": metrics[key],
            "matches": metrics[key] == baseline[key],
        }
        for key in keys
    }
    return {
        "comparisons": comparisons,
        "normalized_export_equivalent": all(item["matches"] for item in comparisons.values()),
    }


def run() -> dict[str, Any]:
    target = load_json(TARGET_PATH)
    drift_event = load_json(DRIFT_EVENT_PATH)
    baseline = load_json(BASELINE_PATH)

    with tempfile.TemporaryDirectory(prefix="bible-os-webp-drift-impact-") as temp_dir:
        archive_path = Path(temp_dir) / "engwebp_usfm.zip"
        observation = download_quarantined_revision(target, drift_event, archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            members = safe_zip_members(archive)
            rows = source_rows(archive)

    metrics = verify_reproducible_ndjson(export_records(rows))
    comparison = compare_export(metrics, baseline)
    return {
        "study_contract": "webp-upstream-revision-impact-v1",
        "registered_artifact": {
            "sha256": target["expected_sha256"],
            "bytes": target["expected_bytes"],
        },
        "quarantined_revision": {
            "sha256": observation["observed_sha256"],
            "bytes": observation["observed_bytes"],
            "archive_byte_delta": observation["observed_bytes"] - target["expected_bytes"],
            "zip_entries": len(members),
            "response_headers": observation["response_headers"],
        },
        "normalized_export": {
            **metrics,
            **comparison,
        },
        "interpretation": (
            "normalized-export-equivalent"
            if comparison["normalized_export_equivalent"]
            else "normalized-export-changed"
        ),
        "scripture_text_reported": False,
        "corpus_bytes_retained": False,
        "registered_artifact_mutated": False,
        "baseline_mutated": False,
        "mapping_authority": "none",
        "publication_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare a quarantined WEBP upstream revision to the frozen normalized-export baseline"
    )
    parser.add_argument("--report", type=Path, default=Path("webp-upstream-revision-impact.json"))
    args = parser.parse_args()
    report = run()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
