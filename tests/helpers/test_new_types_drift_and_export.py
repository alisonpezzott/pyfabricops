"""Tests for reconciling and exporting the item types added for RTI and IQ."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from pyfabricops.api.api import ApiResult
from pyfabricops.helpers.drift import comparable_parts
from pyfabricops.helpers.items import export_all_items, export_item
from tests.helpers import test_reconcile_items as reconcile_tests
from tests.helpers.test_reconcile_items import (
    _WORKSPACE_ID,
    _listed,
    _reconcile,
)

# The fixtures of the reconcile tests: the local root and the workspace.
root = reconcile_tests.root
fabric = reconcile_tests.fabric

THIS_WORKSPACE = "00000000-0000-0000-0000-000000000000"
EVENTHOUSE_LOGICAL = "00000000-0000-4000-8000-0000000000e1"
EVENTHOUSE_ID = "00000000-0000-4000-8000-0000000000e2"
DATABASE_ID = "00000000-0000-4000-8000-0000000000e3"


def _encode(content: Any) -> str:
    text = content if isinstance(content, str) else json.dumps(content)
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _definition(parts: dict[str, Any]) -> dict[str, Any]:
    return {
        "parts": [
            {"path": path, "payload": _encode(content)}
            for path, content in parts.items()
        ]
    }


def _write(folder: Path, files: dict[str, Any], **platform: Any) -> Path:
    folder.mkdir(parents=True)
    name, item_type = folder.name.rsplit(".", 1)
    (folder / ".platform").write_text(
        json.dumps(
            {"metadata": {"type": item_type, "displayName": name}, **platform}
        )
    )
    for path, content in files.items():
        file = folder / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(
            content if isinstance(content, str) else json.dumps(content)
        )
    return folder


def _eventhouse(root: Path) -> None:
    eventhouse = _write(
        root / "Telemetry.Eventhouse",
        {"EventhouseProperties.json": {}},
        config={"logicalId": EVENTHOUSE_LOGICAL},
    )
    _write(
        eventhouse / ".children" / "Telemetry.KQLDatabase",
        {
            "DatabaseProperties.json": {
                "databaseType": "ReadWrite",
                "parentEventhouseItemId": EVENTHOUSE_LOGICAL,
            },
            "DatabaseSchema.kql": ".create-merge table Events (id:string)",
        },
    )


def _served(definition: dict[str, Any]) -> ApiResult:
    return ApiResult(True, 200, data={"definition": definition})


def test_a_kql_database_is_compared_as_it_would_be_sent(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Its eventhouse by ID, and not what the database holds, is in sync."""
    _eventhouse(root)
    fabric.items = [
        _listed(EVENTHOUSE_ID, "Eventhouse", "Telemetry"),
        _listed(DATABASE_ID, "KQLDatabase", "Telemetry"),
    ]
    fabric.definitions = {
        EVENTHOUSE_ID: _served(_definition({"EventhouseProperties.json": {}})),
        DATABASE_ID: _served(
            _definition(
                {
                    "DatabaseProperties.json": {
                        "databaseType": "ReadWrite",
                        "parentEventhouseItemId": EVENTHOUSE_ID,
                    },
                    # The whole schema, with a table ingestion created.
                    "DatabaseSchema.kql": ".create-merge table Events "
                    "(id:string)\n.create-merge table Raw (x:dynamic)",
                    "EmbeddedRealTimeQueryset.json": {"queryset": {}},
                }
            )
        ),
    }

    result = _reconcile(root)

    assert result.ok
    assert set(result.in_sync) == {
        ("Eventhouse", "Telemetry"),
        ("KQLDatabase", "Telemetry"),
    }


def _eventstream(root: Path) -> None:
    _write(
        root / "Bronze.Lakehouse", {}, config={"logicalId": EVENTHOUSE_LOGICAL}
    )
    _write(
        root / "Telemetry.Eventstream",
        {
            "eventstream.json": {
                "destinations": [
                    {
                        "properties": {
                            "workspaceId": THIS_WORKSPACE,
                            "itemId": EVENTHOUSE_LOGICAL,
                        }
                    }
                ]
            }
        },
    )


def _served_eventstream(item_id: str) -> ApiResult:
    return _served(
        _definition(
            {
                "eventstream.json": {
                    "destinations": [
                        {
                            "properties": {
                                "workspaceId": _WORKSPACE_ID,
                                "itemId": item_id,
                            }
                        }
                    ]
                }
            }
        )
    )


def test_an_eventstream_bound_to_the_workspace_is_in_sync(
    root: Path, fabric: SimpleNamespace
) -> None:
    _eventstream(root)
    fabric.items = [
        _listed("lh-1", "Lakehouse", "Bronze"),
        _listed("es-1", "Eventstream", "Telemetry"),
    ]
    fabric.definitions = {
        "lh-1": _served(_definition({})),
        "es-1": _served_eventstream("lh-1"),
    }

    result = _reconcile(root, item_types=["Eventstream"])

    assert result.ok
    assert list(result.in_sync) == [("Eventstream", "Telemetry")]


def test_an_eventstream_pointed_elsewhere_drifted(
    root: Path, fabric: SimpleNamespace
) -> None:
    _eventstream(root)
    fabric.items = [
        _listed("lh-1", "Lakehouse", "Bronze"),
        _listed("es-1", "Eventstream", "Telemetry"),
    ]
    fabric.definitions = {"es-1": _served_eventstream("lh-other")}

    result = _reconcile(root, item_types=["Eventstream"])

    assert [a.display_name for a in result.plan.actions] == ["Telemetry"]
    assert "eventstream.json" in (result.plan.actions[0].detail or "")


def test_the_refs_of_an_ontology_model_are_not_compared() -> None:
    source = comparable_parts(
        _definition({"model.tmdl": "model Model\n\nref table A\n"})
    )
    served = comparable_parts(
        _definition({"model.tmdl": "model Model\n\nref table B\nref x C\n"})
    )

    assert source == served


_ITEMS = "pyfabricops.helpers.items"


def _database_definition(parent: str) -> dict[str, Any]:
    return {
        "definition": _definition(
            {"DatabaseProperties.json": {"parentEventhouseItemId": parent}}
        )
    }


def test_export_puts_a_database_in_its_eventhouse(tmp_path: Path) -> None:
    """Listed before its eventhouse, it still goes into its .children."""
    items = [
        _listed(DATABASE_ID, "KQLDatabase", "Logs"),
        _listed(EVENTHOUSE_ID, "Eventhouse", "Telemetry", folderId="f-1"),
    ]
    definitions = {
        DATABASE_ID: _database_definition(EVENTHOUSE_ID),
        EVENTHOUSE_ID: {"definition": _definition({"x.json": {}})},
    }
    with (
        patch(f"{_ITEMS}.resolve_workspace", return_value=_WORKSPACE_ID),
        patch(f"{_ITEMS}.list_items", return_value=items),
        patch(
            f"{_ITEMS}.get_item",
            side_effect=lambda w, i, df: next(
                x for x in items if x["id"] == i
            ),
        ),
        patch(
            f"{_ITEMS}.get_item_definition",
            side_effect=lambda w, i: definitions[i],
        ),
        patch(f"{_ITEMS}.resolve_folder_from_id_to_path", return_value="RTI"),
    ):
        export_all_items("Sales-DEV", str(tmp_path))

    eventhouse = tmp_path / "RTI" / "Telemetry.Eventhouse"
    assert (eventhouse / "x.json").exists()
    assert (
        eventhouse
        / ".children"
        / "Logs.KQLDatabase"
        / "DatabaseProperties.json"
    ).exists()
    assert not (tmp_path / "RTI" / "Logs.KQLDatabase").exists()


def test_export_item_puts_a_database_in_its_eventhouse(tmp_path: Path) -> None:
    items = {
        "Logs": _listed(DATABASE_ID, "KQLDatabase", "Logs"),
        EVENTHOUSE_ID: _listed(EVENTHOUSE_ID, "Eventhouse", "Telemetry"),
    }
    with (
        patch(f"{_ITEMS}.resolve_workspace", return_value=_WORKSPACE_ID),
        patch(f"{_ITEMS}.get_item", side_effect=lambda w, i, df: items[i]),
        patch(
            f"{_ITEMS}.get_item_definition",
            return_value=_database_definition(EVENTHOUSE_ID),
        ),
    ):
        export_item("Sales-DEV", "Logs", str(tmp_path))

    assert (
        tmp_path
        / "Telemetry.Eventhouse"
        / ".children"
        / "Logs.KQLDatabase"
        / "DatabaseProperties.json"
    ).exists()


def test_export_keeps_a_database_whose_eventhouse_is_unknown(
    tmp_path: Path,
) -> None:
    items = {"Logs": _listed(DATABASE_ID, "KQLDatabase", "Logs")}
    with (
        patch(f"{_ITEMS}.resolve_workspace", return_value=_WORKSPACE_ID),
        patch(f"{_ITEMS}.get_item", side_effect=lambda w, i, df: items.get(i)),
        patch(
            f"{_ITEMS}.get_item_definition",
            return_value=_database_definition(EVENTHOUSE_ID),
        ),
    ):
        export_item("Sales-DEV", "Logs", str(tmp_path))

    assert (tmp_path / "Logs.KQLDatabase" / "DatabaseProperties.json").exists()
