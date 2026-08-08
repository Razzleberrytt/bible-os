from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DRIFT_EVENT_PATH = ROOT / "registry" / "acquisition-events" / "engwebp-usfm-20260808-drift.json"
FORMAT_CATALOG_URL = "https://ebible.org/bible/details.php?all=1&id=engwebp"
SCRIPTS_DIRECTORY_URL = "https://ebible.org/Scriptures/dir.php"
USER_AGENT = "Bible-OS-WEBP-Format-Revision-State/0.1 (+https://github.com/Razzleberrytt/bible-os)"
CHUNK_SIZE = 1024 * 1024
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024

DELIVERY_ARTIFACTS = (
    ("usfm", "https://ebible.org/Scriptures/engwebp_usfm.zip"),
    ("html", "https://ebible.org/Scriptures/engwebp_html.zip"),
    ("usfx", "https://ebible.org/Scriptures/engwebp_usfx.zip"),
    ("vpl", "https://ebible.org/Scriptures/engwebp_vpl.zip"),
    ("readaloud", "https://ebible.org/Scriptures/engwebp_readaloud.zip"),
    ("browserBible", "https://ebible.org/Scriptures/engwebp_browserBible.zip"),
    ("xetex", "https://ebible.org/Scriptures/engwebp_xetex.zip"),
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def observe_zip(format_name: str, url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    digest = hashlib.sha256()
    byte_size = 0

    with tempfile.TemporaryDirectory(prefix=f"bible-os-webp-{format_name}-") as temp_dir:
        archive_path = Path(temp_dir) / f"{format_name}.zip"
        with urllib.request.urlopen(request, timeout=90) as response, archive_path.open("wb") as output:
            headers = {
                "content_type": response.headers.get("Content-Type", ""),
                "content_length": response.headers.get("Content-Length", ""),
                "last_modified": response.headers.get("Last-Modified", ""),
                "etag": response.headers.get("ETag", ""),
                "resolved_url": response.geturl(),
            }
            while chunk := response.read(CHUNK_SIZE):
                byte_size += len(chunk)
                if byte_size > MAX_ARTIFACT_BYTES:
                    raise ValueError(
                        f"{format_name} exceeded the {MAX_ARTIFACT_BYTES}-byte safety limit"
                    )
                digest.update(chunk)
                output.write(chunk)

        with zipfile.ZipFile(archive_path) as archive:
            damaged = archive.testzip()
            if damaged is not None:
                raise ValueError(f"{format_name} contains corrupt ZIP member: {damaged}")
            entries = archive.infolist()
            file_entries = [entry for entry in entries if not entry.is_dir()]

    return {
        "format": format_name,
        "requested_url": url,
        "resolved_url": headers["resolved_url"],
        "sha256": digest.hexdigest(),
        "byte_size": byte_size,
        "zip_entry_count": len(entries),
        "zip_file_entry_count": len(file_entries),
        "http": {
            "content_type": headers["content_type"],
            "content_length": headers["content_length"],
            "last_modified": headers["last_modified"],
            "etag": headers["etag"],
        },
        "archive_safe": True,
    }


def parse_last_modified(value: str) -> datetime | None:
    if not value:
        return None
    parsed = parsedate_to_datetime(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def summarize_revision_state(observations: list[dict[str, Any]]) -> dict[str, Any]:
    date_groups: dict[str, list[str]] = defaultdict(list)
    parsed_times: list[tuple[str, datetime]] = []
    missing_last_modified: list[str] = []

    for observation in observations:
        parsed = parse_last_modified(observation["http"]["last_modified"])
        if parsed is None:
            missing_last_modified.append(observation["format"])
            continue
        date_groups[parsed.date().isoformat()].append(observation["format"])
        parsed_times.append((observation["format"], parsed))

    sorted_groups = {
        date: sorted(formats)
        for date, formats in sorted(date_groups.items(), key=lambda item: item[0])
    }
    if parsed_times:
        oldest_format, oldest = min(parsed_times, key=lambda item: item[1])
        latest_format, latest = max(parsed_times, key=lambda item: item[1])
        lag_seconds = int((latest - oldest).total_seconds())
        oldest_iso = oldest.isoformat().replace("+00:00", "Z")
        latest_iso = latest.isoformat().replace("+00:00", "Z")
    else:
        oldest_format = latest_format = None
        oldest_iso = latest_iso = None
        lag_seconds = None

    return {
        "artifact_count": len(observations),
        "last_modified_date_groups": sorted_groups,
        "last_modified_date_group_count": len(sorted_groups),
        "missing_last_modified_formats": sorted(missing_last_modified),
        "oldest_last_modified_format": oldest_format,
        "oldest_last_modified": oldest_iso,
        "latest_last_modified_format": latest_format,
        "latest_last_modified": latest_iso,
        "max_observed_modification_lag_seconds": lag_seconds,
        "delivery_artifact_modification_skew_detected": len(sorted_groups) > 1,
    }


def run() -> dict[str, Any]:
    drift_event = load_json(DRIFT_EVENT_PATH)
    observations = [observe_zip(format_name, url) for format_name, url in DELIVERY_ARTIFACTS]
    by_format = {observation["format"]: observation for observation in observations}

    usfm = by_format["usfm"]
    expected_usfm_sha256 = drift_event["observed_sha256"]
    expected_usfm_bytes = int(drift_event["observed_bytes"])
    if usfm["sha256"] != expected_usfm_sha256 or usfm["byte_size"] != expected_usfm_bytes:
        raise ValueError(
            "live USFM artifact no longer matches the quarantined revision that anchors this study: "
            f"expected {expected_usfm_bytes} bytes/{expected_usfm_sha256}, "
            f"observed {usfm['byte_size']} bytes/{usfm['sha256']}"
        )

    return {
        "study_contract": "webp-format-revision-state-v1",
        "source_id": drift_event["source_id"],
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "publisher_catalog_evidence": {
            "format_catalog_url": FORMAT_CATALOG_URL,
            "scripts_directory_url": SCRIPTS_DIRECTORY_URL,
            "relationship_claim": "listed as official WEBP delivery artifacts by eBible.org",
        },
        "usfm_anchor": {
            "quarantined_event_id": drift_event["event_id"],
            "sha256": expected_usfm_sha256,
            "byte_size": expected_usfm_bytes,
            "matches_quarantined_revision": True,
        },
        "delivery_artifacts": observations,
        "revision_state_summary": summarize_revision_state(observations),
        "interpretation_boundary": {
            "artifact_level_skew_only": True,
            "semantic_equivalence_claimed": False,
            "textual_equivalence_claimed": False,
            "meaning_change_claimed": False,
            "synchronized_revision_claimed": False,
        },
        "corpus_bytes_retained": False,
        "scripture_text_reported": False,
        "publication_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fingerprint WEBP delivery artifacts and measure modification-time skew"
    )
    parser.add_argument("--report", type=Path, default=Path("webp-format-revision-state.json"))
    args = parser.parse_args()

    report = run()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
