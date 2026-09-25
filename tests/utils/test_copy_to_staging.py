"""Tests for copy_to_staging and the folder it stages into."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pyfabricops.utils import utils
from pyfabricops.utils.utils import copy_to_staging


def _source(root: Path) -> Path:
    """A workspace folder with one item, under root."""
    notebook = root / "workspace" / "A.Notebook"
    notebook.mkdir(parents=True)
    (notebook / "notebook-content.py").write_text("print(1)", encoding="utf-8")
    return root / "workspace"


def test_the_copy_goes_to_the_given_folder(tmp_path: Path) -> None:
    """The copy lands in staging_dir, under the name of the source."""
    source = _source(tmp_path / "repo")
    staging_dir = tmp_path / "run" / "stg"

    staging = Path(copy_to_staging(str(source), staging_dir=str(staging_dir)))

    assert staging == staging_dir / "workspace"
    content = staging / "A.Notebook" / "notebook-content.py"
    assert content.read_text(encoding="utf-8") == "print(1)"


def test_a_second_copy_replaces_the_first(tmp_path: Path) -> None:
    """Nothing left from an earlier copy reaches the next deployment."""
    source = _source(tmp_path / "repo")
    staging_dir = str(tmp_path / "stg")
    stale = Path(copy_to_staging(str(source), staging_dir=staging_dir))
    (stale / "stale.txt").write_text("left over", encoding="utf-8")

    copy_to_staging(str(source), staging_dir=staging_dir)

    assert not (stale / "stale.txt").exists()


def test_a_trailing_separator_stages_under_the_source_name(
    tmp_path: Path,
) -> None:
    """The staging folder itself is not replaced, so its content stays."""
    source = _source(tmp_path / "repo")
    staging_dir = tmp_path / "stg"
    staging_dir.mkdir()
    (staging_dir / "keep.txt").write_text("mine", encoding="utf-8")

    staging = copy_to_staging(
        str(source) + os.sep, staging_dir=str(staging_dir)
    )

    assert Path(staging) == staging_dir / "workspace"
    assert (staging_dir / "keep.txt").exists()


@pytest.mark.parametrize(
    ("source_parent", "staging_dir"),
    [
        pytest.param("repo", "repo", id="onto the source"),
        pytest.param("repo", "repo/workspace/stg", id="inside the source"),
        # The source is <tmp>/workspace/workspace: staging it into <tmp>
        # would replace <tmp>/workspace, which holds it.
        pytest.param("workspace", ".", id="over a folder holding it"),
    ],
)
def test_a_staging_folder_overlapping_the_source_is_refused(
    tmp_path: Path, source_parent: str, staging_dir: str
) -> None:
    """Replacing it would delete the source, or copy it into itself."""
    source = _source(tmp_path / source_parent)

    with pytest.raises(ValueError, match="contain one another"):
        copy_to_staging(str(source), staging_dir=str(tmp_path / staging_dir))

    content = source / "A.Notebook" / "notebook-content.py"
    assert content.read_text(encoding="utf-8") == "print(1)"


def test_the_default_staging_folder_is_unchanged() -> None:
    """Without staging_dir, the copy still goes to _stg in the package."""
    package_stg = os.path.join(os.path.dirname(utils.__file__), "_stg")

    staging = utils._staging_path(os.path.join("repo", "workspace"), None)

    assert staging == os.path.join(package_stg, "workspace")
