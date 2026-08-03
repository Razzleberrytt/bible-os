from __future__ import annotations

import json
import shutil
from pathlib import Path

from bible_os.governance import audit_registry, audit_registry_documents


ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = (
    ROOT / "registry/versification/review-queue/synthetic-split-candidate.json"
)
TRANSITION_PATH = (
    ROOT
    / "registry/versification/queue-transitions"
    / "synthetic-split-needs-evidence.json"
)


def compact(record: dict) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")


def actual_queue_bytes() -> bytes:
    return QUEUE_PATH.read_bytes()


def actual_transition_bytes() -> bytes:
    return TRANSITION_PATH.read_bytes()


def test_current_registry_audits_cleanly_and_reports_effective_status():
    report = audit_registry(ROOT)

    assert report.clean is True
    assert report.queue_document_count == 1
    assert report.transition_document_count == 1
    assert report.valid_queue_count == 1
    assert report.invalid_queue_count == 0
    assert report.orphan_transition_count == 0
    assert report.status_counts == (("needs-evidence", 1),)
    assert report.findings == ()

    entry = report.entries[0]
    assert entry.queue_item_id == "vrq_synthsplit01"
    assert entry.valid is True
    assert entry.initial_status == "queued"
    assert entry.effective_status == "needs-evidence"
    assert entry.status_source == "append-only-transition-event"
    assert entry.transition_count == 1
    assert entry.effective_transition_ids == ("vqt_synthtransition01",)
    assert entry.superseded_transition_ids == ()
    assert entry.error_codes == ()


def test_audit_is_read_only_for_repository_files(tmp_path: Path):
    registry_root = tmp_path / "repo"
    queue_directory = registry_root / "registry/versification/review-queue"
    transition_directory = registry_root / "registry/versification/queue-transitions"
    queue_directory.mkdir(parents=True)
    transition_directory.mkdir(parents=True)
    shutil.copy2(QUEUE_PATH, queue_directory / QUEUE_PATH.name)
    shutil.copy2(TRANSITION_PATH, transition_directory / TRANSITION_PATH.name)

    before = {
        path.relative_to(registry_root).as_posix(): path.read_bytes()
        for path in sorted(registry_root.rglob("*"))
        if path.is_file()
    }
    report = audit_registry(registry_root)
    after = {
        path.relative_to(registry_root).as_posix(): path.read_bytes()
        for path in sorted(registry_root.rglob("*"))
        if path.is_file()
    }

    assert report.clean is True
    assert after == before


def test_orphan_transition_is_reported_without_crashing():
    report = audit_registry_documents(
        {},
        {"registry/transitions/orphan.json": actual_transition_bytes()},
    )

    assert report.clean is False
    assert report.queue_document_count == 0
    assert report.transition_document_count == 1
    assert report.orphan_transition_count == 1
    assert report.entries == ()
    assert [finding.code for finding in report.findings] == ["orphan-transition"]


def test_duplicate_queue_ids_are_ambiguous_and_invalid():
    queue = actual_queue_bytes()
    report = audit_registry_documents(
        {
            "queue/b.json": queue,
            "queue/a.json": queue,
        },
        {"transitions/event.json": actual_transition_bytes()},
    )

    assert report.clean is False
    assert report.valid_queue_count == 0
    assert report.invalid_queue_count == 2
    assert [entry.document_path for entry in report.entries] == [
        "queue/a.json",
        "queue/b.json",
    ]
    assert {finding.code for finding in report.findings} == {
        "ambiguous-transition-target",
        "duplicate-queue-item-id",
    }


def test_stale_queue_bytes_are_reported_as_an_invalid_chain():
    queue_record = json.loads(actual_queue_bytes())
    queue_record["priority"] = "high"

    report = audit_registry_documents(
        {"queue/item.json": compact(queue_record)},
        {"transitions/event.json": actual_transition_bytes()},
    )

    assert report.clean is False
    assert report.entries[0].valid is False
    assert report.entries[0].error_codes == ("invalid-transition-chain",)
    assert report.findings[0].code == "invalid-transition-chain"
    assert "queue_item_sha256 does not match bytes" in report.findings[0].message


def test_broken_status_chain_is_reported():
    transition = json.loads(actual_transition_bytes())
    transition["from_status"] = "in-review"

    report = audit_registry_documents(
        {"queue/item.json": actual_queue_bytes()},
        {"transitions/event.json": compact(transition)},
    )

    assert report.clean is False
    assert report.entries[0].valid is False
    assert report.findings[0].code == "invalid-transition-chain"
    assert "expects in-review but current status is queued" in report.findings[0].message


def test_malformed_documents_become_structured_findings():
    report = audit_registry_documents(
        {
            "queue/bad.json": b"[not-an-object]",
            "queue/good.json": actual_queue_bytes(),
        },
        {"transitions/bad.json": b"{"},
    )

    assert report.clean is False
    assert report.queue_document_count == 2
    assert report.transition_document_count == 1
    assert report.valid_queue_count == 1
    assert report.invalid_queue_count == 1
    assert {finding.code for finding in report.findings} == {
        "invalid-queue-document",
        "invalid-transition-document",
    }


def test_report_order_is_deterministic_regardless_of_mapping_insertion_order():
    documents_one = {
        "queue/z.json": b"not-json",
        "queue/a.json": b"[]",
    }
    documents_two = {
        "queue/a.json": b"[]",
        "queue/z.json": b"not-json",
    }

    first = audit_registry_documents(documents_one, {})
    second = audit_registry_documents(documents_two, {})

    assert first == second
    assert [entry.document_path for entry in first.entries] == [
        "queue/a.json",
        "queue/z.json",
    ]


def test_missing_registry_directories_are_reported():
    report = audit_registry(ROOT / "does-not-exist")

    assert report.clean is False
    assert report.queue_document_count == 0
    assert report.transition_document_count == 0
    assert [finding.code for finding in report.findings] == [
        "missing-registry-directory",
        "missing-registry-directory",
    ]
