from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

LIVE_REPRODUCTION_WORKFLOWS = {
    "asv-database-load.yml",
    "asv-webp-candidate-analysis.yml",
    "asv-webp-character-marker-accounting.yml",
    "asv-webp-gospel-structure.yml",
    "asv-webp-lexical-fingerprints.yml",
    "asv-webp-wj-record-shape.yml",
    "asv-webp-wj-token-strata.yml",
}

LIVE_JOBS_REMOVED_FROM_GENERIC_CI = {
    "asv-acquisition",
    "asv-structure-smoke",
    "webp-acquisition",
    "webp-database-load",
}


def load_workflow(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def triggers(workflow: dict) -> dict:
    value = workflow.get("on", {})
    assert isinstance(value, dict)
    return value


def test_only_deterministic_ci_runs_on_pull_requests() -> None:
    pull_request_workflows: set[str] = set()
    for path in WORKFLOWS.glob("*.yml"):
        if "pull_request" in triggers(load_workflow(path)):
            pull_request_workflows.add(path.name)

    assert pull_request_workflows == {"ci.yml"}


def test_generic_ci_contains_no_live_source_jobs() -> None:
    workflow = load_workflow(WORKFLOWS / "ci.yml")
    workflow_triggers = triggers(workflow)
    jobs = set(workflow["jobs"])
    rendered = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")

    assert "pull_request" in workflow_triggers
    assert "push" in workflow_triggers
    assert "schedule" not in workflow_triggers
    assert jobs.isdisjoint(LIVE_JOBS_REMOVED_FROM_GENERIC_CI)
    assert "probe_acquisition.py" not in rendered
    assert "scripts.webp_full_ci" not in rendered
    assert "scripts.asv_adapter_smoke" not in rendered


def test_frozen_live_reproductions_are_manual_research_runs() -> None:
    for filename in LIVE_REPRODUCTION_WORKFLOWS:
        workflow_triggers = triggers(load_workflow(WORKFLOWS / filename))
        assert set(workflow_triggers) == {"workflow_dispatch"}, filename


def test_source_integrity_watch_is_scheduled_manual_and_not_a_pr_gate() -> None:
    path = WORKFLOWS / "source-integrity.yml"
    workflow = load_workflow(path)
    workflow_triggers = triggers(workflow)
    rendered = path.read_text(encoding="utf-8")

    assert "workflow_dispatch" in workflow_triggers
    assert "schedule" in workflow_triggers
    assert "pull_request" not in workflow_triggers
    assert "push" not in workflow_triggers
    assert "probe_acquisition.py" in rendered
    assert "Treat this as an upstream provenance event" in rendered
