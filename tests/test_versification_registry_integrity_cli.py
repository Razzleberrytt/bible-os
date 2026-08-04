from __future__ import annotations

import json
from pathlib import Path

from scripts.versification_registry_integrity import main, run


ROOT = Path(__file__).resolve().parents[1]


def test_registered_registry_integrity_cli_passes(tmp_path: Path):
    report_path = tmp_path / "registry-integrity.json"
    synthetic_queue_path = (
        ROOT
        / "registry/versification/review-queue/synthetic-split-candidate.json"
    )
    romans_queue_path = (
        ROOT
        / "registry/versification/review-queue/asv-webp-romans-structural-candidate.json"
    )
    transition_path = (
        ROOT
        / "registry/versification/queue-transitions"
        / "synthetic-split-needs-evidence.json"
    )
    before = {
        synthetic_queue_path: synthetic_queue_path.read_bytes(),
        romans_queue_path: romans_queue_path.read_bytes(),
        transition_path: transition_path.read_bytes(),
    }

    assert main(["--root", str(ROOT), "--report", str(report_path)]) == 0

    result = json.loads(report_path.read_text(encoding="utf-8"))
    assert result["schema_version"] == "1.0.0"
    assert result["status"] == "passed"
    assert result["read_only"] is True
    assert result["registry_mutation"] == "not-performed"
    assert result["materialization_authority"] == "none"
    assert result["execution_eligible"] is False
    assert result["publication_eligible"] is False
    assert result["audit"]["clean"] is True
    assert result["audit"]["queue_document_count"] == 2
    assert result["audit"]["transition_document_count"] == 1
    assert result["audit"]["status_counts"] == [
        ["needs-evidence", 1],
        ["queued", 1],
    ]

    assert {path: path.read_bytes() for path in before} == before


def test_integrity_cli_fails_with_structured_findings(tmp_path: Path):
    queue_directory = tmp_path / "registry/versification/review-queue"
    transition_directory = tmp_path / "registry/versification/queue-transitions"
    queue_directory.mkdir(parents=True)
    transition_directory.mkdir(parents=True)
    (queue_directory / "broken.json").write_text("{broken", encoding="utf-8")

    report_path = tmp_path / "failed-integrity.json"
    assert main(["--root", str(tmp_path), "--report", str(report_path)]) == 1

    result = json.loads(report_path.read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["audit"]["clean"] is False
    assert result["audit"]["findings"][0]["code"] == "invalid-queue-document"


def test_run_is_deterministic_for_the_registered_registry():
    first = run(ROOT)
    second = run(ROOT)
    assert first == second
