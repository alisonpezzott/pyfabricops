"""Tests for WorkspaceIdMap: the IDs of a source workspace in a target."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pyfabricops.helpers.workspace_ids import (
    THIS_WORKSPACE,
    IdReferences,
    WorkspaceIdMap,
)
from pyfabricops.utils.exceptions import RequestError, ResourceNotFoundError

_MODULE = "pyfabricops.helpers.workspace_ids"

SOURCE = "00000000-0000-4000-8000-0000000000a1"
TARGET = "00000000-0000-4000-8000-0000000000b1"
# The lakehouse and the notebook in the source, by ID and logical ID.
LAKEHOUSE = "00000000-0000-4000-8000-0000000000a2"
LAKEHOUSE_LOGICAL = "00000000-0000-4000-8000-0000000000a3"
NOTEBOOK = "00000000-0000-4000-8000-0000000000a4"
# The same lakehouse and notebook in the target.
TARGET_LAKEHOUSE = "00000000-0000-4000-8000-0000000000b2"
TARGET_LAKEHOUSE_LOGICAL = "00000000-0000-4000-8000-0000000000b3"
TARGET_NOTEBOOK = "00000000-0000-4000-8000-0000000000b4"
# The logical ID of the notebook in its .platform.
NOTEBOOK_LOGICAL = "00000000-0000-4000-8000-0000000000a5"

SOURCE_ITEMS = [
    {
        "type": "Lakehouse",
        "displayName": "bronze",
        "id": LAKEHOUSE,
        "logicalId": LAKEHOUSE_LOGICAL,
    },
    {"type": "Notebook", "displayName": "load", "id": NOTEBOOK},
]
TARGET_LAKEHOUSE_ITEM = {
    "type": "Lakehouse",
    "displayName": "bronze",
    "id": TARGET_LAKEHOUSE,
    "logicalId": TARGET_LAKEHOUSE_LOGICAL,
}
TARGET_NOTEBOOK_ITEM = {
    "type": "Notebook",
    "displayName": "load",
    "id": TARGET_NOTEBOOK,
}


def make_map(
    target_items: list[dict[str, Any]],
    logical_ids: dict[str, tuple[str, str]] | None = None,
) -> WorkspaceIdMap:
    """A map from the source items to the given target items."""
    return WorkspaceIdMap(
        SOURCE,
        TARGET,
        source_items=SOURCE_ITEMS,
        target_items=target_items,
        logical_ids=logical_ids,
    )


def write(path: Path, text: str) -> Path:
    """Write a file, with its folders."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def platform(item_type: str, name: str, logical_id: str) -> str:
    """The text of a .platform file."""
    return json.dumps(
        {
            "metadata": {"type": item_type, "displayName": name},
            "config": {"logicalId": logical_id},
        }
    )


def shortcut(workspace_id: str, item_id: str) -> dict[str, Any]:
    """A OneLake shortcut, as shortcuts.metadata.json holds it."""
    return {
        "name": "raw",
        "path": "/Tables",
        "target": {
            "type": "OneLake",
            "oneLake": {
                "workspaceId": workspace_id,
                "itemId": item_id,
                "path": "Tables/raw",
            },
        },
    }


class TestMapping:
    def test_an_item_the_target_lacks_is_missing(self) -> None:
        ids = make_map([TARGET_LAKEHOUSE_ITEM])

        assert dict(ids.missing) == {NOTEBOOK: ("Notebook", "load")}

    def test_ids_are_compared_in_lowercase(self) -> None:
        ids = WorkspaceIdMap(
            SOURCE.upper(),
            TARGET,
            source_items=[{**SOURCE_ITEMS[1], "id": NOTEBOOK.upper()}],
            target_items=[],
        )

        assert ids.source_workspace_id == SOURCE
        assert dict(ids.missing) == {NOTEBOOK: ("Notebook", "load")}

    def test_logical_ids_of_the_repository_map_too(self) -> None:
        ids = make_map([], {NOTEBOOK_LOGICAL.upper(): ("Notebook", "load")})

        assert ids.missing[NOTEBOOK_LOGICAL] == ("Notebook", "load")

    def test_reload_target_takes_the_items_deployed_since(self) -> None:
        ids = make_map([TARGET_LAKEHOUSE_ITEM])

        with patch(
            f"{_MODULE}.list_items",
            return_value=[TARGET_LAKEHOUSE_ITEM, TARGET_NOTEBOOK_ITEM],
        ) as list_items:
            ids.reload_target()

        list_items.assert_called_once_with(TARGET, df=False)
        assert dict(ids.missing) == {}
        assert ("Notebook", "load") in ids.target_items

    def test_reload_target_raises_when_the_target_cannot_be_listed(
        self,
    ) -> None:
        ids = make_map([])

        with (
            patch(f"{_MODULE}.list_items", return_value=None),
            pytest.raises(RequestError),
        ):
            ids.reload_target()


class TestLoad:
    def test_lists_both_workspaces_and_reads_the_logical_ids(
        self, tmp_path: Path
    ) -> None:
        write(
            tmp_path / "load.Notebook" / ".platform",
            platform("Notebook", "load", NOTEBOOK_LOGICAL),
        )
        listings = {SOURCE: SOURCE_ITEMS, TARGET: [TARGET_NOTEBOOK_ITEM]}

        with (
            patch(
                f"{_MODULE}.resolve_workspace",
                side_effect={"DEV": SOURCE, "PRD": TARGET}.get,
            ),
            patch(
                f"{_MODULE}.list_items",
                side_effect=lambda workspace, df: listings[workspace],
            ),
        ):
            ids = WorkspaceIdMap.load("DEV", "PRD", tmp_path)

        assert ids.target_workspace_id == TARGET
        assert set(ids.missing) == {LAKEHOUSE, LAKEHOUSE_LOGICAL}
        write(tmp_path / "load.Notebook" / "x.py", NOTEBOOK_LOGICAL)
        ids.translate(tmp_path)
        assert (tmp_path / "load.Notebook" / "x.py").read_text(
            encoding="utf-8"
        ) == TARGET_NOTEBOOK

    def test_raises_when_a_workspace_is_not_found(self) -> None:
        with (
            patch(f"{_MODULE}.resolve_workspace", return_value=None),
            pytest.raises(ResourceNotFoundError, match="DEV"),
        ):
            WorkspaceIdMap.load("DEV", "PRD")


class TestTranslate:
    def test_ids_of_the_source_get_those_of_the_target(
        self, tmp_path: Path
    ) -> None:
        content = write(
            tmp_path / "load.Notebook" / "notebook-content.py",
            f'# "default_lakehouse": "{LAKEHOUSE_LOGICAL}",\n'
            f'# "default_lakehouse_workspace_id": "{SOURCE.upper()}",\n'
            f'# "known_lakehouses": [{{"id": "{LAKEHOUSE}"}}]\n',
        )

        make_map([TARGET_LAKEHOUSE_ITEM]).translate(tmp_path)

        assert content.read_text(encoding="utf-8") == (
            f'# "default_lakehouse": "{TARGET_LAKEHOUSE}",\n'
            f'# "default_lakehouse_workspace_id": "{TARGET}",\n'
            f'# "known_lakehouses": [{{"id": "{TARGET_LAKEHOUSE}"}}]\n'
        )

    def test_the_empty_workspace_of_a_pipeline_gets_the_target(
        self, tmp_path: Path
    ) -> None:
        content = write(
            tmp_path / "run.DataPipeline" / "pipeline-content.json",
            f'{{"workspaceId": "{THIS_WORKSPACE}", "id": "{NOTEBOOK}"}}',
        )

        make_map([TARGET_NOTEBOOK_ITEM]).translate(tmp_path)

        assert content.read_text(encoding="utf-8") == (
            f'{{"workspaceId": "{TARGET}", "id": "{TARGET_NOTEBOOK}"}}'
        )

    def test_the_empty_workspace_elsewhere_stays(self, tmp_path: Path) -> None:
        text = f'{{"workspaceId": "{THIS_WORKSPACE}"}}'
        content = write(tmp_path / "m.SemanticModel" / "x.json", text)

        make_map([]).translate(tmp_path)

        assert content.read_text(encoding="utf-8") == text

    def test_platform_and_variable_libraries_stay(
        self, tmp_path: Path
    ) -> None:
        text = platform("Notebook", "load", NOTEBOOK)
        files = [
            write(tmp_path / "load.Notebook" / ".platform", text),
            write(
                tmp_path / "v.VariableLibrary" / "valueSets" / "PRD.json",
                text,
            ),
        ]

        make_map([TARGET_NOTEBOOK_ITEM]).translate(tmp_path)

        assert [f.read_text(encoding="utf-8") for f in files] == [text, text]

    def test_an_id_the_target_lacks_stays(self, tmp_path: Path) -> None:
        content = write(tmp_path / "load.Notebook" / "x.py", NOTEBOOK)

        make_map([]).translate(tmp_path)

        assert content.read_text(encoding="utf-8") == NOTEBOOK


class TestShortcuts:
    def file(self, tmp_path: Path, *shortcuts: dict[str, Any]) -> Path:
        return write(
            tmp_path / "silver.Lakehouse" / "shortcuts.metadata.json",
            json.dumps(list(shortcuts)),
        )

    def one_lake(self, file: Path) -> list[dict[str, Any]]:
        return [
            s["target"]["oneLake"]
            for s in json.loads(file.read_text(encoding="utf-8"))
        ]

    def test_a_shortcut_gets_the_logical_id_in_the_target(
        self, tmp_path: Path
    ) -> None:
        file = self.file(tmp_path, shortcut(THIS_WORKSPACE, LAKEHOUSE_LOGICAL))

        make_map([TARGET_LAKEHOUSE_ITEM]).translate(tmp_path)

        assert self.one_lake(file)[0] == {
            "workspaceId": THIS_WORKSPACE,
            "itemId": TARGET_LAKEHOUSE_LOGICAL,
            "path": "Tables/raw",
        }

    def test_without_a_logical_id_it_gets_the_id_and_the_target(
        self, tmp_path: Path
    ) -> None:
        file = self.file(tmp_path, shortcut(SOURCE, LAKEHOUSE))
        item = {**TARGET_LAKEHOUSE_ITEM, "logicalId": None}

        make_map([item]).translate(tmp_path)

        assert self.one_lake(file)[0]["workspaceId"] == TARGET
        assert self.one_lake(file)[0]["itemId"] == TARGET_LAKEHOUSE

    def test_a_shortcut_to_another_workspace_stays(
        self, tmp_path: Path
    ) -> None:
        other = "00000000-0000-4000-8000-0000000000c1"
        file = self.file(tmp_path, shortcut(other, LAKEHOUSE))

        make_map([TARGET_LAKEHOUSE_ITEM]).translate(tmp_path)

        assert self.one_lake(file)[0]["workspaceId"] == other
        assert self.one_lake(file)[0]["itemId"] == LAKEHOUSE

    def test_a_shortcut_waits_for_its_item(self, tmp_path: Path) -> None:
        file = self.file(tmp_path, shortcut(THIS_WORKSPACE, LAKEHOUSE))
        ids = make_map([])

        ids.translate(tmp_path)
        assert self.one_lake(file)[0]["itemId"] == LAKEHOUSE

        with patch(
            f"{_MODULE}.list_items", return_value=[TARGET_LAKEHOUSE_ITEM]
        ):
            ids.reload_target()
        ids.translate(tmp_path)
        assert self.one_lake(file)[0]["itemId"] == TARGET_LAKEHOUSE_LOGICAL

    def test_point_shortcut_leaves_its_argument_alone(self) -> None:
        original = shortcut(THIS_WORKSPACE, LAKEHOUSE)

        pointed = make_map([TARGET_LAKEHOUSE_ITEM]).point_shortcut(original)

        assert original["target"]["oneLake"]["itemId"] == LAKEHOUSE
        assert (
            pointed["target"]["oneLake"]["itemId"] == TARGET_LAKEHOUSE_LOGICAL
        )


class TestReferences:
    def test_an_item_refers_to_what_the_target_lacks(
        self, tmp_path: Path
    ) -> None:
        folder = tmp_path / "run.DataPipeline"
        write(folder / "pipeline-content.json", f'"{NOTEBOOK.upper()}"')

        found = make_map([]).references(("DataPipeline", "run"), folder)

        assert found == IdReferences(
            frozenset({("Notebook", "load")}), source_workspace=False
        )
        assert not found.ok

    def test_an_item_refers_to_the_source_workspace(
        self, tmp_path: Path
    ) -> None:
        folder = tmp_path / "load.Notebook"
        write(folder / "notebook-content.py", SOURCE)

        found = make_map([]).references(("Notebook", "load"), folder)

        assert found.source_workspace

    def test_an_item_does_not_refer_to_itself(self, tmp_path: Path) -> None:
        folder = tmp_path / "load.Notebook"
        write(folder / "notebook-content.py", NOTEBOOK)

        assert make_map([]).references(("Notebook", "load"), folder).ok

    def test_platform_and_variable_libraries_refer_to_nothing(
        self, tmp_path: Path
    ) -> None:
        notebook = tmp_path / "x.Notebook"
        write(notebook / ".platform", NOTEBOOK)
        library = tmp_path / "v.VariableLibrary"
        write(library / "valueSets" / "DEV.json", f"{SOURCE} {NOTEBOOK}")
        ids = make_map([])

        assert ids.references(("Notebook", "x"), notebook).ok
        assert ids.references(("VariableLibrary", "v"), library).ok

    def test_after_translation_nothing_is_left(self, tmp_path: Path) -> None:
        folder = tmp_path / "run.DataPipeline"
        write(
            folder / "pipeline-content.json",
            f'{{"workspaceId": "{SOURCE}", "id": "{NOTEBOOK}"}}',
        )
        ids = make_map([TARGET_NOTEBOOK_ITEM])

        ids.translate(tmp_path)

        assert ids.references(("DataPipeline", "run"), folder).ok
