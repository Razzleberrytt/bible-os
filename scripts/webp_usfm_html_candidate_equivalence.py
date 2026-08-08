from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import urllib.request
import zipfile
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence

from scripts.asv_webp_lexical_fingerprint_ci import locator, normalize_tokens
from scripts.probe_acquisition import CHUNK_SIZE, USER_AGENT, safe_zip_members
from scripts.webp_db_load import source_rows as webp_source_rows

ROOT = Path(__file__).resolve().parents[1]
FORMAT_STATE_PATH = ROOT / "registry" / "experiments" / "webp-format-revision-state-20260808.json"
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024

CANDIDATES = (
    ("MIC 3:11", "MIC03.htm"),
    ("DAN 4:19", "DAN04.htm"),
    ("DAN 6:11", "DAN06.htm"),
    ("NEH 13:5", "NEH13.htm"),
)


class VisibleTextParser(HTMLParser):
    """Collect visible-ish HTML text without preserving markup or emitting it."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._suppressed_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self._suppressed_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._suppressed_depth:
            self._suppressed_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._suppressed_depth and data:
            self._chunks.append(data)

    def normalized_tokens(self) -> tuple[str, ...]:
        return normalize_tokens(" ".join(self._chunks))


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def artifact_record(experiment: dict[str, Any], format_name: str) -> dict[str, Any]:
    matches = [
        item for item in experiment["delivery_artifacts"] if item.get("format") == format_name
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {format_name} artifact record, found {len(matches)}")
    return matches[0]


def download_pinned(record: dict[str, Any], destination: Path) -> dict[str, Any]:
    expected_sha256 = record["sha256"]
    expected_bytes = int(record["byte_size"])
    request = urllib.request.Request(
        record["requested_url"],
        headers={"User-Agent": USER_AGENT, "Accept": "application/zip,*/*;q=0.1"},
    )
    digest = hashlib.sha256()
    observed_bytes = 0

    with urllib.request.urlopen(request, timeout=90) as response, destination.open("wb") as output:
        while chunk := response.read(CHUNK_SIZE):
            observed_bytes += len(chunk)
            if observed_bytes > min(MAX_ARTIFACT_BYTES, expected_bytes + CHUNK_SIZE):
                raise ValueError("download exceeded the pinned artifact safety margin")
            digest.update(chunk)
            output.write(chunk)

    observed_sha256 = digest.hexdigest()
    if observed_bytes != expected_bytes or observed_sha256 != expected_sha256:
        raise ValueError(
            f"live {record['format']} artifact no longer matches the pinned observation: "
            f"expected {expected_bytes} bytes/{expected_sha256}, "
            f"observed {observed_bytes} bytes/{observed_sha256}"
        )
    return {"sha256": observed_sha256, "byte_size": observed_bytes}


def count_subsequence(haystack: Sequence[str], needle: Sequence[str]) -> int:
    if not needle or len(needle) > len(haystack):
        return 0
    width = len(needle)
    return sum(
        1
        for index in range(len(haystack) - width + 1)
        if tuple(haystack[index : index + width]) == tuple(needle)
    )


def find_member_by_basename(archive: zipfile.ZipFile, basename: str) -> zipfile.ZipInfo:
    wanted = basename.casefold()
    matches = [
        member
        for member in archive.infolist()
        if not member.is_dir() and PurePosixPath(member.filename).name.casefold() == wanted
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one HTML member named {basename}, found {len(matches)}")
    return matches[0]


def html_page_tokens(archive: zipfile.ZipFile, basename: str) -> tuple[str, tuple[str, ...]]:
    member = find_member_by_basename(archive, basename)
    raw = archive.read(member)
    try:
        rendered = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError(f"HTML member is not valid UTF-8: {member.filename}") from error
    parser = VisibleTextParser()
    parser.feed(rendered)
    parser.close()
    return member.filename, parser.normalized_tokens()


def candidate_usfm_tokens(
    rows: Iterable[dict[str, Any]], wanted_locator: str
) -> tuple[str, ...]:
    matches = [row for row in rows if locator(row) == wanted_locator]
    if len(matches) != 1:
        raise ValueError(f"expected one USFM row for {wanted_locator}, found {len(matches)}")
    row = matches[0]
    if row.get("realization_type") != "text" or not isinstance(row.get("source_text"), str):
        raise ValueError(f"USFM realization is not text at {wanted_locator}")
    tokens = normalize_tokens(row["source_text"])
    if not tokens:
        raise ValueError(f"USFM token projection is empty at {wanted_locator}")
    return tokens


def compare_candidates(
    usfm_rows: list[dict[str, Any]], html_archive: zipfile.ZipFile
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for wanted_locator, html_basename in CANDIDATES:
        usfm_tokens = candidate_usfm_tokens(usfm_rows, wanted_locator)
        member_name, page_tokens = html_page_tokens(html_archive, html_basename)
        occurrences = count_subsequence(page_tokens, usfm_tokens)
        results.append(
            {
                "locator": wanted_locator,
                "html_member": member_name,
                "usfm_normalized_token_count": len(usfm_tokens),
                "html_page_normalized_token_count": len(page_tokens),
                "exact_usfm_sequence_occurrences_in_html_page": occurrences,
                "exact_normalized_sequence_found": occurrences > 0,
            }
        )
    return results


def run() -> dict[str, Any]:
    format_state = load_json(FORMAT_STATE_PATH)
    usfm_record = artifact_record(format_state, "usfm")
    html_record = artifact_record(format_state, "html")

    with tempfile.TemporaryDirectory(prefix="bible-os-webp-usfm-html-") as temp_dir:
        temp_root = Path(temp_dir)
        usfm_path = temp_root / "engwebp_usfm.zip"
        html_path = temp_root / "engwebp_html.zip"
        usfm_observation = download_pinned(usfm_record, usfm_path)
        html_observation = download_pinned(html_record, html_path)

        with zipfile.ZipFile(usfm_path) as archive:
            safe_zip_members(archive)
            usfm_rows = webp_source_rows(archive)
        with zipfile.ZipFile(html_path) as archive:
            safe_zip_members(archive)
            comparisons = compare_candidates(usfm_rows, archive)

    exact_match_count = sum(item["exact_normalized_sequence_found"] for item in comparisons)
    return {
        "study_contract": "webp-usfm-html-candidate-equivalence-v1",
        "source_id": format_state["source_id"],
        "normalization_contract": "unicode-nfkc-casefold-alnum-apostrophe-token-v1",
        "candidate_scope": [locator_value for locator_value, _ in CANDIDATES],
        "artifacts": {
            "usfm": usfm_observation,
            "html": html_observation,
        },
        "candidate_results": comparisons,
        "summary": {
            "candidate_count": len(comparisons),
            "exact_normalized_sequence_match_count": exact_match_count,
            "all_candidates_exact_normalized_sequence_match": exact_match_count == len(comparisons),
        },
        "interpretation_boundary": {
            "candidate_loci_only": True,
            "positive_match_means_current_usfm_sequence_occurs_in_current_html_chapter": True,
            "negative_match_alone_proves_textual_disagreement": False,
            "whole_corpus_textual_equivalence_claimed": False,
            "semantic_equivalence_claimed": False,
            "meaning_change_claimed": False,
        },
        "scripture_text_reported": False,
        "token_lists_reported": False,
        "corpus_bytes_retained": False,
        "publication_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare current pinned WEBP USFM candidate sequences with the pinned HTML package"
    )
    parser.add_argument(
        "--report", type=Path, default=Path("webp-usfm-html-candidate-equivalence.json")
    )
    args = parser.parse_args()
    report = run()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
