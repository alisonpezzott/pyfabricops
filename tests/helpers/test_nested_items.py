"""Tests for items nested in another, as KQL databases in their eventhouse."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from pyfabricops.helpers.dependencies import LocalCatalog, scan_references
from pyfabricops.helpers.dependency_graph import Dependency
from pyfabricops.helpers.source_changes import ItemResolver
from pyfabricops.helpers.workspace_ids import WorkspaceIdMap
from pyfabricops.utils.utils import (
    extract_middle_path,
    list_paths_of_type,
    pack_item_definition,
    parent_item_folder,
)

EVENTHOUSE_LOGICAL = "00000000-0000-4000-8000-0000000000c1"
DATABASE_ID = "00000000-0000-4000-8000-0000000000c2"


def _write_item(
    folder: Path, *, logical_id: str | None = None, files: dict[str, str]
) -> Path:
    """Create an item folder with a .platform and the given files."""
    folder.mkdir(parents=True)
    name, item_type = folder.name.rsplit(".", 1)
    platform: dict[str, object] = {
        "metadata": {"type": item_type, "displayName": name}
    }
    if logical_id is not None:
        platform["config"] = {"logicalId": logical_id}
    (folder / ".platform").write_text(json.dumps(platform), encoding="utf-8")
    for path, content in files.items():
        (folder / path).write_text(content, encoding="utf-8")
    return folder


def _eventhouse(root: Path, *, parent: str = "") -> tuple[Path, Path]:
    """An eventhouse with its default KQL database, as Git writes them."""
    eventhouse = _write_item(
        root / parent / "Telemetry.Eventhouse",
        logical_id=EVENTHOUSE_LOGICAL,
        files={"EventhouseProperties.json": "{}"},
    )
    database = _write_item(
        eventhouse / ".children" / "Telemetry.KQLDatabase",
        files={
            "DatabaseProperties.json": json.dumps(
                {
                    "databaseType": "ReadWrite",
                    "parentEventhouseItemId": EVENTHOUSE_LOGICAL,
                }
            ),
            "DatabaseSchema.kql": ".create-merge table Events (id:string)",
        },
    )
    return eventhouse, database


def test_nested_items_are_listed(tmp_path: Path) -> None:
    """glob skips hidden folders; .children is looked into anyway."""
    eventhouse, database = _eventhouse(tmp_path, parent="Storage")

    assert list_paths_of_type(tmp_path, "KQLDatabase") == [database.as_posix()]
    assert list_paths_of_type(tmp_path, "Eventhouse") == [
        eventhouse.as_posix()
    ]


def test_a_nested_item_has_the_folder_of_its_parent(tmp_path: Path) -> None:
    eventhouse, database = _eventhouse(tmp_path, parent="Storage/RTI")

    assert parent_item_folder(database) == eventhouse
    assert parent_item_folder(eventhouse) is None
    assert (
        extract_middle_path(str(database), start_path=str(tmp_path))
        == "Storage/RTI"
    )


def test_a_nested_item_at_the_root_has_no_folder(tmp_path: Path) -> None:
    _, database = _eventhouse(tmp_path)

    assert extract_middle_path(str(database), start_path=str(tmp_path)) is None
    assert (
        extract_middle_path("Telemetry.Eventhouse/.children/Logs.KQLDatabase")
        is None
    )


def test_the_definition_of_a_parent_leaves_its_children_out(
    tmp_path: Path,
) -> None:
    eventhouse, _ = _eventhouse(tmp_path)

    paths = [p["path"] for p in pack_item_definition(str(eventhouse))["parts"]]

    assert sorted(paths) == [".platform", "EventhouseProperties.json"]


def test_a_change_in_a_nested_item_belongs_to_it() -> None:
    resolver = ItemResolver(["Eventhouse", "KQLDatabase"])

    assert resolver.resolve(
        [
            "Storage/Telemetry.Eventhouse/.children/Logs.KQLDatabase/"
            "DatabaseSchema.kql",
            "Storage/Telemetry.Eventhouse/EventhouseProperties.json",
        ]
    ) == [
        (
            "KQLDatabase",
            "Storage/Telemetry.Eventhouse/.children/Logs.KQLDatabase",
        ),
        ("Eventhouse", "Storage/Telemetry.Eventhouse"),
    ]


def test_a_change_in_a_nested_item_out_of_scope_is_ignored() -> None:
    """It is no change of the eventhouse, whose definition leaves it out."""
    resolver = ItemResolver(["Eventhouse"])

    assert (
        resolver.resolve(
            ["Telemetry.Eventhouse/.children/Logs.KQLDatabase/x.kql"]
        )
        == []
    )


def test_a_nested_database_needs_its_eventhouse(tmp_path: Path) -> None:
    _eventhouse(tmp_path)
    catalog = LocalCatalog.read(str(tmp_path), ["Eventhouse", "KQLDatabase"])

    scan = scan_references(catalog, [("KQLDatabase", "Telemetry")])

    assert scan.dependencies == (
        Dependency(
            ("KQLDatabase", "Telemetry"),
            ("Eventhouse", "Telemetry"),
            "nested in the eventhouse",
        ),
    )
    assert not scan.broken


def test_a_sibling_database_needs_its_eventhouse_by_logical_id(
    tmp_path: Path,
) -> None:
    """The layout of older repositories: side by side."""
    _write_item(
        tmp_path / "Telemetry.Eventhouse",
        logical_id=EVENTHOUSE_LOGICAL,
        files={"EventhouseProperties.json": "{}"},
    )
    _write_item(
        tmp_path / "Logs.KQLDatabase",
        files={
            "DatabaseProperties.json": json.dumps(
                {"parentEventhouseItemId": EVENTHOUSE_LOGICAL}
            )
        },
    )
    catalog = LocalCatalog.read(str(tmp_path), ["Eventhouse", "KQLDatabase"])

    scan = scan_references(catalog, [("KQLDatabase", "Logs")])

    assert [(d.target, d.via) for d in scan.dependencies] == [
        (("Eventhouse", "Telemetry"), "parentEventhouseItemId")
    ]


def test_a_database_of_an_eventhouse_outside_the_source_needs_nothing(
    tmp_path: Path,
) -> None:
    _write_item(
        tmp_path / "Logs.KQLDatabase",
        files={
            "DatabaseProperties.json": json.dumps(
                {"parentEventhouseItemId": DATABASE_ID}
            )
        },
    )
    catalog = LocalCatalog.read(str(tmp_path), ["Eventhouse", "KQLDatabase"])

    scan = scan_references(catalog, [("KQLDatabase", "Logs")])

    assert scan.dependencies == ()
    assert not scan.broken


def test_the_references_of_a_parent_leave_its_children_out(
    tmp_path: Path,
) -> None:
    """The database refers to itself by ID; the eventhouse does not."""
    eventhouse, database = _eventhouse(tmp_path)
    (database / "EmbeddedRealTimeQueryset.json").write_text(
        json.dumps(
            {"queryset": {"dataSources": [{"databaseItemId": DATABASE_ID}]}}
        ),
        encoding="utf-8",
    )
    ids = WorkspaceIdMap(
        "00000000-0000-4000-8000-0000000000a1",
        "00000000-0000-4000-8000-0000000000b1",
        source_items=[
            {
                "type": "KQLDatabase",
                "displayName": "Telemetry",
                "id": DATABASE_ID,
            }
        ],
        target_items=[],
    )

    assert ids.references(("Eventhouse", "Telemetry"), eventhouse).ok
    assert ids.references(("KQLDatabase", "Telemetry"), database).ok


def test_packing_keeps_a_childrens_folder_deeper_in_an_item(
    tmp_path: Path,
) -> None:
    """Only the .children at the root of an item holds other items."""
    item = _write_item(tmp_path / "Orders.Notebook", files={})
    (item / "resources" / ".children").mkdir(parents=True)
    (item / "resources" / ".children" / "a.txt").write_text("a")

    parts = pack_item_definition(str(item))["parts"]

    assert "resources/.children/a.txt" in [p["path"] for p in parts]
    assert (
        base64.b64decode(
            next(p for p in parts if p["path"].endswith("a.txt"))["payload"]
        )
        == b"a"
    )
