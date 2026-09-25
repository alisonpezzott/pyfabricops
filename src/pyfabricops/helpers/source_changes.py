"""
Source changes: which items changed in Git since a baseline commit.

``ItemResolver`` maps changed files to the item folders they belong to, and
``GitChangeDetector`` asks git which files changed between a baseline commit
and HEAD and whether each changed item was added, modified or deleted.
``head_commit`` and ``has_uncommitted_changes`` tell what a deployment state
records. Everything here only reads. Git runs as a subprocess, so selective
deployment needs git on PATH and the baseline commit in the local history.

Internal for now: nothing here is exported from ``pyfabricops``.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath

from ..helpers.deployment_plan import SourceChange
from ..utils.exceptions import ConfigurationError

__all__ = [
    "GitChangeDetector",
    "ItemChange",
    "ItemResolver",
    "has_uncommitted_changes",
    "head_commit",
]


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
    Find the items that changed in Git between a baseline and a target.

    Git runs in ``path`` and only reads. Both commits are resolved to
    commit IDs once, so a branch or tag cannot move during the run.

    Args:
        path (str): The folder that holds the items, inside a Git repository.
        baseline_commit (str): The commit to compare from: a commit ID, tag
            or branch.
        target_commit (str, optional): The commit to compare to. Defaults to
            ``"HEAD"``.

    Raises:
        ConfigurationError: If git cannot run, ``path`` is not inside a Git
            repository, or a commit is not in its history.
    """

    def __init__(
        self, path: str, baseline_commit: str, target_commit: str = "HEAD"
    ) -> None:
        self._git = _Git(path)
        self._git.check_repository()
        self._baseline = self._git.commit_id(
            baseline_commit,
            error=(
                f"Commit '{baseline_commit}' is not in the Git history of "
                f"{path}. A shallow clone may lack it: fetch the history that "
                "contains it."
            ),
        )
        self._target = self._git.commit_id(
            target_commit,
            error=f"Commit '{target_commit}' is not in the Git history of {path}.",
        )

    @property
    def baseline(self) -> str:
        """The ID of the baseline commit."""
        return self._baseline

    @property
    def target(self) -> str:
        """The ID of the target commit."""
        return self._target

    def changed_items(self, resolver: ItemResolver) -> list[ItemChange]:
        """
        List the items with changed files between the baseline and target.

        An item folder missing at the baseline was added, one missing at the
        target was deleted, and any other was modified, even when all its
        changed files are new.

        Args:
            resolver (ItemResolver): Maps the changed files to item folders.

        Returns:
            list[ItemChange]: Each changed item once, in path order.
        """
        output = self._git.run(
            "diff",
            "--name-only",
            "-z",
            "--no-renames",
            "--relative",
            self._baseline,
            self._target,
            "--",
            ".",
            error=f"Could not compare commit {self._baseline} with {self._target}.",
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
        return self._git.run(
            "cat-file",
            "blob",
            f"{self._baseline}:./{path}",
            error=f"{path} does not exist at commit {self._baseline[:12]}.",
        )

    def _classify(self, item_path: str) -> SourceChange:
        """Tell whether an item folder was added, modified or deleted."""
        at_baseline = self._exists(self._baseline, item_path)
        at_target = self._exists(self._target, item_path)
        if at_baseline and at_target:
            return SourceChange.MODIFIED
        return SourceChange.ADDED if at_target else SourceChange.DELETED

    def _exists(self, commit: str, path: str) -> bool:
        """Tell whether a path exists at a commit."""
        return self._git.succeeds(
            "rev-parse", "--verify", "--quiet", f"{commit}:./{path}"
        )


def head_commit(path: str) -> str:
    """
    Return the ID of the commit HEAD points to, in the repository of a folder.

    Args:
        path (str): A folder inside a Git repository.

    Returns:
        str: The commit ID.

    Raises:
        ConfigurationError: If git cannot run, the folder is not inside a Git
            repository, or the repository has no commit yet.
    """
    git = _Git(path)
    git.check_repository()
    return git.commit_id(
        "HEAD", error=f"The Git repository of {path} has no commit yet."
    )


def has_uncommitted_changes(path: str) -> bool:
    """
    Tell whether a folder has changes that are in no commit.

    Untracked files count: a deployment reads them, but no commit has them.

    Args:
        path (str): A folder inside a Git repository.

    Returns:
        bool: True when ``git status`` lists anything under the folder.

    Raises:
        ConfigurationError: If git cannot run or the folder is not inside a
            Git repository.
    """
    output = _Git(path).run(
        "status",
        "--porcelain",
        "--",
        ".",
        error=f"{path} is not inside a Git repository.",
    )
    return bool(output.strip())


class _Git:
    """Runs git in a folder, only to read."""

    def __init__(self, path: str) -> None:
        self._path = path

    def check_repository(self) -> None:
        """Raise unless the folder is inside a Git repository."""
        self.run(
            "rev-parse",
            "--show-toplevel",
            error=f"{self._path} is not inside a Git repository.",
        )

    def commit_id(self, revision: str, *, error: str) -> str:
        """Resolve a commit ID, tag or branch to the ID of its commit."""
        if revision.startswith("-"):
            raise ConfigurationError(f"'{revision}' is not a commit.")
        output = self.run(
            "rev-parse",
            "--verify",
            "--quiet",
            f"{revision}^{{commit}}",
            error=error,
        )
        return output.decode().strip()

    def run(self, *args: str, error: str) -> bytes:
        """Run git and return its output, or raise ``error`` on failure."""
        result = self._call(*args)
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise ConfigurationError(f"{error} {detail}".strip())
        return result.stdout

    def succeeds(self, *args: str) -> bool:
        """Tell whether git exits without an error."""
        return self._call(*args).returncode == 0

    def _call(self, *args: str) -> subprocess.CompletedProcess[bytes]:
        """Run git in the folder, capturing its output."""
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
