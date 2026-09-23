"""A throwaway Git repository for tests that need real history."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GitRepo:
    """
    A Git repository in a temporary folder.

    Attributes:
        root (Path): The repository root.
    """

    root: Path

    def run(self, *args: str) -> str:
        """Run git in the repository and return its output."""
        result = subprocess.run(
            ["git", "-C", str(self.root), *args],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def commit(self, message: str) -> str:
        """Commit every change and return the commit ID."""
        self.run("add", "--all")
        self.run("commit", "--quiet", "--allow-empty", "--message", message)
        return self.run("rev-parse", "HEAD")


def init_git_repo(root: Path) -> GitRepo:
    """Create an empty repository at ``root``, isolated from user settings."""
    repo = GitRepo(root)
    repo.run("init", "--quiet")
    for key, value in (
        ("user.name", "Test"),
        ("user.email", "test@example.com"),
        ("commit.gpgsign", "false"),
        ("core.autocrlf", "false"),
    ):
        repo.run("config", key, value)
    return repo
