"""Tests for the Git change detection in pyfabricops.helpers.source_changes."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from pyfabricops.helpers.deployment_plan import SourceChange
from pyfabricops.helpers.source_changes import (
    GitChangeDetector,
    ItemChange,
    ItemResolver,
)
from pyfabricops.utils.exceptions import ConfigurationError
from tests.helpers.git_repo import GitRepo

ADDED = SourceChange.ADDED
MODIFIED = SourceChange.MODIFIED
DELETED = SourceChange.DELETED

_TYPES = ("Lakehouse", "Notebook", "SemanticModel", "Report")


def _write_item(root: Path, relative: str) -> Path:
    """Create an item folder with a .platform and one content file."""
    item_dir = root / relative
    item_dir.mkdir(parents=True)
    name, item_type = item_dir.name.rsplit(".", 1)
    platform = {"metadata": {"type": item_type, "displayName": name}}
    (item_dir / ".platform").write_text(json.dumps(platform), encoding="utf-8")
    (item_dir / "content.txt").write_text("content", encoding="utf-8")
    return item_dir


@pytest.fixture()
def workspace(git_repo: GitRepo) -> Path:
    """The folder that holds the items, inside the repository."""
    path = git_repo.root / "workspace"
    path.mkdir()
    return path


def _changes(workspace: Path, baseline: str) -> list[ItemChange]:
    detector = GitChangeDetector(str(workspace), baseline)
    return detector.changed_items(ItemResolver(_TYPES))


# ---------------------------------------------------------------------------
# Files to items
# ---------------------------------------------------------------------------


def test_files_of_one_item_give_the_item_once() -> None:
    """The item folder is the unit of deployment, not the file."""
    items = ItemResolver(_TYPES).resolve(
        [
            "Sales.SemanticModel/definition/model.tmdl",
            "Sales.SemanticModel/.platform",
            "Orders.Notebook/notebook-content.py",
        ]
    )

    assert items == [
        ("SemanticModel", "Sales.SemanticModel"),
        ("Notebook", "Orders.Notebook"),
    ]


def test_an_item_is_found_under_workspace_folders() -> None:
    """Workspace folders are part of the item path."""
    items = ItemResolver(_TYPES).resolve(
        ["Sales/Staging/Orders.Notebook/notebook-content.py"]
    )

    assert items == [("Notebook", "Sales/Staging/Orders.Notebook")]


def test_a_file_belongs_to_the_outermost_item_folder() -> None:
    """A folder named like an item, inside an item, is part of that item."""
    items = ItemResolver(_TYPES).resolve(
        ["Bronze.Lakehouse/Files/archive.Notebook/data.csv"]
    )

    assert items == [("Lakehouse", "Bronze.Lakehouse")]


def test_files_outside_items_or_of_other_types_are_ignored() -> None:
    """Only folders named <name>.<type>, for the types asked, count."""
    items = ItemResolver(["Notebook"]).resolve(
        [
            "README.md",
            "pipelines/deploy.yml",
            "Sales.Report/definition.pbir",
            ".Notebook/hidden.py",
            "Orders.Notebook",
        ]
    )

    assert items == []


# ---------------------------------------------------------------------------
# Changes between commits
# ---------------------------------------------------------------------------


def test_changed_items_are_classified_by_their_folders(
    git_repo: GitRepo, workspace: Path
) -> None:
    """An existing item that only gained files was modified, not added."""
    _write_item(workspace, "Sales/Orders.Notebook")
    _write_item(workspace, "Sales.SemanticModel")
    _write_item(workspace, "Old.Report")
    _write_item(workspace, "Untouched.Notebook")
    baseline = git_repo.commit("baseline")

    (workspace / "Sales/Orders.Notebook/content.txt").write_text(
        "changed", encoding="utf-8"
    )
    (workspace / "Sales.SemanticModel/table.tmdl").write_text(
        "table", encoding="utf-8"
    )
    shutil.rmtree(workspace / "Old.Report")
    _write_item(workspace, "New.Report")
    git_repo.commit("head")

    assert _changes(workspace, baseline) == [
        ItemChange("Report", "New.Report", ADDED),
        ItemChange("Report", "Old.Report", DELETED),
        ItemChange("SemanticModel", "Sales.SemanticModel", MODIFIED),
        ItemChange("Notebook", "Sales/Orders.Notebook", MODIFIED),
    ]


def test_only_the_compared_folder_counts(
    git_repo: GitRepo, workspace: Path
) -> None:
    """Changes elsewhere in the repository are not changes of the items."""
    _write_item(workspace, "Orders.Notebook")
    other = _write_item(git_repo.root / "other", "Orders.Notebook")
    (git_repo.root / "README.md").write_text("v1", encoding="utf-8")
    baseline = git_repo.commit("baseline")

    (other / "content.txt").write_text("changed", encoding="utf-8")
    (git_repo.root / "README.md").write_text("v2", encoding="utf-8")
    git_repo.commit("head")

    assert _changes(workspace, baseline) == []


def test_a_moved_item_is_deleted_there_and_added_here(
    git_repo: GitRepo, workspace: Path
) -> None:
    """A folder move is two item changes; the planner pairs them."""
    _write_item(workspace, "Sales/Orders.Notebook")
    baseline = git_repo.commit("baseline")

    (workspace / "Finance").mkdir()
    (workspace / "Sales/Orders.Notebook").rename(
        workspace / "Finance/Orders.Notebook"
    )
    git_repo.commit("move")

    assert _changes(workspace, baseline) == [
        ItemChange("Notebook", "Finance/Orders.Notebook", ADDED),
        ItemChange("Notebook", "Sales/Orders.Notebook", DELETED),
    ]


def test_a_tag_is_resolved_to_its_commit(
    git_repo: GitRepo, workspace: Path
) -> None:
    """A tag or branch works as the baseline, resolved once."""
    _write_item(workspace, "Orders.Notebook")
    baseline = git_repo.commit("baseline")
    git_repo.run("tag", "deployed")
    _write_item(workspace, "Sales.Report")
    git_repo.commit("head")

    detector = GitChangeDetector(str(workspace), "deployed")

    assert detector.baseline == baseline
    assert detector.changed_items(ItemResolver(_TYPES)) == [
        ItemChange("Report", "Sales.Report", ADDED)
    ]


def test_a_file_is_read_as_it_was_at_the_baseline(
    git_repo: GitRepo, workspace: Path
) -> None:
    """A deleted item keeps the name it had at the baseline."""
    _write_item(workspace, "Old.Report")
    baseline = git_repo.commit("baseline")
    shutil.rmtree(workspace / "Old.Report")
    git_repo.commit("delete")

    detector = GitChangeDetector(str(workspace), baseline)
    platform = json.loads(detector.read_baseline_file("Old.Report/.platform"))

    assert platform["metadata"]["displayName"] == "Old"


def test_a_file_missing_at_the_baseline_is_a_configuration_error(
    git_repo: GitRepo, workspace: Path
) -> None:
    """Reading what the baseline did not have fails clearly."""
    baseline = git_repo.commit("baseline")
    detector = GitChangeDetector(str(workspace), baseline)

    with pytest.raises(ConfigurationError, match="does not exist at commit"):
        detector.read_baseline_file("Nope.Report/.platform")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def test_an_unknown_baseline_is_a_configuration_error(
    git_repo: GitRepo, workspace: Path
) -> None:
    """A shallow clone is the usual cause, so the message says so."""
    git_repo.commit("only")

    with pytest.raises(ConfigurationError, match="shallow clone"):
        GitChangeDetector(str(workspace), "0" * 40)


def test_a_folder_outside_git_is_a_configuration_error(
    tmp_path: Path,
) -> None:
    """Selective deployment needs the items inside a Git repository."""
    if shutil.which("git") is None:
        pytest.skip("git is not installed")

    with pytest.raises(ConfigurationError, match="not inside a Git"):
        GitChangeDetector(str(tmp_path), "HEAD")


def test_an_option_is_not_taken_for_a_commit(
    git_repo: GitRepo, workspace: Path
) -> None:
    """A baseline that looks like a git option never reaches git."""
    with pytest.raises(ConfigurationError, match="is not a commit"):
        GitChangeDetector(str(workspace), "--output=leak.txt")
