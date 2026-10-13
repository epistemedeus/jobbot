"""Tests never act on the repository that runs them.

git exports GIT_DIR (and friends) to its hooks. A commit from a linked worktree
runs the suite with GIT_DIR pointing at that worktree's admin directory, and a
test that runs `git init` in a temp folder would then re-initialise the real
repository and set `core.bare = true` in its shared config.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tests.conftest import GIT_REPO_ENV

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".githooks" / "pre-commit"


def _git(*args: str, cwd: Path, env: dict[str, str] | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True
    ).stdout.strip()


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in GIT_REPO_ENV}


def test_conftest_clears_every_repo_local_git_variable() -> None:
    """The list must cover what git itself calls repository-local."""
    listed = set(_git("rev-parse", "--local-env-vars", cwd=ROOT, env=_clean_env()).split())
    assert listed <= set(GIT_REPO_ENV)
    assert not [name for name in GIT_REPO_ENV if name in os.environ]


def test_suite_run_from_a_hook_leaves_the_calling_repo_alone(tmp_path: Path) -> None:
    """The hook's GIT_DIR must not reach the `git init` a test runs."""
    caller = tmp_path / "caller"
    caller.mkdir()
    clean = _clean_env() | {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    _git("init", "-q", cwd=caller, env=clean)
    _git("commit", "-q", "--allow-empty", "-m", "init", cwd=caller, env=clean)
    _git("worktree", "add", "-q", str(tmp_path / "wt"), "-b", "feat", cwd=caller, env=clean)
    git_dir = caller / ".git"
    before = _git("--git-dir", str(git_dir), "config", "--get", "core.bare", cwd=tmp_path)

    # What git exports to a hook when the commit happens in a linked worktree.
    admin = git_dir / "worktrees" / "wt"
    env = _clean_env() | {"GIT_DIR": str(admin), "GIT_INDEX_FILE": str(admin / "index")}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/unit/test_workspace_init.py::test_init_gitignore_is_honoured_by_git",
        ],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
    )

    after = _git("--git-dir", str(git_dir), "config", "--get", "core.bare", cwd=tmp_path)
    assert (before, after) == ("false", "false")


def test_hook_unsets_repo_variables_before_the_suite() -> None:
    """The staged-files check needs GIT_INDEX_FILE; the suite must not see it."""
    body = HOOK.read_text(encoding="utf-8")
    unset = body.index("unset $(git rev-parse --local-env-vars)")
    assert body.index("jobbot.ops.precommit") < unset < body.index("pytest")
