from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "registry" / "experiments" / "webp-wj-semantics-provenance.json"
SOURCE = ROOT / "registry" / "sources" / "engwebp.source.json"
ARTIFACT = ROOT / "registry" / "artifacts" / "engwebp-usfm.artifact.json"
SHAPE = ROOT / "registry" / "experiments" / "asv-webp-wj-record-shape.json"
STRATA = ROOT / "registry" / "experiments" / "asv-webp-wj-token-strata.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_standard_semantics_are_explicit_and_separate_from_source_inference() -> None:
    study = load(STUDY)
    standard = study["standard_semantics"]
    interpretation = study["interpretation"]

    assert study["marker"] == "wj"
    assert standard == {
        "standard": "USFM-USX-USJ",
        "version": "3.1.2",
        "documentation_url": "https://docs.usfm.bible/usfm/3.1.2/char/features/wj.html",
        "description": "Words of Jesus",
        "style_type": "Character",
        "added_in": "1.0",
        "semantic_status": "normative-standard-definition",
    }
    assert interpretation["normative_definition_confidence"] == "high"
    assert interpretation["source_specific_intent_confidence"] == "moderate"
    assert study["verified_source"]["source_specific_wj_policy_url"] is None
    assert study["verified_source"]["source_specific_override_observed"] is False


def test_verified_source_and_artifact_anchors_match_registry() -> None:
    study = load(STUDY)["verified_source"]
    source = load(SOURCE)
    artifact = load(ARTIFACT)

    assert study["source_id"] == source["source_id"] == artifact["source_id"]
    assert study["artifact_id"] == artifact["artifact_id"]
    assert study["artifact_sha256"] == artifact["sha256"]
    assert study["source_name"] == source["name"]
    assert study["license_status"] == source["license_status"] == "public-domain"
    assert study["verification_status"] == artifact["verification_status"] == "verified"
    assert study["upstream_version"] == artifact["upstream_version"]
    assert study["official_usfm_url"] in source["official_urls"]


def test_reproduced_usage_anchors_match_prior_experiments() -> None:
    anchors = load(STUDY)["reproduced_usage_anchors"]
    shape = load(SHAPE)
    strata = load(STRATA)
    webp_shape = shape["webp"]["corpus"]
    strata_by_name = {row["stratum"]: row for row in strata["strata"]}

    assert anchors["record_shape_profile_contract"] == shape["profile_contract"]
    assert anchors["record_shape_comparison_sha256"] == shape["comparison_sha256"]
    assert anchors["webp_opening_wj_record_count"] == webp_shape["records_with_opening_wj"] == 1430
    assert anchors["webp_opening_wj_visible_token_count"] == webp_shape["opening_wj_visible_token_count"] == 89366
    assert anchors["webp_subsequent_wj_line_count"] == webp_shape["subsequent_wj_line_count"] == 0
    assert anchors["webp_token_reconciliation_delta"] == webp_shape["token_reconciliation_delta"] == 0
    assert anchors["token_strata_profile_contract"] == strata["profile_contract"]
    assert anchors["token_strata_numeric_stream_sha256"] == strata["numeric_stream"]["sha256"]
    assert anchors["shared_text_text_opening_wj_locator_count"] == strata_by_name["webp-opening-wj"]["locator_count"] == 1423
    assert anchors["shared_text_text_non_wj_locator_count"] == strata_by_name["webp-non-wj"]["locator_count"] == 29660
    assert anchors["opening_wj_token_delta"] == strata_by_name["webp-opening-wj"]["token_count_delta"] == 58530


def test_study_preserves_text_and_authority_boundaries() -> None:
    study = load(STUDY)
    interpretation = study["interpretation"]

    assert interpretation["content_treatment"] == "retain-as-verse-text"
    assert interpretation["marker_treatment"] == "preserve-as-semantic-metadata"
    assert interpretation["parser_removal_authorized"] is False
    assert interpretation["text_removal_authorized"] is False
    assert interpretation["semantic_drift_claimed"] is False
    assert interpretation["mistranslation_claimed"] is False
    assert study["scripture_text_reported"] is False
    assert study["token_lists_reported"] is False
    assert study["locator_identifiers_reported"] is False
    assert study["per_locator_text_digests_reported"] is False
    assert study["text_boundaries_defined"] is False
    assert study["parser_behavior_changed"] is False
    assert study["corpus_mutation"] == "not-performed"
    assert study["mapping_authority"] == "none"
    assert study["execution_eligible"] is False
    assert study["publication_eligible"] is False


def test_record_contains_no_scripture_payload_fields() -> None:
    rendered = STUDY.read_text(encoding="utf-8").casefold()
    forbidden_keys = ('"verse_text"', '"scripture_text"', '"tokens"', '"locator"', '"raw_payload"')
    assert all(key not in rendered for key in forbidden_keys)
