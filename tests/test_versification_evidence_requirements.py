from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/versification-evidence-requirements.schema.json"
REQUIREMENTS_PATH = (
    ROOT
    / "registry/versification/evidence-requirements"
    / "asv-webp-romans-human-review.json"
)
QUEUE_PATH = (
    ROOT
    / "registry/versification/review-queue"
    / "asv-webp-romans-structural-candidate.json"
)
ATTESTATION_PATH = (
    ROOT
    / "registry/versification/review-attestations"
    / "asv-webp-romans-textual-needs-evidence.json"
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def errors(record: dict) -> list:
    return list(
        Draft202012Validator(
            load(SCHEMA_PATH),
            format_checker=FormatChecker(),
        ).iter_errors(record)
    )


def test_evidence_requirements_schema_and_record_validate():
    schema = load(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    assert errors(load(REQUIREMENTS_PATH)) == []


def test_record_is_anchored_to_exact_queue_and_attestation_bytes():
    record = load(REQUIREMENTS_PATH)
    queue = load(QUEUE_PATH)
    attestation = load(ATTESTATION_PATH)

    assert record["queue_item_id"] == queue["queue_item_id"]
    assert record["queue_item_sha256"] == hashlib.sha256(
        QUEUE_PATH.read_bytes()
    ).hexdigest()
    assert record["trigger_attestation_id"] == attestation["attestation_id"]
    assert record["trigger_attestation_sha256"] == hashlib.sha256(
        ATTESTATION_PATH.read_bytes()
    ).hexdigest()
    assert attestation["recommendation"] == "needs-evidence"


def test_scope_matches_the_queued_romans_proposal_exactly():
    record = load(REQUIREMENTS_PATH)
    queue = load(QUEUE_PATH)

    assert record["scope"]["source_references"] == queue["source_system"][
        "references"
    ]
    assert record["scope"]["target_references"] == queue["target_system"][
        "references"
    ]
    assert record["scope"]["excluded_candidate_ids"] == [
        "can_k6cfuv7sbumommdi2ha7"
    ]


def test_all_four_evidence_classes_are_required():
    record = load(REQUIREMENTS_PATH)
    categories = {item["category"] for item in record["requirements"]}

    assert categories == {
        "source-anchored-textual-comparison",
        "numbering-tradition-provenance",
        "independent-scholarly-analysis",
        "alternative-hypothesis-assessment",
    }
    assert len(record["requirements"]) == 4


def test_requirements_demand_human_validation_without_embedding_unit_wording():
    record = load(REQUIREMENTS_PATH)

    assert record["source_text_embedded"] is False
    for requirement in record["requirements"]:
        assert requirement["contains_source_text"] is False
        assert requirement["human_validation_required"] is True
        assert requirement["required_artifacts"]
        assert requirement["acceptance_criteria"]
        assert "source_text" not in requirement

    scholarship = next(
        item
        for item in record["requirements"]
        if item["category"] == "independent-scholarly-analysis"
    )
    assert any("two independently authored" in criterion for criterion in scholarship["acceptance_criteria"])


def test_alternative_hypotheses_remain_open_and_separate():
    record = load(REQUIREMENTS_PATH)
    hypothesis = next(
        item
        for item in record["requirements"]
        if item["category"] == "alternative-hypothesis-assessment"
    )
    criteria = " ".join(hypothesis["acceptance_criteria"])

    for term in [
        "Relocation",
        "duplication",
        "omission",
        "numbering-only",
        "mixed",
    ]:
        assert term in criteria
    assert "No hypothesis is accepted" in criteria


def test_completion_only_returns_evidence_to_human_review():
    record = load(REQUIREMENTS_PATH)
    policy = record["completion_policy"]

    assert policy == {
        "all_requirements_required": True,
        "required_reviewer_role": "textual-scholar",
        "independent_human_reviewer_required": True,
        "completion_effect": "evidence-ready-for-review-only",
        "approval_implied": False,
    }
    assert record["status"] == "open"
    assert record["record_policy"] == "append-only"
    assert record["decision_authority"] == "none"
    assert record["queue_status_authority"] == "none"
    assert record["materialization_authority"] == "none"
    assert record["execution_eligible"] is False
    assert record["publication_eligible"] is False


def test_requirements_cannot_be_mutated_into_authority_or_completion():
    original = load(REQUIREMENTS_PATH)
    mutations = [
        (lambda item: item.__setitem__("source_text_embedded", True)),
        (lambda item: item.__setitem__("status", "completed")),
        (lambda item: item.__setitem__("decision_authority", "approve")),
        (lambda item: item.__setitem__("queue_status_authority", "transition")),
        (lambda item: item.__setitem__("materialization_authority", "allowed")),
        (lambda item: item.__setitem__("execution_eligible", True)),
        (lambda item: item.__setitem__("publication_eligible", True)),
        (
            lambda item: item["completion_policy"].__setitem__(
                "approval_implied", True
            )
        ),
        (
            lambda item: item["completion_policy"].__setitem__(
                "completion_effect", "mapping-approved"
            )
        ),
        (
            lambda item: item["requirements"][0].__setitem__(
                "contains_source_text", True
            )
        ),
        (
            lambda item: item["requirements"][0].__setitem__(
                "human_validation_required", False
            )
        ),
    ]

    for mutate in mutations:
        changed = deepcopy(original)
        mutate(changed)
        assert errors(changed)


def test_source_wording_and_empty_requirements_are_rejected():
    record = deepcopy(load(REQUIREMENTS_PATH))
    record["requirements"][0]["source_text"] = "not allowed"
    assert errors(record)

    record = deepcopy(load(REQUIREMENTS_PATH))
    record["requirements"] = []
    assert errors(record)


def test_underlying_queue_and_attestation_remain_inert():
    queue = load(QUEUE_PATH)
    attestation = load(ATTESTATION_PATH)

    assert queue["status"] == "queued"
    assert "decision" not in queue
    assert queue["materialization_state"] == "not-materialized"
    assert queue["execution_eligible"] is False
    assert queue["publication_eligible"] is False

    assert attestation["recommendation"] == "needs-evidence"
    assert attestation["materialization_authority"] == "none"
    assert attestation["execution_eligible"] is False
    assert attestation["publication_eligible"] is False
