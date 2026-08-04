from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path

from bible_os.governance import (
    audit_evidence_package_documents,
    audit_evidence_packages,
)


ROOT = Path(__file__).resolve().parents[1]
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


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def encode(record: dict) -> bytes:
    return (json.dumps(record, indent=2) + "\n").encode("utf-8")


def audit(package_records: dict[str, dict], requirements_record: dict | None = None):
    requirements = requirements_record or load(REQUIREMENTS_PATH)
    return audit_evidence_package_documents(
        {"requirements.json": encode(requirements)},
        {path: encode(record) for path, record in package_records.items()},
    )


def finding_codes(report) -> set[str]:
    return {finding.code for finding in report.findings}


def revision(
    package_id: str,
    *,
    supersedes: str | None,
    created_at: str,
) -> dict:
    record = deepcopy(load(PACKAGE_PATH))
    record["package_id"] = package_id
    record["supersedes_package_id"] = supersedes
    record["created_at"] = created_at
    return record


def artifact(
    artifact_id: str,
    requirement_ids: list[str],
    *,
    validation_status: str = "unreviewed",
) -> dict:
    return {
        "artifact_id": artifact_id,
        "requirement_ids": requirement_ids,
        "artifact_kind": "comparison-notes",
        "locator": "external://human-evidence/example.json",
        "sha256": "a" * 64,
        "byte_size": 42,
        "media_type": "application/json",
        "supplied_by": {
            "actor_id": "human:test:textual-scholar",
            "actor_type": "human",
            "affiliation": None,
        },
        "supplied_at": "2026-08-04T01:00:00Z",
        "validation": {
            "status": validation_status,
            "validated_by": (
                "human:test:textual-scholar"
                if validation_status == "human-validated"
                else None
            ),
            "validated_at": (
                "2026-08-04T01:05:00Z"
                if validation_status == "human-validated"
                else None
            ),
        },
        "contains_source_text": False,
        "retained_in_repository": False,
        "decision_effect": "none",
    }


def test_registered_evidence_package_audits_cleanly():
    report = audit_evidence_packages(ROOT)

    assert report.clean is True
    assert report.requirements_document_count == 1
    assert report.package_document_count == 1
    assert report.valid_package_count == 1
    assert report.invalid_package_count == 0
    assert report.active_package_count == 1
    assert report.status_counts == (("awaiting-human-evidence", 1),)
    assert report.findings == ()

    entry = report.entries[0]
    assert entry.package_id == "vep_asvwebpromans01"
    assert entry.requirements_id == "ver_asvwebpromans01"
    assert entry.valid is True
    assert entry.active is True
    assert entry.requirement_count == 4
    assert entry.satisfied_requirement_count == 0
    assert entry.human_validated_requirement_count == 0
    assert entry.referenced_artifact_count == 0
    assert entry.review_readiness == "not-ready"


def test_filesystem_audit_is_read_only(tmp_path: Path):
    for source in (REQUIREMENTS_PATH, PACKAGE_PATH):
        relative = source.relative_to(ROOT)
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in sorted(tmp_path.rglob("*.json"))
    }
    assert audit_evidence_packages(tmp_path).clean is True
    after = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in sorted(tmp_path.rglob("*.json"))
    }
    assert after == before


def test_exact_requirements_hash_is_recomputed():
    package = load(PACKAGE_PATH)
    package["requirements_sha256"] = "0" * 64

    report = audit({"package.json": package})
    assert "requirements-hash-mismatch" in finding_codes(report)
    assert report.entries[0].valid is False


def test_scope_and_queue_identity_must_match_requirements():
    package = load(PACKAGE_PATH)
    package["queue_item_id"] = "vrq_differentqueue01"
    package["scope"]["target_references"] = ["ROM 1:1"]

    codes = finding_codes(audit({"package.json": package}))
    assert {"queue-item-mismatch", "scope-mismatch"} <= codes


def test_requirement_states_must_exactly_cover_requirements():
    package = load(PACKAGE_PATH)
    package["requirement_states"].pop()
    package["requirement_states"][0]["requirement_id"] = "req_unknownstate001"

    codes = finding_codes(audit({"package.json": package}))
    assert "missing-requirement-state" in codes
    assert "unknown-requirement-state" in codes


def test_completion_counts_and_readiness_are_derived_not_trusted():
    package = load(PACKAGE_PATH)
    package["completion_summary"]["requirement_count"] = 99
    package["completion_summary"]["referenced_artifact_count"] = 7
    package["status"] = "evidence-ready-for-review"
    package["completion_summary"]["review_readiness"] = (
        "evidence-ready-for-review-only"
    )
    package["completion_summary"]["approval_implied"] = True

    codes = finding_codes(audit({"package.json": package}))
    assert "completion-count-mismatch" in codes
    assert "false-package-status" in codes
    assert "false-review-readiness" in codes
    assert "approval-implied" in codes


def test_artifact_links_must_be_bidirectional_and_known():
    package = load(PACKAGE_PATH)
    package["requirement_states"][0]["state"] = "partial"
    package["requirement_states"][0]["artifact_ids"] = ["epa_exampleartifact01"]
    package["artifacts"] = [
        artifact("epa_exampleartifact01", ["req_numberingprov01"])
    ]
    package["status"] = "collecting-human-evidence"
    package["completion_summary"]["referenced_artifact_count"] = 1

    codes = finding_codes(audit({"package.json": package}))
    assert "asymmetric-artifact-link" in codes
    assert "asymmetric-requirement-link" in codes


def test_human_validated_state_requires_human_validated_artifacts():
    package = load(PACKAGE_PATH)
    requirement_id = package["requirement_states"][0]["requirement_id"]
    package["requirement_states"][0]["state"] = "human-validated"
    package["requirement_states"][0]["artifact_ids"] = ["epa_exampleartifact01"]
    package["artifacts"] = [artifact("epa_exampleartifact01", [requirement_id])]
    package["status"] = "collecting-human-evidence"
    package["completion_summary"]["satisfied_requirement_count"] = 1
    package["completion_summary"]["human_validated_requirement_count"] = 1
    package["completion_summary"]["referenced_artifact_count"] = 1

    codes = finding_codes(audit({"package.json": package}))
    assert "unvalidated-artifact-for-human-state" in codes


def test_linear_supersession_selects_one_active_revision():
    first = revision(
        "vep_asvwebpromans01",
        supersedes=None,
        created_at="2026-08-04T00:36:00Z",
    )
    second = revision(
        "vep_asvwebpromans02",
        supersedes="vep_asvwebpromans01",
        created_at="2026-08-04T01:36:00Z",
    )

    report = audit({"first.json": first, "second.json": second})
    assert report.clean is True
    assert report.valid_package_count == 2
    assert report.active_package_count == 1
    entries = {entry.package_id: entry for entry in report.entries}
    assert entries["vep_asvwebpromans01"].active is False
    assert entries["vep_asvwebpromans02"].active is True


def test_unknown_predecessor_and_nonmonotonic_time_are_reported():
    missing = revision(
        "vep_asvwebpromans02",
        supersedes="vep_missingpackage01",
        created_at="2026-08-04T01:36:00Z",
    )
    report = audit({"missing.json": missing})
    assert "unknown-superseded-package" in finding_codes(report)

    first = revision(
        "vep_asvwebpromans01",
        supersedes=None,
        created_at="2026-08-04T02:36:00Z",
    )
    second = revision(
        "vep_asvwebpromans02",
        supersedes="vep_asvwebpromans01",
        created_at="2026-08-04T01:36:00Z",
    )
    assert "nonmonotonic-supersession-time" in finding_codes(
        audit({"first.json": first, "second.json": second})
    )


def test_branched_cycles_and_multiple_roots_are_rejected():
    root = revision(
        "vep_asvwebpromans01",
        supersedes=None,
        created_at="2026-08-04T00:36:00Z",
    )
    left = revision(
        "vep_asvwebpromans02",
        supersedes="vep_asvwebpromans01",
        created_at="2026-08-04T01:36:00Z",
    )
    right = revision(
        "vep_asvwebpromans03",
        supersedes="vep_asvwebpromans01",
        created_at="2026-08-04T02:36:00Z",
    )
    assert "branched-supersession" in finding_codes(
        audit({"root.json": root, "left.json": left, "right.json": right})
    )

    root["supersedes_package_id"] = "vep_asvwebpromans02"
    assert "supersession-cycle" in finding_codes(
        audit({"root.json": root, "left.json": left})
    )

    other_root = revision(
        "vep_asvwebpromans04",
        supersedes=None,
        created_at="2026-08-04T03:36:00Z",
    )
    root["supersedes_package_id"] = None
    assert "multiple-package-roots" in finding_codes(
        audit({"root.json": root, "other.json": other_root})
    )


def test_malformed_and_duplicate_package_documents_produce_structured_entries():
    duplicate = load(PACKAGE_PATH)
    report = audit_evidence_package_documents(
        {"requirements.json": REQUIREMENTS_PATH.read_bytes()},
        {
            "broken.json": b"{broken",
            "duplicate-a.json": encode(duplicate),
            "duplicate-b.json": encode(duplicate),
        },
    )
    codes = finding_codes(report)
    assert "invalid-package-document" in codes
    assert "duplicate-package-id" in codes
    assert report.invalid_package_count == 3


def test_document_mapping_order_does_not_change_the_report():
    requirements = {"z-requirements.json": REQUIREMENTS_PATH.read_bytes()}
    package = PACKAGE_PATH.read_bytes()
    first = audit_evidence_package_documents(
        requirements,
        {"z-package.json": package},
    )
    second = audit_evidence_package_documents(
        dict(reversed(list(requirements.items()))),
        {"z-package.json": package},
    )
    assert first == second
