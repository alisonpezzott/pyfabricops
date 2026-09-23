"""
Source changes: which items changed in Git since a baseline commit.

``ItemResolver`` maps changed files to the item folders they belong to, and
``GitChangeDetector`` asks git which files changed between a baseline commit
and HEAD and whether each changed item was added, modified or deleted. Both
only read. Git runs as a subprocess, so selective deployment needs git on
PATH and the baseline commit in the local history.

Internal for now: nothing here is exported from ``pyfabricops``.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath

from ..helpers.deployment_plan import SourceChange
from ..utils.exceptions import ConfigurationError

__all__ = ["GitChangeDetector", "ItemChange", "ItemResolver"]


@dataclass(frozen=True)
class ItemChange:
    """
    An item folder with changes between the baseline commit and HEAD.

    Attributes:
        item_type (str): The Fabric item type, from the folder suffix.
        path (str): The item folder, relative to the compared folder, with
            forward slashes.
        change (SourceChange): Whether the item was added, modified or
            deleted.
    """

    item_type: str
    path: str
    change: SourceChange


class ItemResolver:
    """
    Map changed files to the item folders they belong to.

    An item folder is named ``<display name>.<item type>``, the layout
    ``deploy_all_items`` reads. A file belongs to the outermost such folder
    on its path. Files outside any item folder, or in folders of other
    types, are ignored, and several files of one item give it once.

    Args:
        item_types (Iterable[str]): The item types to look for.
    """

    def __init__(self, item_types: Iterable[str]) -> None:
        self._item_types = frozenset(item_types)

    def resolve(self, paths: Iterable[str]) -> list[tuple[str, str]]:
        """
        Return the ``(item_type, item_path)`` of each item the files touch.

        Args:
            paths (Iterable[str]): File paths with forward slashes, relative
                to the folder that holds the items.

        Returns:
            list[tuple[str, str]]: Each item once, in the order first
                touched.
        """
        found: dict[str, str] = {}
        for path in paths:
            item = self._item_of(path)
            if item is not None:
                item_type, item_path = item
                found.setdefault(item_path, item_type)
        return [
            (item_type, item_path) for item_path, item_type in found.items()
        ]

    def _item_of(self, path: str) -> tuple[str, str] | None:
        """Find the item folder a file belongs to, if any."""
        folders = PurePosixPath(path).parts[:-1]
        for depth, name in enumerate(folders, start=1):
            stem, _, item_type = name.rpartition(".")
            if stem and item_type in self._item_types:
                return item_type, "/".join(folders[:depth])
        return None


class GitChangeDetector:
    """
    Find the items that changed in Git between a baseline commit and HEAD.

    Git runs in ``path`` and only reads. The baseline is resolved to a
    commit ID once, so a branch or tag cannot move during the run.

    Args:
        path (str): The folder that holds the items, inside a Git repository.
        baseline_commit (str): The commit to compare HEAD with: a commit ID,
            tag or branch.

    Raises:
        ConfigurationError: If git cannot run, ``path`` is not inside a Git
            repository, or the baseline commit is not in its history.
    """

    def __init__(self, path: str, baseline_commit: str) -> None:
        self._path = path
        if baseline_commit.startswith("-"):
            raise ConfigurationError(f"'{baseline_commit}' is not a commit.")
        self._run(
            "rev-parse",
            "--show-toplevel",
            error=f"{path} is not inside a Git repository.",
        )
        self._baseline = (
            self._run(
                "rev-parse",
                "--verify",
                "--quiet",
                f"{baseline_commit}^{{commit}}",
                error=(
                    f"Commit '{baseline_commit}' is not in the Git history of "
                    f"{path}. A shallow clone may lack it: fetch the history "
                    "that contains it."
                ),
            )
            .decode()
            .strip()
        )

    @property
    def baseline(self) -> str:
        """The ID of the baseline commit."""
        return self._baseline

    def changed_items(self, resolver: ItemResolver) -> list[ItemChange]:
        """
        List the items with changed files between the baseline and HEAD.

        An item folder missing at the baseline was added, one missing at
        HEAD was deleted, and any other was modified, even when all its
        changed files are new.

        Args:
            resolver (ItemResolver): Maps the changed files to item folders.

        Returns:
            list[ItemChange]: Each changed item once, in path order.
        """
        output = self._run(
            "diff",
            "--name-only",
            "-z",
            "--no-renames",
            "--relative",
            self._baseline,
            "HEAD",
            "--",
            ".",
            error=f"Could not compare commit {self._baseline} with HEAD.",
        )
        paths = [path for path in output.decode("utf-8").split("\0") if path]
        return [
            ItemChange(item_type, item_path, self._classify(item_path))
            for item_type, item_path in resolver.resolve(paths)
        ]

    def read_baseline_file(self, path: str) -> bytes:
        """
        Read a file as it was at the baseline commit.

        Args:
            path (str): The file, relative to the compared folder.

        Returns:
            bytes: The file content.

        Raises:
            ConfigurationError: If the file did not exist at the baseline.
        """
        return self._run(
            "cat-file",
            "blob",
            f"{self._baseline}:./{path}",
            error=f"{path} does not exist at commit {self._baseline[:12]}.",
        )

    def _classify(self, item_path: str) -> SourceChange:
        """Tell whether an item folder was added, modified or deleted."""
        at_baseline = self._exists(self._baseline, item_path)
        at_head = self._exists("HEAD", item_path)
        if at_baseline and at_head:
            return SourceChange.MODIFIED
        return SourceChange.ADDED if at_head else SourceChange.DELETED

    def _exists(self, commit: str, path: str) -> bool:
        """Tell whether a path exists at a commit."""
        found = self._git(
            "rev-parse", "--verify", "--quiet", f"{commit}:./{path}"
        )
        return found.returncode == 0

    def _run(self, *args: str, error: str) -> bytes:
        """Run git and return its output, or raise ``error`` on failure."""
        result = self._git(*args)
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise ConfigurationError(f"{error} {detail}".strip())
        return result.stdout

    def _git(self, *args: str) -> subprocess.CompletedProcess[bytes]:
        """Run git in the compared folder, capturing its output."""
        try:
            return subprocess.run(
                ["git", "-C", self._path, *args],
                capture_output=True,
                check=False,
            )
        except FileNotFoundError as e:
            raise ConfigurationError(
                "git was not found; selective deployment needs git on PATH."
            ) from e
        except OSError as e:
            raise ConfigurationError(f"Could not run git: {e}") from e
