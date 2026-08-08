from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.asv_webp_lexical_fingerprint_ci import normalize_tokens
from scripts.probe_acquisition import CHUNK_SIZE, USER_AGENT, safe_zip_members
from scripts.webp_db_load import source_rows as webp_source_rows
from scripts.webp_usfm_html_candidate_equivalence import (
    VisibleTextParser,
    candidate_usfm_tokens,
    count_subsequence,
    download_pinned,
    find_member_by_basename,
)

ROOT = Path(__file__).resolve().parents[1]
FORMAT_STATE_PATH = ROOT / "registry" / "experiments" / "webp-format-revision-state-20260808.json"
SERVED_PAGE_URL = "https://ebible.org/engwebp/MIC03.htm"
HTML_MEMBER_BASENAME = "MIC03.htm"
LOCATOR = "MIC 3:11"
MAX_SERVED_PAGE_BYTES = 2 * 1024 * 1024


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def artifact_record(experiment: dict[str, Any], format_name: str) -> dict[str, Any]:
    matches = [
        item for item in experiment["delivery_artifacts"] if item.get("format") == format_name
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {format_name} artifact record, found {len(matches)}")
    return matches[0]


def visible_tokens(raw_html: bytes) -> tuple[str, ...]:
    try:
        rendered = raw_html.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("HTML surface is not valid UTF-8") from error
    parser = VisibleTextParser()
    parser.feed(rendered)
    parser.close()
    return parser.normalized_tokens()


def token_sequence_sha256(tokens: tuple[str, ...]) -> str:
    canonical = "\n".join(tokens).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def observe_served_page(url: str = SERVED_PAGE_URL) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.1"},
    )
    body = bytearray()
    with urllib.request.urlopen(request, timeout=60) as response:
        headers = {
            "content_type": response.headers.get("Content-Type", ""),
            "content_length": response.headers.get("Content-Length", ""),
            "last_modified": response.headers.get("Last-Modified", ""),
            "etag": response.headers.get("ETag", ""),
            "cache_control": response.headers.get("Cache-Control", ""),
            "age": response.headers.get("Age", ""),
            "date": response.headers.get("Date", ""),
            "resolved_url": response.geturl(),
        }
        while chunk := response.read(CHUNK_SIZE):
            body.extend(chunk)
            if len(body) > MAX_SERVED_PAGE_BYTES:
                raise ValueError("served page exceeded the safety limit")

    raw = bytes(body)
    tokens = visible_tokens(raw)
    return {
        "requested_url": url,
        "resolved_url": headers["resolved_url"],
        "byte_size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "visible_normalized_token_count": len(tokens),
        "visible_normalized_token_sha256": token_sequence_sha256(tokens),
        "tokens": tokens,
        "http": {
            key: value for key, value in headers.items() if key != "resolved_url"
        },
    }


def package_member_observation(archive: zipfile.ZipFile) -> dict[str, Any]:
    member = find_member_by_basename(archive, HTML_MEMBER_BASENAME)
    raw = archive.read(member)
    tokens = visible_tokens(raw)
    return {
        "member": member.filename,
        "byte_size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "visible_normalized_token_count": len(tokens),
        "visible_normalized_token_sha256": token_sequence_sha256(tokens),
        "tokens": tokens,
    }


def compare_surfaces(
    current_usfm_tokens: tuple[str, ...],
    package: dict[str, Any],
    served: dict[str, Any],
) -> dict[str, Any]:
    package_tokens = package["tokens"]
    served_tokens = served["tokens"]
    package_occurrences = count_subsequence(package_tokens, current_usfm_tokens)
    served_occurrences = count_subsequence(served_tokens, current_usfm_tokens)
    return {
        "locator": LOCATOR,
        "current_usfm_normalized_token_count": len(current_usfm_tokens),
        "current_sequence_occurrences_in_downloadable_html_member": package_occurrences,
        "current_sequence_occurrences_in_served_page": served_occurrences,
        "downloadable_member_and_served_page_byte_equal": package["sha256"] == served["sha256"],
        "downloadable_member_and_served_page_normalized_visible_sequence_equal": (
            package["visible_normalized_token_sha256"]
            == served["visible_normalized_token_sha256"]
            and package["visible_normalized_token_count"]
            == served["visible_normalized_token_count"]
        ),
        "current_sequence_delivery_surface_divergence_detected": (
            package_occurrences > 0 and served_occurrences == 0
        ),
    }


def run() -> dict[str, Any]:
    format_state = load_json(FORMAT_STATE_PATH)
    usfm_record = artifact_record(format_state, "usfm")
    html_record = artifact_record(format_state, "html")

    with tempfile.TemporaryDirectory(prefix="bible-os-webp-served-package-") as temp_dir:
        temp_root = Path(temp_dir)
        usfm_path = temp_root / "engwebp_usfm.zip"
        html_path = temp_root / "engwebp_html.zip"
        usfm_artifact = download_pinned(usfm_record, usfm_path)
        html_artifact = download_pinned(html_record, html_path)

        with zipfile.ZipFile(usfm_path) as archive:
            safe_zip_members(archive)
            rows = webp_source_rows(archive)
            current_usfm_tokens = candidate_usfm_tokens(rows, LOCATOR)
        with zipfile.ZipFile(html_path) as archive:
            safe_zip_members(archive)
            package = package_member_observation(archive)

    served = observe_served_page()
    comparison = compare_surfaces(current_usfm_tokens, package, served)

    package_public = {key: value for key, value in package.items() if key != "tokens"}
    served_public = {key: value for key, value in served.items() if key != "tokens"}
    return {
        "study_contract": "webp-served-page-package-state-v1",
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_id": format_state["source_id"],
        "normalization_contract": "unicode-nfkc-casefold-alnum-apostrophe-token-v1",
        "pinned_artifacts": {
            "usfm": usfm_artifact,
            "html": html_artifact,
        },
        "downloadable_html_member": package_public,
        "served_html_page": served_public,
        "comparison": comparison,
        "interpretation_boundary": {
            "delivery_surface_state_only": True,
            "cache_cause_claimed": False,
            "deployment_cause_claimed": False,
            "publisher_intent_claimed": False,
            "semantic_drift_claimed": False,
            "meaning_change_claimed": False,
        },
        "scripture_text_reported": False,
        "token_lists_reported": False,
        "corpus_bytes_retained": False,
        "publication_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare the live served WEBP Micah page with the pinned downloadable HTML member"
    )
    parser.add_argument("--report", type=Path, default=Path("webp-served-page-package-state.json"))
    args = parser.parse_args()
    report = run()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
