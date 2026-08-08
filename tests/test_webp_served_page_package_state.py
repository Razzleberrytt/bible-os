from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.webp_served_page_package_state import (
    compare_surfaces,
    token_sequence_sha256,
    visible_tokens,
)

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_PATH = ROOT / "registry" / "experiments" / "webp-served-page-package-state-20260808.json"


def test_visible_tokens_excludes_non_visible_script_content() -> None:
    tokens = visible_tokens(
        b"<html><body>Alpha <script>hidden words</script><b>beta</b></body></html>"
    )

    assert tokens == ("alpha", "beta")


def test_token_sequence_hash_is_deterministic_and_order_sensitive() -> None:
    first = token_sequence_sha256(("alpha", "beta"))
    second = token_sequence_sha256(("alpha", "beta"))
    reversed_hash = token_sequence_sha256(("beta", "alpha"))

    assert first == second
    assert first == hashlib.sha256(b"alpha\nbeta").hexdigest()
    assert first != reversed_hash


def test_compare_surfaces_detects_current_sequence_delivery_divergence() -> None:
    current = ("current", "verse", "sequence")
    package_tokens = ("chapter", *current, "tail")
    served_tokens = ("chapter", "older", "verse", "sequence", "tail")
    package = {
        "sha256": "a" * 64,
        "visible_normalized_token_sha256": token_sequence_sha256(package_tokens),
        "visible_normalized_token_count": len(package_tokens),
        "tokens": package_tokens,
    }
    served = {
        "sha256": "b" * 64,
        "visible_normalized_token_sha256": token_sequence_sha256(served_tokens),
        "visible_normalized_token_count": len(served_tokens),
        "tokens": served_tokens,
    }

    result = compare_surfaces(current, package, served)

    assert result["current_sequence_occurrences_in_downloadable_html_member"] == 1
    assert result["current_sequence_occurrences_in_served_page"] == 0
    assert result["downloadable_member_and_served_page_byte_equal"] is False
    assert result["downloadable_member_and_served_page_normalized_visible_sequence_equal"] is False
    assert result["current_sequence_delivery_surface_divergence_detected"] is True


def test_compare_surfaces_reports_agreement_when_current_sequence_is_on_both_surfaces() -> None:
    current = ("current", "sequence")
    tokens = ("chapter", *current, "tail")
    package = {
        "sha256": "a" * 64,
        "visible_normalized_token_sha256": token_sequence_sha256(tokens),
        "visible_normalized_token_count": len(tokens),
        "tokens": tokens,
    }
    served = {
        "sha256": "a" * 64,
        "visible_normalized_token_sha256": token_sequence_sha256(tokens),
        "visible_normalized_token_count": len(tokens),
        "tokens": tokens,
    }

    result = compare_surfaces(current, package, served)

    assert result["current_sequence_occurrences_in_downloadable_html_member"] == 1
    assert result["current_sequence_occurrences_in_served_page"] == 1
    assert result["downloadable_member_and_served_page_byte_equal"] is True
    assert result["downloadable_member_and_served_page_normalized_visible_sequence_equal"] is True
    assert result["current_sequence_delivery_surface_divergence_detected"] is False


def test_registered_live_observation_rejects_current_divergence_claim() -> None:
    experiment = json.loads(EXPERIMENT_PATH.read_text(encoding="utf-8"))

    assert experiment["comparison"]["current_usfm_normalized_token_count"] == 38
    assert experiment["comparison"]["current_sequence_occurrences_in_downloadable_html_member"] == 1
    assert experiment["comparison"]["current_sequence_occurrences_in_served_page"] == 1
    assert experiment["comparison"]["downloadable_member_and_served_page_byte_equal"] is False
    assert experiment["comparison"][
        "downloadable_member_and_served_page_normalized_visible_sequence_equal"
    ] is True
    assert experiment["comparison"]["current_sequence_delivery_surface_divergence_detected"] is False
    assert experiment["interpretation"][
        "current_served_page_and_downloadable_member_agree_under_visible_text_normalization"
    ] is True
    assert experiment["interpretation"]["current_delivery_surface_text_state_divergence_supported"] is False
    assert experiment["interpretation"]["cache_cause_claimed"] is False
    assert experiment["interpretation"]["deployment_cause_claimed"] is False
    assert experiment["interpretation"]["semantic_drift_claimed"] is False
    assert experiment["interpretation"]["meaning_change_claimed"] is False
    assert experiment["scripture_text_reported"] is False
    assert experiment["token_lists_reported"] is False
    assert experiment["corpus_bytes_retained"] is False
    assert experiment["publication_eligible"] is False
