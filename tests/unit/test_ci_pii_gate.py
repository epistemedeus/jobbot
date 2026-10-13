"""The PII guard is a hard CI gate, and smoke scripts never depend on a tracked CV."""

from __future__ import annotations

import re
from pathlib import Path

import yaml


def _ci_steps(project_root: Path) -> list[dict[str, object]]:
    ci = yaml.safe_load((project_root / ".github" / "workflows" / "ci.yml").read_text("utf-8"))
    steps: list[dict[str, object]] = ci["jobs"]["test"]["steps"]
    return steps


def test_ci_runs_the_pii_guard_over_the_tracked_tree_as_its_own_gate(project_root: Path) -> None:
    """A release PR tolerates 5% failing tests, so the guard cannot live only inside pytest."""
    steps = _ci_steps(project_root)
    runs = [str(step.get("run", "")) for step in steps]
    guard = [i for i, run in enumerate(runs) if "jobbot.ops.pii_guard --all" in run]
    assert guard, "ci.yml must run `python -m jobbot.ops.pii_guard --all`"

    step = steps[guard[0]]
    assert not step.get("continue-on-error"), "the PII guard must fail the job"
    tests = next(i for i, run in enumerate(runs) if "pytest" in run)
    assert guard[0] < tests, "the guard runs before the suite, whatever the pass-rate gate"


def test_smoke_scripts_only_reference_fixtures_that_exist(project_root: Path) -> None:
    """A smoke script pointing at a removed fixture fails on every machine."""
    missing: list[str] = []
    for script in sorted((project_root / "scripts").glob("*.sh")):
        text = script.read_text("utf-8")
        for ref in re.findall(r"tests/fixtures/[\w./-]+", text):
            if not (project_root / ref).exists():
                missing.append(f"{script.name}: {ref}")
    assert not missing, missing


def test_smoke_scripts_build_the_cv_at_run_time(project_root: Path) -> None:
    """No CV binary is tracked: smoke runs generate the invented sample CV."""
    for name in ("smoke-cold-home.sh", "smoke-cold-docker.sh"):
        text = (project_root / "scripts" / name).read_text("utf-8")
        assert "write_sample_cv" in text, name
        assert "tests/fixtures/cvs" not in text, name
