"""`getonboard upload-cv` validates before any browser work."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE


def _workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _write_pdf(root: Path) -> Path:
    path = root / "output" / "base" / "cv.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4\n" + b"x" * 200)
    return path


def test_dry_run_prints_the_hash_and_does_not_open_a_browser(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    path = _write_pdf(tmp_path)
    from jobbot.cli import run_cli

    opened: list[str] = []

    def _no_session(*_a: object, **_k: object) -> None:
        opened.append("session")

    monkeypatch.setattr("jobbot.cli._getonboard_session", _no_session)

    assert run_cli(["getonboard", "upload-cv"], standalone_mode=False) == SUCCESS
    from tests.conftest import plain_cli_text

    out = plain_cli_text(capsys.readouterr().out)

    assert opened == []
    assert "sha256:" in out
    assert path.name in out
    assert "Dry-run" in out


def test_successful_upload_warns_that_gob_may_rewrite_the_profile(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    _write_pdf(tmp_path)
    from jobbot.adapters.getonboard.cv_upload import CvUploadResult
    from jobbot.adapters.getonboard.profile_edit import CV_REWRITE_NOTICE
    from jobbot.cli import run_cli
    from tests.conftest import plain_cli_text

    class _Session:
        def __enter__(self) -> _Session:
            return self

        def __exit__(self, *_a: object) -> None:
            return None

        @property
        def page(self) -> object:
            return object()

    monkeypatch.setattr("jobbot.cli._getonboard_session", lambda *_a, **_k: _Session())

    def _upload(page: object, path: Path, **_k: object) -> CvUploadResult:
        return CvUploadResult(
            label="CV base",
            path=path,
            listed=True,
            is_default=True,
        )

    monkeypatch.setattr("jobbot.adapters.getonboard.cv_upload.upload_cv", _upload)

    assert (
        run_cli(
            ["getonboard", "upload-cv", "--apply", "--yes"],
            standalone_mode=False,
        )
        == SUCCESS
    )
    out = plain_cli_text(capsys.readouterr().out)
    assert "Estamos leyendo tu último CV" in out or CV_REWRITE_NOTICE.split("`")[0] in out
    assert "cv sync --apply" in out


def test_a_broken_pdf_never_reaches_the_browser(
    tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    bad = tmp_path / "output" / "base" / "cv.pdf"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b"not-a-pdf")
    from jobbot.cli import run_cli

    opened: list[str] = []

    def _no_session(*_a: object, **_k: object) -> None:
        opened.append("session")

    monkeypatch.setattr("jobbot.cli._getonboard_session", _no_session)

    code = run_cli(["getonboard", "upload-cv", "--apply", "--yes"], standalone_mode=False)

    assert code == VALIDATION_FAILURE
    assert opened == []
