from __future__ import annotations

import json
import shutil
from pathlib import Path

from scripts.evidence_package_integrity import main, run


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


def copy_registered_package(destination_root: Path) -> tuple[Path, Path]:
    requirements_destination = destination_root / REQUIREMENTS_PATH.relative_to(ROOT)
    package_destination = destination_root / PACKAGE_PATH.relative_to(ROOT)
    requirements_destination.parent.mkdir(parents=True, exist_ok=True)
    package_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REQUIREMENTS_PATH, requirements_destination)
    shutil.copyfile(PACKAGE_PATH, package_destination)
    return requirements_destination, package_destination


def test_registered_evidence_package_integrity_cli_passes(tmp_path: Path):
    report_path = tmp_path / "evidence-package-integrity.json"
    before = {
        REQUIREMENTS_PATH: REQUIREMENTS_PATH.read_bytes(),
        PACKAGE_PATH: PACKAGE_PATH.read_bytes(),
    }

    assert main(["--root", str(ROOT), "--report", str(report_path)]) == 0

    result = json.loads(report_path.read_text(encoding="utf-8"))
    assert result["schema_version"] == "1.0.0"
    assert result["status"] == "passed"
    assert result["read_only"] is True
    assert result["evidence_collection"] == "not-performed"
    assert result["registry_mutation"] == "not-performed"
    assert result["decision_authority"] == "none"
    assert result["queue_status_authority"] == "none"
    assert result["materialization_authority"] == "none"
    assert result["execution_eligible"] is False
    assert result["publication_eligible"] is False

    audit = result["audit"]
    assert audit["clean"] is True
    assert audit["requirements_document_count"] == 1
    assert audit["package_document_count"] == 1
    assert audit["valid_package_count"] == 1
    assert audit["invalid_package_count"] == 0
    assert audit["active_package_count"] == 1
    assert audit["status_counts"] == [["awaiting-human-evidence", 1]]
    assert audit["findings"] == []
    assert audit["entries"][0]["package_id"] == "vep_asvwebpromans01"
    assert audit["entries"][0]["review_readiness"] == "not-ready"

    rendered = report_path.read_text(encoding="utf-8")
    for prohibited_key in (
        '"artifacts"',
        '"artifact_kind"',
        '"citation"',
        '"locator"',
        '"source_references"',
        '"target_references"',
    ):
        assert prohibited_key not in rendered

    assert {path: path.read_bytes() for path in before} == before


def test_integrity_cli_fails_with_structured_metadata_only_findings(tmp_path: Path):
    requirements_path, package_path = copy_registered_package(tmp_path)
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["requirements_sha256"] = "0" * 64
    package_path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")

    registry_before = {
        requirements_path: requirements_path.read_bytes(),
        package_path: package_path.read_bytes(),
    }
    report_path = tmp_path / "failed-evidence-package-integrity.json"

    assert main(["--root", str(tmp_path), "--report", str(report_path)]) == 1

    result = json.loads(report_path.read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["audit"]["clean"] is False
    assert "requirements-hash-mismatch" in {
        finding["code"] for finding in result["audit"]["findings"]
    }
    assert result["evidence_collection"] == "not-performed"
    assert result["registry_mutation"] == "not-performed"
    assert {path: path.read_bytes() for path in registry_before} == registry_before


def test_cli_output_is_deterministic(tmp_path: Path):
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"

    assert run(ROOT) == run(ROOT)
    assert main(["--root", str(ROOT), "--report", str(first_path)]) == 0
    assert main(["--root", str(ROOT), "--report", str(second_path)]) == 0
    assert first_path.read_bytes() == second_path.read_bytes()
