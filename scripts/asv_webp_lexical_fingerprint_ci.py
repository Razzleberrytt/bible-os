from __future__ import annotations

import argparse
import json
import tempfile
import unicodedata
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

from bible_os.exports import verify_reproducible_ndjson
from bible_os.identity import stable_id
from bible_os.importers.webp_usfm import BOOK_ORDER
from scripts.asv_full_ci import ARTIFACT_PATH as ASV_ARTIFACT_PATH
from scripts.asv_full_ci import source_rows as asv_source_rows
from scripts.webp_adapter_smoke import download_verified_archive, load_json
from scripts.webp_db_load import ARTIFACT_PATH as WEBP_ARTIFACT_PATH
from scripts.webp_db_load import TARGET_PATH as WEBP_TARGET_PATH
from scripts.webp_db_load import source_rows as webp_source_rows


ROOT = Path(__file__).resolve().parents[1]
ASV_TARGET_PATH = ROOT / "registry" / "acquisitions" / "eng-asv-usfm.json"
FINGERPRINT_NAMESPACE = "bible-os:asv-webp-lexical-fingerprint:v1"
NORMALIZATION_CONTRACT = "unicode-nfkc-casefold-alnum-apostrophe-token-v1"
DISTANCE_CONTRACT = "token-levenshtein-and-token-set-jaccard-ppm-v1"
BOOK_INDEX = {code: index for index, code in enumerate(BOOK_ORDER)}
PPM = 1_000_000
EDIT_DISTANCE_BANDS = (
    ("exact", 0, 0),
    ("very-low", 1, 100_000),
    ("low", 100_001, 250_000),
    ("moderate", 250_001, 500_000),
    ("high", 500_001, 750_000),
    ("very-high", 750_001, PPM),
)


def locator(row: dict[str, Any]) -> str:
    return f"{row['book_code']} {row['chapter']}:{row['verse']}"


def locator_sort_key(value: str) -> tuple[int, int, int]:
    book, chapter_verse = value.split(" ", 1)
    chapter, verse = chapter_verse.split(":", 1)
    return BOOK_INDEX[book], int(chapter), int(verse)


def normalize_tokens(text: str) -> tuple[str, ...]:
    """Normalize English source text into deterministic comparison tokens."""

    if not isinstance(text, str):
        raise TypeError("source text must be a string")
    normalized = (
        unicodedata.normalize("NFKC", text)
        .casefold()
        .replace("\u2019", "'")
        .replace("\u02bc", "'")
    )
    tokens: list[str] = []
    current: list[str] = []
    for character in normalized:
        if character.isalnum():
            current.append(character)
            continue
        if character == "'" and current:
            current.append(character)
            continue
        if current:
            token = "".join(current).strip("'")
            if token:
                tokens.append(token)
            current = []
    if current:
        token = "".join(current).strip("'")
        if token:
            tokens.append(token)
    return tuple(tokens)


def ratio_ppm(numerator: int, denominator: int) -> int:
    if numerator < 0 or denominator < 0:
        raise ValueError("ratio inputs must be nonnegative")
    if denominator == 0:
        return 0 if numerator == 0 else PPM
    return min(PPM, (numerator * PPM + denominator // 2) // denominator)


def token_edit_distance(left: Sequence[str], right: Sequence[str]) -> int:
    """Compute Levenshtein distance over token sequences using linear memory."""

    if len(left) > len(right):
        left, right = right, left
    previous = list(range(len(left) + 1))
    for right_index, right_token in enumerate(right, start=1):
        current = [right_index]
        for left_index, left_token in enumerate(left, start=1):
            substitution = previous[left_index - 1] + (left_token != right_token)
            insertion = current[left_index - 1] + 1
            deletion = previous[left_index] + 1
            current.append(min(substitution, insertion, deletion))
        previous = current
    return previous[-1]


def token_set_jaccard_distance_ppm(
    left: Iterable[str], right: Iterable[str]
) -> int:
    left_set = set(left)
    right_set = set(right)
    union = left_set | right_set
    if not union:
        return 0
    difference = len(union) - len(left_set & right_set)
    return ratio_ppm(difference, len(union))


def build_fingerprint_records(
    asv_rows: list[dict[str, Any]], webp_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Build text-private numeric fingerprints for shared text-to-text loci."""

    asv_by_locator = {locator(row): row for row in asv_rows}
    webp_by_locator = {locator(row): row for row in webp_rows}
    if len(asv_by_locator) != len(asv_rows):
        raise ValueError("duplicate ASV locator detected")
    if len(webp_by_locator) != len(webp_rows):
        raise ValueError("duplicate WEBP locator detected")

    records: list[dict[str, Any]] = []
    shared = sorted(set(asv_by_locator) & set(webp_by_locator), key=locator_sort_key)
    for value in shared:
        asv = asv_by_locator[value]
        webp = webp_by_locator[value]
        if asv.get("realization_type") != "text" or webp.get("realization_type") != "text":
            continue
        asv_text = asv.get("source_text")
        webp_text = webp.get("source_text")
        if not isinstance(asv_text, str) or not isinstance(webp_text, str):
            raise ValueError(f"text realization is missing source text at {value}")
        asv_tokens = normalize_tokens(asv_text)
        webp_tokens = normalize_tokens(webp_text)
        if not asv_tokens or not webp_tokens:
            raise ValueError(f"text realization normalized to zero tokens at {value}")

        asv_count = len(asv_tokens)
        webp_count = len(webp_tokens)
        count_delta = webp_count - asv_count
        edit_distance = token_edit_distance(asv_tokens, webp_tokens)
        records.append(
            {
                "fingerprint_version": "1.0.0",
                "fingerprint_id": stable_id("lxf", FINGERPRINT_NAMESPACE, value),
                "locator": value,
                "book_code": asv["book_code"],
                "chapter": asv["chapter"],
                "verse": asv["verse"],
                "asv_token_count": asv_count,
                "webp_token_count": webp_count,
                "token_count_delta": count_delta,
                "token_count_abs_delta": abs(count_delta),
                "token_count_delta_ppm": ratio_ppm(
                    abs(count_delta), max(asv_count, webp_count)
                ),
                "token_edit_distance": edit_distance,
                "token_edit_distance_ppm": ratio_ppm(
                    edit_distance, max(asv_count, webp_count)
                ),
                "token_set_jaccard_distance_ppm": token_set_jaccard_distance_ppm(
                    asv_tokens, webp_tokens
                ),
                "normalized_token_sequence_equal": asv_tokens == webp_tokens,
            }
        )
    return records


def nearest_rank(values: Sequence[int], percentile: int) -> int:
    if not values:
        raise ValueError("percentile requires at least one value")
    if percentile < 1 or percentile > 100:
        raise ValueError("percentile must be between 1 and 100")
    ordered = sorted(values)
    rank = (len(ordered) * percentile + 99) // 100
    return ordered[rank - 1]


def distance_band(value: int) -> str:
    for name, lower, upper in EDIT_DISTANCE_BANDS:
        if lower <= value <= upper:
            return name
    raise ValueError(f"distance outside supported ppm range: {value}")


def _mean(values: Sequence[int]) -> int:
    if not values:
        raise ValueError("mean requires at least one value")
    return (sum(values) + len(values) // 2) // len(values)


def _book_summaries(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["book_code"]].append(record)

    summaries: list[dict[str, Any]] = []
    for book_code in BOOK_ORDER:
        book_records = grouped.get(book_code, [])
        if not book_records:
            continue
        edit_values = [record["token_edit_distance_ppm"] for record in book_records]
        jaccard_values = [
            record["token_set_jaccard_distance_ppm"] for record in book_records
        ]
        summaries.append(
            {
                "book_code": book_code,
                "locator_count": len(book_records),
                "asv_token_count": sum(
                    record["asv_token_count"] for record in book_records
                ),
                "webp_token_count": sum(
                    record["webp_token_count"] for record in book_records
                ),
                "normalized_equal_count": sum(
                    record["normalized_token_sequence_equal"] for record in book_records
                ),
                "mean_token_edit_distance_ppm": _mean(edit_values),
                "median_token_edit_distance_ppm": nearest_rank(edit_values, 50),
                "p90_token_edit_distance_ppm": nearest_rank(edit_values, 90),
                "mean_token_set_jaccard_distance_ppm": _mean(jaccard_values),
                "mean_token_count_abs_delta_ppm": _mean(
                    [record["token_count_delta_ppm"] for record in book_records]
                ),
            }
        )
    return summaries


def summarize_fingerprints(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise ValueError("fingerprint stream must not be empty")
    fingerprint = verify_reproducible_ndjson(records)
    edit_values = [record["token_edit_distance_ppm"] for record in records]
    jaccard_values = [
        record["token_set_jaccard_distance_ppm"] for record in records
    ]
    bands = Counter(distance_band(value) for value in edit_values)
    highest_distance = sorted(
        records,
        key=lambda record: (
            -record["token_edit_distance_ppm"],
            -record["token_set_jaccard_distance_ppm"],
            -record["token_count_abs_delta"],
            locator_sort_key(record["locator"]),
        ),
    )[:25]
    return {
        **fingerprint,
        "fingerprint_namespace": FINGERPRINT_NAMESPACE,
        "normalization_contract": NORMALIZATION_CONTRACT,
        "distance_contract": DISTANCE_CONTRACT,
        "shared_text_locator_count": len(records),
        "asv_total_token_count": sum(record["asv_token_count"] for record in records),
        "webp_total_token_count": sum(
            record["webp_token_count"] for record in records
        ),
        "normalized_equal_locator_count": sum(
            record["normalized_token_sequence_equal"] for record in records
        ),
        "same_token_count_locator_count": sum(
            record["asv_token_count"] == record["webp_token_count"]
            for record in records
        ),
        "mean_token_edit_distance_ppm": _mean(edit_values),
        "median_token_edit_distance_ppm": nearest_rank(edit_values, 50),
        "p90_token_edit_distance_ppm": nearest_rank(edit_values, 90),
        "p95_token_edit_distance_ppm": nearest_rank(edit_values, 95),
        "p99_token_edit_distance_ppm": nearest_rank(edit_values, 99),
        "mean_token_set_jaccard_distance_ppm": _mean(jaccard_values),
        "median_token_set_jaccard_distance_ppm": nearest_rank(jaccard_values, 50),
        "distance_band_counts": [
            {"band": name, "lower_ppm": lower, "upper_ppm": upper, "count": bands[name]}
            for name, lower, upper in EDIT_DISTANCE_BANDS
        ],
        "book_summaries": _book_summaries(records),
        "highest_distance_locators": [
            {
                "locator": record["locator"],
                "asv_token_count": record["asv_token_count"],
                "webp_token_count": record["webp_token_count"],
                "token_count_delta": record["token_count_delta"],
                "token_edit_distance": record["token_edit_distance"],
                "token_edit_distance_ppm": record["token_edit_distance_ppm"],
                "token_set_jaccard_distance_ppm": record[
                    "token_set_jaccard_distance_ppm"
                ],
            }
            for record in highest_distance
        ],
        "source_text_retained": False,
        "token_lists_reported": False,
        "per_locator_text_digests_reported": False,
        "corpus_mutation": "not-performed",
        "mapping_authority": "none",
        "execution_eligible": False,
        "publication_eligible": False,
    }


def assert_expected(observed: dict[str, Any], expected: dict[str, Any]) -> None:
    for key, expected_value in expected.items():
        if key.startswith("_"):
            continue
        actual = observed.get(key)
        if actual != expected_value:
            raise ValueError(
                f"ASV/WEBP lexical fingerprint mismatch for {key}: "
                f"expected {expected_value!r}, observed {actual!r}"
            )


def run(expected_path: Path | None = None) -> dict[str, Any]:
    asv_target = load_json(ASV_TARGET_PATH)
    asv_artifact = load_json(ASV_ARTIFACT_PATH)
    webp_target = load_json(WEBP_TARGET_PATH)
    webp_artifact = load_json(WEBP_ARTIFACT_PATH)

    with tempfile.TemporaryDirectory(prefix="bible-os-asv-webp-lexical-") as temp_dir:
        temp_root = Path(temp_dir)
        asv_archive_path = temp_root / asv_artifact["filename"]
        webp_archive_path = temp_root / webp_artifact["filename"]
        download_verified_archive(asv_target, asv_archive_path)
        download_verified_archive(webp_target, webp_archive_path)
        with zipfile.ZipFile(asv_archive_path) as archive:
            asv_rows = asv_source_rows(archive)
        with zipfile.ZipFile(webp_archive_path) as archive:
            webp_rows = webp_source_rows(archive)

    records = build_fingerprint_records(asv_rows, webp_rows)
    comparison = summarize_fingerprints(records)
    if expected_path is not None:
        assert_expected(comparison, load_json(expected_path))
        comparison["expected_profile"] = str(expected_path)
        comparison["profile_status"] = "matched"
    else:
        comparison["profile_status"] = "observed-unpinned"

    return {
        "status": "passed",
        "experiment": "asv-webp-text-private-lexical-fingerprints-v1",
        "asv_artifact_sha256": asv_artifact["sha256"],
        "webp_artifact_sha256": webp_artifact["sha256"],
        "comparison": comparison,
        "corpus_bytes_committed": False,
        "scripture_text_reported": False,
        "token_lists_reported": False,
        "per_locator_text_digests_reported": False,
        "mapping_authority": "none",
        "execution_eligible": False,
        "publication_eligible": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate text-private ASV/WEBP lexical fingerprints"
    )
    parser.add_argument("--expected", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    report = run(args.expected)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report is not None:
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
