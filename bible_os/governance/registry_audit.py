"""Read-only integrity audit for versification governance registry documents."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .queue_state import QueueStateError, reduce_queue_state

_QUEUE_ID = re.compile(r"^vrq_[a-z0-9]{12,}$")


@dataclass(frozen=True, slots=True)
class RegistryAuditFinding:
    """One deterministic integrity finding produced by the registry audit."""

    code: str
    severity: str
    document_path: str
    queue_item_id: str | None
    message: str


@dataclass(frozen=True, slots=True)
class QueueAuditEntry:
    """Read-only effective-state summary for one queue document."""

    document_path: str
    queue_item_id: str | None
    valid: bool
    initial_status: str | None
    effective_status: str | None
    status_source: str | None
    transition_count: int
    effective_transition_ids: tuple[str, ...]
    superseded_transition_ids: tuple[str, ...]
    last_applied_at: str | None
    error_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RegistryAuditReport:
    """Frozen report for a complete read-only registry audit."""

    queue_document_count: int
    transition_document_count: int
    valid_queue_count: int
    invalid_queue_count: int
    orphan_transition_count: int
    status_counts: tuple[tuple[str, int], ...]
    entries: tuple[QueueAuditEntry, ...]
    findings: tuple[RegistryAuditFinding, ...]
    clean: bool


def _decode_object(document: bytes, *, label: str) -> dict[str, Any]:
    if not isinstance(document, bytes):
        raise ValueError(f"{label} must be immutable bytes")
    try:
        value = json.loads(document.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must decode to a JSON object")
    return value


def _queue_id(record: Mapping[str, Any], *, label: str) -> str:
    value = record.get("queue_item_id")
    if not isinstance(value, str) or _QUEUE_ID.fullmatch(value) is None:
        raise ValueError(f"{label}.queue_item_id is invalid")
    return value


def _raw_status(record: Mapping[str, Any]) -> str | None:
    value = record.get("status")
    return value if isinstance(value, str) and value else None


def _finding(
    code: str,
    path: str,
    message: str,
    *,
    queue_item_id: str | None = None,
) -> RegistryAuditFinding:
    return RegistryAuditFinding(
        code=code,
        severity="error",
        document_path=path,
        queue_item_id=queue_item_id,
        message=message,
    )


def _invalid_entry(
    path: str,
    *,
    queue_item_id: str | None,
    initial_status: str | None,
    transition_count: int,
    error_codes: tuple[str, ...],
) -> QueueAuditEntry:
    return QueueAuditEntry(
        document_path=path,
        queue_item_id=queue_item_id,
        valid=False,
        initial_status=initial_status,
        effective_status=None,
        status_source=None,
        transition_count=transition_count,
        effective_transition_ids=(),
        superseded_transition_ids=(),
        last_applied_at=None,
        error_codes=error_codes,
    )


def _finalize(
    *,
    queue_document_count: int,
    transition_document_count: int,
    entries: list[QueueAuditEntry],
    findings: list[RegistryAuditFinding],
) -> RegistryAuditReport:
    ordered_entries = tuple(
        sorted(entries, key=lambda entry: (entry.document_path, entry.queue_item_id or ""))
    )
    ordered_findings = tuple(
        sorted(
            findings,
            key=lambda item: (
                item.document_path,
                item.code,
                item.queue_item_id or "",
                item.message,
            ),
        )
    )
    status_counts = Counter(
        entry.effective_status
        for entry in ordered_entries
        if entry.valid and entry.effective_status is not None
    )
    return RegistryAuditReport(
        queue_document_count=queue_document_count,
        transition_document_count=transition_document_count,
        valid_queue_count=sum(entry.valid for entry in ordered_entries),
        invalid_queue_count=sum(not entry.valid for entry in ordered_entries),
        orphan_transition_count=sum(
            finding.code == "orphan-transition" for finding in ordered_findings
        ),
        status_counts=tuple(sorted(status_counts.items())),
        entries=ordered_entries,
        findings=ordered_findings,
        clean=not ordered_findings,
    )


def audit_registry_documents(
    queue_documents: Mapping[str, bytes],
    transition_documents: Mapping[str, bytes],
) -> RegistryAuditReport:
    """Audit supplied immutable registry documents without performing I/O.

    Mapping keys are stable logical paths used only for deterministic reporting.
    Mapping values must be the exact UTF-8 JSON bytes stored in the registry.
    """

    findings: list[RegistryAuditFinding] = []
    entries: list[QueueAuditEntry] = []

    queue_records: dict[str, tuple[bytes, dict[str, Any]]] = {}
    queue_paths_by_id: dict[str, list[str]] = defaultdict(list)

    for path in sorted(queue_documents):
        document = queue_documents[path]
        try:
            record = _decode_object(document, label=f"queue document {path}")
        except ValueError as exc:
            findings.append(_finding("invalid-queue-document", path, str(exc)))
            entries.append(
                _invalid_entry(
                    path,
                    queue_item_id=None,
                    initial_status=None,
                    transition_count=0,
                    error_codes=("invalid-queue-document",),
                )
            )
            continue

        try:
            queue_item_id = _queue_id(record, label=f"queue document {path}")
        except ValueError as exc:
            findings.append(_finding("invalid-queue-id", path, str(exc)))
            entries.append(
                _invalid_entry(
                    path,
                    queue_item_id=None,
                    initial_status=_raw_status(record),
                    transition_count=0,
                    error_codes=("invalid-queue-id",),
                )
            )
            continue

        queue_records[path] = (document, record)
        queue_paths_by_id[queue_item_id].append(path)

    transitions_by_queue: dict[str, list[tuple[str, bytes]]] = defaultdict(list)
    parsed_transition_paths: set[str] = set()

    for path in sorted(transition_documents):
        document = transition_documents[path]
        try:
            record = _decode_object(document, label=f"transition document {path}")
        except ValueError as exc:
            findings.append(_finding("invalid-transition-document", path, str(exc)))
            continue

        try:
            queue_item_id = _queue_id(record, label=f"transition document {path}")
        except ValueError as exc:
            findings.append(_finding("invalid-transition-queue-id", path, str(exc)))
            continue

        parsed_transition_paths.add(path)
        transitions_by_queue[queue_item_id].append((path, document))

    duplicate_queue_ids = {
        queue_item_id
        for queue_item_id, paths in queue_paths_by_id.items()
        if len(paths) > 1
    }

    for queue_item_id in sorted(duplicate_queue_ids):
        paths = sorted(queue_paths_by_id[queue_item_id])
        transition_count = len(transitions_by_queue.get(queue_item_id, ()))
        for path in paths:
            _, record = queue_records[path]
            findings.append(
                _finding(
                    "duplicate-queue-item-id",
                    path,
                    f"queue_item_id {queue_item_id} appears in {len(paths)} documents",
                    queue_item_id=queue_item_id,
                )
            )
            entries.append(
                _invalid_entry(
                    path,
                    queue_item_id=queue_item_id,
                    initial_status=_raw_status(record),
                    transition_count=transition_count,
                    error_codes=("duplicate-queue-item-id",),
                )
            )
        for transition_path, _ in transitions_by_queue.get(queue_item_id, ()):
            findings.append(
                _finding(
                    "ambiguous-transition-target",
                    transition_path,
                    "transition targets a duplicated queue_item_id",
                    queue_item_id=queue_item_id,
                )
            )

    known_queue_ids = set(queue_paths_by_id)
    for queue_item_id in sorted(set(transitions_by_queue) - known_queue_ids):
        for path, _ in sorted(transitions_by_queue[queue_item_id]):
            findings.append(
                _finding(
                    "orphan-transition",
                    path,
                    "transition references a queue_item_id with no queue document",
                    queue_item_id=queue_item_id,
                )
            )

    for queue_item_id in sorted(known_queue_ids - duplicate_queue_ids):
        path = queue_paths_by_id[queue_item_id][0]
        queue_document, record = queue_records[path]
        transition_items = sorted(transitions_by_queue.get(queue_item_id, ()))
        transition_bytes = [document for _, document in transition_items]
        try:
            state = reduce_queue_state(queue_document, transition_bytes)
        except QueueStateError as exc:
            findings.append(
                _finding(
                    "invalid-transition-chain",
                    path,
                    str(exc),
                    queue_item_id=queue_item_id,
                )
            )
            entries.append(
                _invalid_entry(
                    path,
                    queue_item_id=queue_item_id,
                    initial_status=_raw_status(record),
                    transition_count=len(transition_items),
                    error_codes=("invalid-transition-chain",),
                )
            )
            continue

        entries.append(
            QueueAuditEntry(
                document_path=path,
                queue_item_id=state.queue_item_id,
                valid=True,
                initial_status=state.initial_status,
                effective_status=state.effective_status,
                status_source=state.status_source,
                transition_count=state.transition_count,
                effective_transition_ids=state.effective_transition_ids,
                superseded_transition_ids=state.superseded_transition_ids,
                last_applied_at=state.last_applied_at,
                error_codes=(),
            )
        )

    return _finalize(
        queue_document_count=len(queue_documents),
        transition_document_count=len(transition_documents),
        entries=entries,
        findings=findings,
    )


def audit_registry(repository_root: Path) -> RegistryAuditReport:
    """Read and audit the repository's versification governance registry.

    The function performs only deterministic directory enumeration and `read_bytes()`
    calls. It never creates, updates, renames, or deletes a file.
    """

    root = Path(repository_root)
    queue_directory = root / "registry/versification/review-queue"
    transition_directory = root / "registry/versification/queue-transitions"

    queue_documents = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(queue_directory.glob("*.json"))
    }
    transition_documents = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(transition_directory.glob("*.json"))
    }

    report = audit_registry_documents(queue_documents, transition_documents)
    missing_findings: list[RegistryAuditFinding] = []
    if not queue_directory.is_dir():
        missing_findings.append(
            _finding(
                "missing-registry-directory",
                queue_directory.relative_to(root).as_posix(),
                "versification review-queue directory does not exist",
            )
        )
    if not transition_directory.is_dir():
        missing_findings.append(
            _finding(
                "missing-registry-directory",
                transition_directory.relative_to(root).as_posix(),
                "versification queue-transitions directory does not exist",
            )
        )
    if not missing_findings:
        return report

    return _finalize(
        queue_document_count=report.queue_document_count,
        transition_document_count=report.transition_document_count,
        entries=list(report.entries),
        findings=[*report.findings, *missing_findings],
    )
