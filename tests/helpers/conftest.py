"""Fixtures shared by the helpers tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.helpers.git_repo import GitRepo, init_git_repo


@pytest.fixture()
def git_repo(tmp_path: Path) -> GitRepo:
    """An empty Git repository at tmp_path; skipped where git is missing."""
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    return init_git_repo(tmp_path)
