"""`portals catalog`: a dry run writes nothing and the plan creates no account."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console

from jobbot.config import load_config
from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE

SEED = """
catalog_version: "0.1.0"
country: CL
researched_at: 2026-10-12
expected:
  employers: 2
  channels: 2
channels:
  - employer: "Empresa Demo"
    sector: demo
    url: "https://empresa-demo.cl/empleos"
    type: listing
    ats: trabajando
    read: fetched
  - employer: "Otra Demo"
    sector: demo
    url: "https://ats-demo.com/otra-demo"
    type: access
    ats: hiringroom
    read: reader_error
research_queue:
  demo: [Marca Pendiente]
"""


def _workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    seed = tmp_path / "seed.yaml"
    seed.write_text(SEED, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return seed


def _console(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    import jobbot.cli as cli

    buffer = io.StringIO()
    monkeypatch.setattr(cli, "console", Console(file=buffer, width=140, color_system=None))
    return buffer


def test_import_is_a_dry_run_until_apply(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = _workspace(tmp_path, project_root, monkeypatch)
    import jobbot.cli as cli

    buffer = _console(monkeypatch)
    assert cli.run_cli(["portals", "catalog", "import", str(seed)], standalone_mode=False) == (
        SUCCESS
    )

    out = buffer.getvalue()
    assert "dry-run (nothing written)" in out
    assert "2 employers, 2 channels" in out
    assert "enabled       : 0" in out
    assert not load_config().catalog_path.exists()


def test_apply_writes_a_catalog_of_candidates(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = _workspace(tmp_path, project_root, monkeypatch)
    import jobbot.cli as cli
    from jobbot.catalog.registry import load_catalog

    _console(monkeypatch)
    argv = ["portals", "catalog", "import", str(seed), "--apply"]
    assert cli.run_cli(argv, standalone_mode=False) == SUCCESS

    catalog = load_catalog(load_config().catalog_path)
    assert len(catalog.channels) == 2
    assert not any(channel.enabled for channel in catalog.channels)

    buffer = _console(monkeypatch)
    assert cli.run_cli(argv, standalone_mode=False) == SUCCESS
    assert "+0 employers, +0 channels" in buffer.getvalue()


def test_a_seed_whose_counts_do_not_match_writes_nothing(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = _workspace(tmp_path, project_root, monkeypatch)
    seed.write_text(SEED.replace("channels: 2", "channels: 9"), encoding="utf-8")
    import jobbot.cli as cli

    buffer = _console(monkeypatch)
    argv = ["portals", "catalog", "import", str(seed), "--apply"]
    assert cli.run_cli(argv, standalone_mode=False) == VALIDATION_FAILURE

    assert "count mismatch" in buffer.getvalue()
    assert not load_config().catalog_path.exists()


def test_the_plan_lists_what_needs_review_and_opens_nothing(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = _workspace(tmp_path, project_root, monkeypatch)
    import jobbot.cli as cli

    _console(monkeypatch)
    cli.run_cli(["portals", "catalog", "import", str(seed), "--apply"], standalone_mode=False)

    buffer = _console(monkeypatch)
    assert cli.run_cli(["portals", "catalog", "plan"], standalone_mode=False) == SUCCESS

    out = buffer.getvalue()
    assert "explorable now : 0" in out
    assert "disabled" in out and "not_extracted" in out
    assert "No account was created and no application was sent." in out


def test_list_shows_the_observed_platform_and_employer(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = _workspace(tmp_path, project_root, monkeypatch)
    import jobbot.cli as cli

    _console(monkeypatch)
    cli.run_cli(["portals", "catalog", "import", str(seed), "--apply"], standalone_mode=False)

    buffer = _console(monkeypatch)
    argv = ["portals", "catalog", "list", "--ats", "trabajando"]
    assert cli.run_cli(argv, standalone_mode=False) == SUCCESS

    out = buffer.getvalue()
    assert "Empresa Demo" in out
    assert "Otra Demo" not in out
    assert "0 enabled" in out
