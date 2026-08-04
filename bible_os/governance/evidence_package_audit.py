"""Deterministic, read-only consistency checks for evidence-package manifests."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class EvidencePackageFinding:
    """One deterministic evidence-package integrity finding."""

    code: str
    document_path: str
    requirements_id: str | None
    package_id: str | None
    message: str
    severity: str = "error"


@dataclass(frozen=True, slots=True)
class EvidencePackageEntry:
    """Read-only summary of one evidence-package manifest."""

    document_path: str
    requirements_id: str | None
    package_id: str | None
    valid: bool
    active: bool
    status: str | None
    requirement_count: int
    satisfied_requirement_count: int
    human_validated_requirement_count: int
    referenced_artifact_count: int
    review_readiness: str | None
    supersedes_package_id: str | None
    error_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidencePackageAuditReport:
    """Frozen report for a complete evidence-package consistency audit."""

    requirements_document_count: int
    package_document_count: int
    valid_package_count: int
    invalid_package_count: int
    active_package_count: int
    status_counts: tuple[tuple[str, int], ...]
    entries: tuple[EvidencePackageEntry, ...]
    findings: tuple[EvidencePackageFinding, ...]
    clean: bool


@dataclass(frozen=True, slots=True)
class _Document:
    path: str
    raw: bytes
    record: dict[str, Any]


def _decode(path: str, raw: bytes, kind: str) -> _Document:
    if not isinstance(raw, bytes):
        raise ValueError(f"{kind} document must be immutable bytes")
    try:
        record = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{kind} document is not valid UTF-8 JSON") from exc
    if not isinstance(record, dict):
        raise ValueError(f"{kind} document must decode to an object")
    return _Document(path=path, raw=raw, record=record)


def _required_text(record: Mapping[str, Any], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _finding(
    code: str,
    document: _Document | None,
    message: str,
    *,
    path: str | None = None,
) -> EvidencePackageFinding:
    record = document.record if document is not None else {}
    return EvidencePackageFinding(
        code=code,
        document_path=path or (document.path if document is not None else ""),
        requirements_id=record.get("requirements_id"),
        package_id=record.get("package_id"),
        message=message,
    )


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        result = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return result if result.tzinfo is not None else None


def _requirement_ids(
    requirements: _Document,
    findings: list[EvidencePackageFinding],
) -> tuple[str, ...]:
    items = requirements.record.get("requirements")
    if not isinstance(items, list):
        findings.append(
            _finding(
                "invalid-requirements-list",
                requirements,
                "requirements must be an array",
            )
        )
        return ()
    result: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("requirement_id"), str):
            findings.append(
                _finding(
                    "invalid-requirement",
                    requirements,
                    f"requirements[{index}] has no valid requirement_id",
                )
            )
            continue
        result.append(item["requirement_id"])
    if len(result) != len(set(result)):
        findings.append(
            _finding(
                "duplicate-requirement-id",
                requirements,
                "requirements contain duplicate identifiers",
            )
        )
    return tuple(result)


def _audit_manifest(
    package: _Document,
    requirements: _Document,
) -> tuple[dict[str, Any], list[EvidencePackageFinding]]:
    findings: list[EvidencePackageFinding] = []
    record = package.record
    required_ids = _requirement_ids(requirements, findings)
    required_set = set(required_ids)

    exact_digest = hashlib.sha256(requirements.raw).hexdigest()
    if record.get("requirements_sha256") != exact_digest:
        findings.append(
            _finding(
                "requirements-hash-mismatch",
                package,
                "requirements_sha256 does not match the exact requirements bytes",
            )
        )
    if record.get("queue_item_id") != requirements.record.get("queue_item_id"):
        findings.append(
            _finding("queue-item-mismatch", package, "queue_item_id does not match")
        )
    if record.get("scope") != requirements.record.get("scope"):
        findings.append(_finding("scope-mismatch", package, "scope does not match"))

    raw_states = record.get("requirement_states")
    if not isinstance(raw_states, list):
        findings.append(
            _finding(
                "invalid-requirement-states",
                package,
                "requirement_states must be an array",
            )
        )
        raw_states = []
    states: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(raw_states):
        if not isinstance(item, dict) or not isinstance(item.get("requirement_id"), str):
            findings.append(
                _finding(
                    "invalid-requirement-state",
                    package,
                    f"requirement_states[{index}] is invalid",
                )
            )
            continue
        requirement_id = item["requirement_id"]
        if requirement_id in states:
            findings.append(
                _finding(
                    "duplicate-requirement-state",
                    package,
                    f"duplicate state for {requirement_id}",
                )
            )
            continue
        states[requirement_id] = item

    for requirement_id in sorted(required_set - set(states)):
        findings.append(
            _finding(
                "missing-requirement-state",
                package,
                f"missing state for {requirement_id}",
            )
        )
    for requirement_id in sorted(set(states) - required_set):
        findings.append(
            _finding(
                "unknown-requirement-state",
                package,
                f"unknown requirement state {requirement_id}",
            )
        )

    raw_artifacts = record.get("artifacts")
    if not isinstance(raw_artifacts, list):
        findings.append(_finding("invalid-artifacts", package, "artifacts must be an array"))
        raw_artifacts = []
    artifacts: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(raw_artifacts):
        if not isinstance(item, dict) or not isinstance(item.get("artifact_id"), str):
            findings.append(
                _finding("invalid-artifact", package, f"artifacts[{index}] is invalid")
            )
            continue
        artifact_id = item["artifact_id"]
        if artifact_id in artifacts:
            findings.append(
                _finding("duplicate-artifact-id", package, f"duplicate {artifact_id}")
            )
            continue
        artifacts[artifact_id] = item

    satisfied = 0
    human_validated = 0
    for requirement_id in sorted(required_set & set(states)):
        state_record = states[requirement_id]
        state = state_record.get("state")
        artifact_ids = state_record.get("artifact_ids")
        if not isinstance(artifact_ids, list):
            findings.append(
                _finding(
                    "invalid-state-artifacts",
                    package,
                    f"{requirement_id}.artifact_ids must be an array",
                )
            )
            artifact_ids = []
        if len(artifact_ids) != len(set(artifact_ids)):
            findings.append(
                _finding(
                    "duplicate-state-artifact",
                    package,
                    f"{requirement_id} repeats artifact IDs",
                )
            )
        if state == "missing" and artifact_ids:
            findings.append(
                _finding(
                    "missing-state-has-artifacts",
                    package,
                    f"{requirement_id} is missing but links artifacts",
                )
            )
        if state != "missing" and not artifact_ids:
            findings.append(
                _finding(
                    "nonmissing-state-without-artifacts",
                    package,
                    f"{requirement_id} has no artifacts",
                )
            )
        if state in {"satisfied-pending-human-validation", "human-validated"}:
            satisfied += 1
        if state == "human-validated":
            human_validated += 1

        for artifact_id in artifact_ids:
            artifact = artifacts.get(artifact_id)
            if artifact is None:
                findings.append(
                    _finding(
                        "unknown-state-artifact",
                        package,
                        f"{requirement_id} references unknown {artifact_id}",
                    )
                )
                continue
            if requirement_id not in artifact.get("requirement_ids", []):
                findings.append(
                    _finding(
                        "asymmetric-artifact-link",
                        package,
                        f"{artifact_id} does not link back to {requirement_id}",
                    )
                )
            if state == "human-validated":
                validation = artifact.get("validation")
                if not isinstance(validation, dict) or validation.get("status") != "human-validated":
                    findings.append(
                        _finding(
                            "unvalidated-artifact-for-human-state",
                            package,
                            f"{artifact_id} is not human validated",
                        )
                    )

    for artifact_id, artifact in sorted(artifacts.items()):
        requirement_ids = artifact.get("requirement_ids")
        if not isinstance(requirement_ids, list) or not requirement_ids:
            findings.append(
                _finding(
                    "invalid-artifact-requirements",
                    package,
                    f"{artifact_id} has no requirement_ids",
                )
            )
            continue
        for requirement_id in requirement_ids:
            if requirement_id not in required_set:
                findings.append(
                    _finding(
                        "unknown-artifact-requirement",
                        package,
                        f"{artifact_id} references unknown {requirement_id}",
                    )
                )
                continue
            linked = states.get(requirement_id, {}).get("artifact_ids", [])
            if artifact_id not in linked:
                findings.append(
                    _finding(
                        "asymmetric-requirement-link",
                        package,
                        f"{requirement_id} does not link back to {artifact_id}",
                    )
                )

    completion = record.get("completion_summary")
    if not isinstance(completion, dict):
        findings.append(
            _finding(
                "invalid-completion-summary",
                package,
                "completion_summary must be an object",
            )
        )
        completion = {}
    expected_counts = {
        "requirement_count": len(required_ids),
        "satisfied_requirement_count": satisfied,
        "human_validated_requirement_count": human_validated,
        "referenced_artifact_count": len(artifacts),
    }
    for field, expected in expected_counts.items():
        if completion.get(field) != expected:
            findings.append(
                _finding(
                    "completion-count-mismatch",
                    package,
                    f"{field} must equal {expected}",
                )
            )

    all_validated = len(states) == len(required_ids) and all(
        states.get(requirement_id, {}).get("state") == "human-validated"
        for requirement_id in required_ids
    )
    progress = bool(artifacts) or any(
        states.get(requirement_id, {}).get("state") != "missing"
        for requirement_id in required_ids
    )
    expected_status = (
        "evidence-ready-for-review"
        if all_validated
        else "collecting-human-evidence"
        if progress
        else "awaiting-human-evidence"
    )
    expected_readiness = (
        "evidence-ready-for-review-only" if all_validated else "not-ready"
    )
    if record.get("status") != expected_status:
        findings.append(
            _finding("false-package-status", package, f"status must equal {expected_status}")
        )
    if completion.get("review_readiness") != expected_readiness:
        findings.append(
            _finding(
                "false-review-readiness",
                package,
                f"review_readiness must equal {expected_readiness}",
            )
        )
    if completion.get("approval_implied") is not False:
        findings.append(_finding("approval-implied", package, "approval_implied must be false"))

    return {
        **expected_counts,
        "review_readiness": completion.get("review_readiness"),
    }, findings


def _finalize(
    requirements_count: int,
    package_count: int,
    entries: list[EvidencePackageEntry],
    findings: list[EvidencePackageFinding],
) -> EvidencePackageAuditReport:
    ordered_entries = tuple(sorted(entries, key=lambda item: item.document_path))
    ordered_findings = tuple(
        sorted(
            findings,
            key=lambda item: (
                item.document_path,
                item.code,
                item.requirements_id or "",
                item.package_id or "",
                item.message,
            ),
        )
    )
    statuses = Counter(
        entry.status for entry in ordered_entries if entry.valid and entry.status is not None
    )
    return EvidencePackageAuditReport(
        requirements_document_count=requirements_count,
        package_document_count=package_count,
        valid_package_count=sum(entry.valid for entry in ordered_entries),
        invalid_package_count=sum(not entry.valid for entry in ordered_entries),
        active_package_count=sum(entry.valid and entry.active for entry in ordered_entries),
        status_counts=tuple(sorted(statuses.items())),
        entries=ordered_entries,
        findings=ordered_findings,
        clean=not ordered_findings,
    )


def audit_evidence_package_documents(
    requirements_documents: Mapping[str, bytes],
    package_documents: Mapping[str, bytes],
) -> EvidencePackageAuditReport:
    """Audit immutable evidence documents without I/O or mutation."""

    findings: list[EvidencePackageFinding] = []
    entries: list[EvidencePackageEntry] = []

    requirements_by_id: dict[str, list[_Document]] = defaultdict(list)
    for path in sorted(requirements_documents):
        try:
            document = _decode(path, requirements_documents[path], "requirements")
            requirements_by_id[_required_text(document.record, "requirements_id")].append(document)
        except ValueError as exc:
            findings.append(_finding("invalid-requirements-document", None, str(exc), path=path))
    for requirements_id, documents in sorted(requirements_by_id.items()):
        if len(documents) > 1:
            for document in documents:
                findings.append(
                    _finding(
                        "duplicate-requirements-id",
                        document,
                        f"{requirements_id} appears in multiple documents",
                    )
                )

    package_groups: dict[str, list[_Document]] = defaultdict(list)
    for path in sorted(package_documents):
        try:
            document = _decode(path, package_documents[path], "package")
            package_groups[_required_text(document.record, "package_id")].append(document)
        except ValueError as exc:
            findings.append(_finding("invalid-package-document", None, str(exc), path=path))
            entries.append(
                EvidencePackageEntry(
                    path, None, None, False, False, None, 0, 0, 0, 0, None, None,
                    ("invalid-package-document",),
                )
            )

    duplicates = {package_id for package_id, docs in package_groups.items() if len(docs) > 1}
    packages = {
        package_id: docs[0]
        for package_id, docs in package_groups.items()
        if package_id not in duplicates
    }
    for package_id in sorted(duplicates):
        for document in package_groups[package_id]:
            findings.append(_finding("duplicate-package-id", document, f"{package_id} is duplicated"))
            entries.append(
                EvidencePackageEntry(
                    document.path,
                    document.record.get("requirements_id"),
                    package_id,
                    False,
                    False,
                    document.record.get("status"),
                    0, 0, 0, 0, None,
                    document.record.get("supersedes_package_id"),
                    ("duplicate-package-id",),
                )
            )

    successors: dict[str, list[str]] = defaultdict(list)
    chain_errors: dict[str, set[str]] = defaultdict(set)
    for package_id, document in sorted(packages.items()):
        prior_id = document.record.get("supersedes_package_id")
        if prior_id is None:
            continue
        prior = packages.get(prior_id)
        if prior is None:
            findings.append(
                _finding("unknown-superseded-package", document, f"{prior_id} does not exist uniquely")
            )
            chain_errors[package_id].add("unknown-superseded-package")
            continue
        successors[prior_id].append(package_id)
        if document.record.get("requirements_id") != prior.record.get("requirements_id"):
            findings.append(
                _finding("cross-requirements-supersession", document, "supersession crosses requirements records")
            )
            chain_errors[package_id].add("cross-requirements-supersession")
        current_time = _parse_time(document.record.get("created_at"))
        prior_time = _parse_time(prior.record.get("created_at"))
        if current_time is None or prior_time is None or current_time <= prior_time:
            findings.append(
                _finding("nonmonotonic-supersession-time", document, "superseding package must be newer")
            )
            chain_errors[package_id].add("nonmonotonic-supersession-time")

    for prior_id, next_ids in sorted(successors.items()):
        if len(next_ids) > 1:
            for package_id in next_ids:
                findings.append(
                    _finding("branched-supersession", packages[package_id], f"{prior_id} has multiple successors")
                )
                chain_errors[package_id].add("branched-supersession")

    for start_id, start in sorted(packages.items()):
        seen: set[str] = set()
        current_id: str | None = start_id
        while current_id is not None:
            if current_id in seen:
                findings.append(_finding("supersession-cycle", start, "supersession chain contains a cycle"))
                chain_errors[start_id].add("supersession-cycle")
                break
            seen.add(current_id)
            current = packages.get(current_id)
            current_id = current.record.get("supersedes_package_id") if current else None

    roots: dict[str, list[str]] = defaultdict(list)
    for package_id, document in sorted(packages.items()):
        if document.record.get("supersedes_package_id") is None:
            roots[document.record.get("requirements_id")].append(package_id)
    for requirements_id, root_ids in sorted(roots.items()):
        if len(root_ids) > 1:
            for package_id in root_ids:
                findings.append(
                    _finding(
                        "multiple-package-roots",
                        packages[package_id],
                        f"{requirements_id} has multiple package histories",
                    )
                )
                chain_errors[package_id].add("multiple-package-roots")

    superseded_ids = set(successors)
    for package_id, document in sorted(packages.items()):
        local: list[EvidencePackageFinding] = []
        metrics: dict[str, Any] = {
            "requirement_count": 0,
            "satisfied_requirement_count": 0,
            "human_validated_requirement_count": 0,
            "referenced_artifact_count": 0,
            "review_readiness": None,
        }
        requirements_id = document.record.get("requirements_id")
        candidates = requirements_by_id.get(requirements_id, [])
        if not candidates:
            local.append(_finding("orphan-package", document, "requirements document is missing"))
        elif len(candidates) > 1:
            local.append(_finding("ambiguous-requirements-target", document, "requirements ID is duplicated"))
        else:
            metrics, manifest_findings = _audit_manifest(document, candidates[0])
            local.extend(manifest_findings)
        findings.extend(local)
        codes = {item.code for item in local} | chain_errors.get(package_id, set())
        entries.append(
            EvidencePackageEntry(
                document_path=document.path,
                requirements_id=requirements_id,
                package_id=package_id,
                valid=not codes,
                active=not codes and package_id not in superseded_ids,
                status=document.record.get("status"),
                requirement_count=metrics["requirement_count"],
                satisfied_requirement_count=metrics["satisfied_requirement_count"],
                human_validated_requirement_count=metrics["human_validated_requirement_count"],
                referenced_artifact_count=metrics["referenced_artifact_count"],
                review_readiness=metrics["review_readiness"],
                supersedes_package_id=document.record.get("supersedes_package_id"),
                error_codes=tuple(sorted(codes)),
            )
        )

    return _finalize(
        len(requirements_documents),
        len(package_documents),
        entries,
        findings,
    )


def audit_evidence_packages(repository_root: Path) -> EvidencePackageAuditReport:
    """Read and audit repository manifests using only deterministic read_bytes calls."""

    root = Path(repository_root)
    requirements_dir = root / "registry/versification/evidence-requirements"
    packages_dir = root / "registry/versification/evidence-packages"
    requirements_documents = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(requirements_dir.glob("*.json"))
    }
    package_documents = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(packages_dir.glob("*.json"))
    }
    report = audit_evidence_package_documents(requirements_documents, package_documents)
    missing: list[EvidencePackageFinding] = []
    if not requirements_dir.is_dir():
        missing.append(
            EvidencePackageFinding(
                "missing-registry-directory",
                requirements_dir.relative_to(root).as_posix(),
                None,
                None,
                "evidence-requirements directory does not exist",
            )
        )
    if not packages_dir.is_dir():
        missing.append(
            EvidencePackageFinding(
                "missing-registry-directory",
                packages_dir.relative_to(root).as_posix(),
                None,
                None,
                "evidence-packages directory does not exist",
            )
        )
    if not missing:
        return report
    return _finalize(
        report.requirements_document_count,
        report.package_document_count,
        list(report.entries),
        [*report.findings, *missing],
    )
