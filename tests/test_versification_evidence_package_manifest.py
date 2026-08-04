from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/versification-evidence-package-manifest.schema.json"
REQUIREMENTS_PATH = (
    ROOT
    / "registry/versification/evidence-requirements"
    / "asv-webp-romans-human-review.json"
)
PACKAGE_PATH = (
    ROOT
    / "registry/versification/evidence-packages"
    / "asv-webp-romans-awaiting-human-evidence.json"
)
QUEUE_PATH = (
    ROOT
    / "registry/versification/review-queue"
    / "asv-webp-romans-structural-candidate.json"
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


def referenced_artifact(
    *,
    artifact_id: str = "epa_romansdigest001",
    requirement_id: str = "req_sourcetext001",
    artifact_kind: str = "source-unit-digests",
    digest_character: str = "1",
) -> dict:
    return {
        "artifact_id": artifact_id,
        "requirement_ids": [requirement_id],
        "artifact_kind": artifact_kind,
        "locator": "urn:sha256:" + (digest_character * 64),
        "sha256": digest_character * 64,
        "byte_size": 512,
        "media_type": "application/json",
        "supplied_by": {
            "actor_id": "human-reviewer-001",
            "actor_type": "human",
            "affiliation": None,
        },
        "supplied_at": "2026-08-04T00:40:00Z",
        "validation": {
            "status": "unreviewed",
            "validated_by": None,
            "validated_at": None,
        },
        "contains_source_text": False,
        "retained_in_repository": False,
        "decision_effect": "none",
    }


def test_evidence_package_schema_and_empty_manifest_validate():
    schema = load(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    assert errors(load(PACKAGE_PATH)) == []


def test_manifest_is_anchored_to_exact_requirements_bytes():
    package = load(PACKAGE_PATH)
    requirements = load(REQUIREMENTS_PATH)

    assert package["requirements_id"] == requirements["requirements_id"]
    assert package["queue_item_id"] == requirements["queue_item_id"]
    assert package["requirements_sha256"] == hashlib.sha256(
        REQUIREMENTS_PATH.read_bytes()
    ).hexdigest()


def test_manifest_scope_and_requirement_ids_match_the_requirements_record():
    package = load(PACKAGE_PATH)
    requirements = load(REQUIREMENTS_PATH)

    assert package["scope"] == requirements["scope"]
    assert [state["requirement_id"] for state in package["requirement_states"]] == [
        requirement["requirement_id"]
        for requirement in requirements["requirements"]
    ]


def test_initial_manifest_is_truthfully_empty_and_not_ready():
    package = load(PACKAGE_PATH)

    assert package["status"] == "awaiting-human-evidence"
    assert package["artifacts"] == []
    assert all(
        state["state"] == "missing" and state["artifact_ids"] == []
        for state in package["requirement_states"]
    )
    assert package["completion_summary"] == {
        "requirement_count": 4,
        "satisfied_requirement_count": 0,
        "human_validated_requirement_count": 0,
        "referenced_artifact_count": 0,
        "review_readiness": "not-ready",
        "approval_implied": False,
    }


def test_future_human_supplied_digest_reference_can_validate_without_source_text():
    package = deepcopy(load(PACKAGE_PATH))
    artifact = referenced_artifact()

    package["package_id"] = "vep_asvwebpromans02"
    package["status"] = "collecting-human-evidence"
    package["supersedes_package_id"] = "vep_asvwebpromans01"
    package["requirement_states"][0]["state"] = "partial"
    package["requirement_states"][0]["artifact_ids"] = [artifact["artifact_id"]]
    package["artifacts"] = [artifact]
    package["completion_summary"]["referenced_artifact_count"] = 1

    assert errors(package) == []
    assert artifact["contains_source_text"] is False
    assert artifact["retained_in_repository"] is False
    assert artifact["decision_effect"] == "none"


def test_artifact_reference_requires_a_human_supplier_and_digest():
    package = deepcopy(load(PACKAGE_PATH))
    artifact = referenced_artifact()
    package["status"] = "collecting-human-evidence"
    package["requirement_states"][0]["state"] = "partial"
    package["requirement_states"][0]["artifact_ids"] = [artifact["artifact_id"]]
    package["artifacts"] = [artifact]
    package["completion_summary"]["referenced_artifact_count"] = 1

    package["artifacts"][0]["supplied_by"]["actor_type"] = "automated"
    assert errors(package)

    package = deepcopy(load(PACKAGE_PATH))
    artifact = referenced_artifact()
    artifact["sha256"] = "not-a-digest"
    package["status"] = "collecting-human-evidence"
    package["requirement_states"][0]["state"] = "partial"
    package["requirement_states"][0]["artifact_ids"] = [artifact["artifact_id"]]
    package["artifacts"] = [artifact]
    package["completion_summary"]["referenced_artifact_count"] = 1
    assert errors(package)


def test_manifest_rejects_embedded_source_units_or_artifact_content():
    package = deepcopy(load(PACKAGE_PATH))
    package["source_text"] = "not allowed"
    assert errors(package)

    package = deepcopy(load(PACKAGE_PATH))
    artifact = referenced_artifact()
    artifact["content"] = "not allowed"
    package["status"] = "collecting-human-evidence"
    package["requirement_states"][0]["state"] = "partial"
    package["requirement_states"][0]["artifact_ids"] = [artifact["artifact_id"]]
    package["artifacts"] = [artifact]
    package["completion_summary"]["referenced_artifact_count"] = 1
    assert errors(package)

    package = deepcopy(load(PACKAGE_PATH))
    artifact = referenced_artifact()
    artifact["contains_source_text"] = True
    package["status"] = "collecting-human-evidence"
    package["requirement_states"][0]["state"] = "partial"
    package["requirement_states"][0]["artifact_ids"] = [artifact["artifact_id"]]
    package["artifacts"] = [artifact]
    package["completion_summary"]["referenced_artifact_count"] = 1
    assert errors(package)


def test_review_ready_status_requires_every_requirement_to_be_human_validated():
    package = deepcopy(load(PACKAGE_PATH))
    package["status"] = "evidence-ready-for-review"
    package["completion_summary"]["review_readiness"] = (
        "evidence-ready-for-review-only"
    )
    assert errors(package)

    artifact_kinds = [
        "source-unit-digests",
        "provenance-citations",
        "scholarly-citations",
        "hypothesis-matrix",
    ]
    artifacts = []
    for index, (state, artifact_kind) in enumerate(
        zip(package["requirement_states"], artifact_kinds, strict=True),
        start=1,
    ):
        artifact = referenced_artifact(
            artifact_id=f"epa_validatedartifact{index:02d}",
            requirement_id=state["requirement_id"],
            artifact_kind=artifact_kind,
            digest_character=str(index),
        )
        artifact["validation"] = {
            "status": "human-validated",
            "validated_by": f"human-validator-{index:02d}",
            "validated_at": "2026-08-04T00:45:00Z",
        }
        state["state"] = "human-validated"
        state["artifact_ids"] = [artifact["artifact_id"]]
        artifacts.append(artifact)

    package["artifacts"] = artifacts
    package["completion_summary"] = {
        "requirement_count": 4,
        "satisfied_requirement_count": 4,
        "human_validated_requirement_count": 4,
        "referenced_artifact_count": 4,
        "review_readiness": "evidence-ready-for-review-only",
        "approval_implied": False,
    }
    assert errors(package) == []


def test_manifest_cannot_claim_decision_queue_or_execution_authority():
    original = load(PACKAGE_PATH)
    for field, unsafe_value in [
        ("record_policy", "mutable"),
        ("package_semantics", "embedded-evidence"),
        ("decision_authority", "approve"),
        ("queue_status_authority", "transition"),
        ("materialization_authority", "mapping"),
        ("execution_eligible", True),
        ("publication_eligible", True),
        ("source_text_embedded", True),
    ]:
        mutated = deepcopy(original)
        mutated[field] = unsafe_value
        assert errors(mutated)


def test_manifest_does_not_change_the_underlying_queue():
    queue = load(QUEUE_PATH)
    package = load(PACKAGE_PATH)

    assert queue["queue_item_id"] == package["queue_item_id"]
    assert queue["status"] == "queued"
    assert "decision" not in queue
    assert queue["materialization_state"] == "not-materialized"
    assert queue["execution_eligible"] is False
    assert queue["publication_eligible"] is False
