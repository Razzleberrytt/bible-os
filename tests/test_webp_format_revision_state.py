from __future__ import annotations

from scripts.webp_format_revision_state import parse_last_modified, summarize_revision_state


def observation(format_name: str, last_modified: str) -> dict:
    return {
        "format": format_name,
        "http": {"last_modified": last_modified},
    }


def test_parse_last_modified_normalizes_to_utc() -> None:
    parsed = parse_last_modified("Thu, 06 Aug 2026 00:01:09 GMT")

    assert parsed is not None
    assert parsed.isoformat() == "2026-08-06T00:01:09+00:00"


def test_summary_detects_delivery_artifact_modification_skew() -> None:
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
    assert summary["delivery_artifact_modification_skew_detected"] is True
    assert summary["oldest_last_modified_format"] == "html"
    assert summary["latest_last_modified_format"] == "usfm"
    assert summary["max_observed_modification_lag_seconds"] > 0


def test_summary_does_not_infer_skew_when_dates_match() -> None:
    observations = [
        observation("html", "Thu, 06 Aug 2026 00:01:09 GMT"),
        observation("usfm", "Thu, 06 Aug 2026 00:02:09 GMT"),
    ]

    summary = summarize_revision_state(observations)

    assert summary["last_modified_date_group_count"] == 1
    assert summary["delivery_artifact_modification_skew_detected"] is False


def test_summary_tracks_missing_last_modified_without_fabricating_dates() -> None:
    summary = summarize_revision_state(
        [
            observation("html", ""),
            observation("usfm", "Thu, 06 Aug 2026 00:01:09 GMT"),
        ]
    )

    assert summary["missing_last_modified_formats"] == ["html"]
    assert summary["last_modified_date_groups"] == {"2026-08-06": ["usfm"]}
