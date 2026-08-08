from __future__ import annotations

import json
from pathlib import Path

from scripts.webp_format_revision_state import parse_last_modified, summarize_revision_state

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_PATH = ROOT / "registry" / "experiments" / "webp-format-revision-state-20260808.json"


def observation(format_name: str, last_modified: str) -> dict:
    return {
        "format": format_name,
        "http": {"last_modified": last_modified},
    }


def test_parse_last_modified_normalizes_to_utc() -> None:
    parsed = parse_last_modified("Thu, 06 Aug 2026 00:01:09 GMT")

    assert parsed is not None
    assert parsed.isoformat() == "2026-08-06T00:01:09+00:00"


def test_summary_detects_calendar_date_and_timestamp_skew() -> None:
    observations = [
        observation("html", "Tue, 28 Jul 2026 03:14:57 GMT"),
        observation("usfm", "Thu, 06 Aug 2026 00:01:09 GMT"),
        observation("vpl", "Tue, 28 Jul 2026 03:14:57 GMT"),
    ]

    summary = summarize_revision_state(observations)

    assert summary["artifact_count"] == 3
    assert summary["last_modified_date_group_count"] == 2
    assert summary["last_modified_date_groups"] == {
        "2026-07-28": ["html", "vpl"],
        "2026-08-06": ["usfm"],
    }
    assert summary["calendar_date_skew_detected"] is True
    assert summary["modification_timestamp_skew_detected"] is True
    assert summary["oldest_last_modified_format"] == "html"
    assert summary["latest_last_modified_format"] == "usfm"
    assert summary["max_observed_modification_lag_seconds"] > 0


def test_summary_separates_same_date_build_stagger_from_date_skew() -> None:
    observations = [
        observation("html", "Thu, 06 Aug 2026 00:01:09 GMT"),
        observation("usfm", "Thu, 06 Aug 2026 00:02:09 GMT"),
    ]

    summary = summarize_revision_state(observations)

    assert summary["last_modified_date_group_count"] == 1
    assert summary["calendar_date_skew_detected"] is False
    assert summary["modification_timestamp_skew_detected"] is True
    assert summary["max_observed_modification_lag_seconds"] == 60


def test_summary_reports_no_timestamp_skew_for_identical_times() -> None:
    observations = [
        observation("html", "Thu, 06 Aug 2026 00:01:09 GMT"),
        observation("usfm", "Thu, 06 Aug 2026 00:01:09 GMT"),
    ]

    summary = summarize_revision_state(observations)

    assert summary["calendar_date_skew_detected"] is False
    assert summary["modification_timestamp_skew_detected"] is False
    assert summary["max_observed_modification_lag_seconds"] == 0


def test_summary_tracks_missing_last_modified_without_fabricating_dates() -> None:
    summary = summarize_revision_state(
        [
            observation("html", ""),
            observation("usfm", "Thu, 06 Aug 2026 00:01:09 GMT"),
        ]
    )

    assert summary["missing_last_modified_formats"] == ["html"]
    assert summary["last_modified_date_groups"] == {"2026-08-06": ["usfm"]}


def test_registered_format_state_preserves_interpretation_boundaries() -> None:
    experiment = json.loads(EXPERIMENT_PATH.read_text(encoding="utf-8"))

    assert experiment["revision_state_summary"]["artifact_count"] == 7
    assert experiment["revision_state_summary"]["calendar_date_skew_detected"] is False
    assert experiment["revision_state_summary"]["modification_timestamp_skew_detected"] is True
    assert experiment["revision_state_summary"]["max_observed_modification_lag_seconds"] == 3166
    assert experiment["interpretation"]["best_supported_model"] == "same-day staggered build-or-publish batch"
    assert experiment["interpretation"]["independent_textual_revision_claimed"] is False
    assert experiment["interpretation"]["textual_equivalence_claimed"] is False
    assert experiment["interpretation"]["semantic_equivalence_claimed"] is False
    assert experiment["scripture_text_reported"] is False
    assert experiment["corpus_bytes_retained"] is False
    assert experiment["publication_eligible"] is False
