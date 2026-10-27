"""Tests for the deployment of eventhouses and their KQL databases."""

from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from pyfabricops.api.api import ApiResult
from pyfabricops.helpers.deployment import DEPLOY_ORDER
from tests.helpers import test_deployment as engine_tests
from tests.helpers.test_deployment import (
    _WORKSPACE_ID,
    _deploy,
    _failure,
    _write_item,
)

# The fixtures of the engine tests: the local root and the patched Fabric.
root = engine_tests.root
fabric = engine_tests.fabric

_EVENTHOUSE_LOGICAL = "00000000-0000-4000-8000-0000000000e1"
_DEFAULT_DATABASE = {
    "id": "db-1",
    "type": "KQLDatabase",
    "displayName": "Telemetry",
}


def _write_eventhouse(root: Path, folder: str = "") -> tuple[Path, Path]:
    """An eventhouse and its KQL database, nested as Git writes them."""
    eventhouse = root / folder / "Telemetry.Eventhouse"
    database = eventhouse / ".children" / "Telemetry.KQLDatabase"
    database.mkdir(parents=True)
    (eventhouse / ".platform").write_text(
        json.dumps(
            {
                "metadata": {"type": "Eventhouse", "displayName": "Telemetry"},
                "config": {"logicalId": _EVENTHOUSE_LOGICAL},
            }
        ),
        encoding="utf-8",
    )
    (eventhouse / "EventhouseProperties.json").write_text("{}")
    _write_platform(database, "Telemetry")
    _write_database_properties(database, _EVENTHOUSE_LOGICAL)
    return eventhouse, database


def _write_platform(database: Path, name: str) -> None:
    (database / ".platform").write_text(
        json.dumps({"metadata": {"type": "KQLDatabase", "displayName": name}}),
        encoding="utf-8",
    )


def _write_database_properties(database: Path, parent: str) -> None:
    (database / "DatabaseProperties.json").write_text(
        json.dumps(
            {"databaseType": "ReadWrite", "parentEventhouseItemId": parent}
        ),
        encoding="utf-8",
    )


def _created_by_type(
    workspace_id: str,
    *,
    display_name: str,
    item_type: str,
    item_definition: dict[str, Any],
    folder_id: str | None,
) -> ApiResult:
    return ApiResult(True, 201, data={"id": f"{item_type}-id"})


def _parts(definition: dict[str, Any]) -> dict[str, bytes]:
    return {
        part["path"]: base64.b64decode(part["payload"])
        for part in definition["parts"]
    }


def _parent(definition: dict[str, Any]) -> str:
    """The parentEventhouseItemId a KQL database definition was sent with."""
    properties = json.loads(_parts(definition)["DatabaseProperties.json"])
    return str(properties["parentEventhouseItemId"])


def test_eventhouses_come_after_warehouses_and_before_their_databases() -> (
    None
):
    order = list(DEPLOY_ORDER)
    assert (
        order.index("Warehouse")
        < order.index("Eventhouse")
        < order.index("KQLDatabase")
        < order.index("Notebook")
    )


def test_a_kql_database_follows_its_eventhouse_and_is_bound_to_it(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Its folder is the eventhouse's, and it gets the eventhouse's ID."""
    _write_eventhouse(root, "Storage")
    fabric.create.side_effect = _created_by_type

    report = _deploy(root)

    assert [(r.item_type, r.action) for r in report.results] == [
        ("Eventhouse", "created"),
        ("KQLDatabase", "created"),
    ]
    eventhouse_call, database_call = fabric.create.call_args_list
    assert set(_parts(eventhouse_call.kwargs["item_definition"])) == {
        ".platform",
        "EventhouseProperties.json",
    }
    assert database_call.kwargs["folder_id"] == "folder-Storage"
    assert _parent(database_call.kwargs["item_definition"]) == "Eventhouse-id"
    fabric.create_folder.assert_called_once()


def test_the_database_fabric_creates_with_an_eventhouse_is_updated(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Fabric may create the default database: it is updated, not created."""
    _write_eventhouse(root)
    fabric.create.side_effect = _created_by_type
    fabric.list_items.side_effect = [[], [_DEFAULT_DATABASE]]

    report = _deploy(root)

    assert [(r.item_type, r.action, r.item_id) for r in report.results] == [
        ("Eventhouse", "created", "Eventhouse-id"),
        ("KQLDatabase", "updated", "db-1"),
    ]
    assert fabric.create.call_count == 1
    workspace_id, item_id, definition = fabric.update.call_args.args
    assert (workspace_id, item_id) == (_WORKSPACE_ID, "db-1")
    assert _parent(definition) == "Eventhouse-id"


def test_a_database_whose_name_is_taken_late_is_updated(
    root: Path, fabric: SimpleNamespace
) -> None:
    """The default database may appear after the eventhouse is listed."""
    _write_eventhouse(root)
    fabric.list_items.side_effect = [[], [], [_DEFAULT_DATABASE]]
    fabric.create.side_effect = [
        ApiResult(True, 201, data={"id": "eh-1"}),
        _failure("ItemDisplayNameAlreadyInUse"),
    ]

    report = _deploy(root)

    assert [(r.item_type, r.action) for r in report.results] == [
        ("Eventhouse", "created"),
        ("KQLDatabase", "updated"),
    ]
    assert fabric.update.call_args.args[1] == "db-1"


def test_another_item_whose_name_is_taken_still_fails(
    root: Path, fabric: SimpleNamespace
) -> None:
    _write_item(root, "Orders.Notebook")
    fabric.create.return_value = _failure("ItemDisplayNameAlreadyInUse")

    report = _deploy(root)

    assert report.results[0].action == "failed"
    assert fabric.list_items.call_count == 1


def test_a_kql_database_moves_with_its_eventhouse(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Fabric refuses to move a child on its own: only the parent moves."""
    _write_eventhouse(root, "Storage")
    fabric.list_items.return_value = [
        {"id": "eh-1", "type": "Eventhouse", "displayName": "Telemetry"},
        _DEFAULT_DATABASE,
    ]

    report = _deploy(root)

    assert [(r.item_type, r.action, r.moved) for r in report.results] == [
        ("Eventhouse", "updated", True),
        ("KQLDatabase", "updated", True),
    ]
    fabric.move.assert_called_once()
    assert fabric.move.call_args.args[1] == "eh-1"


def test_a_sibling_database_is_bound_by_the_logical_id_of_its_eventhouse(
    root: Path, fabric: SimpleNamespace
) -> None:
    """The layout of older repositories: side by side."""
    _, database = _write_eventhouse(root)
    sibling = root / "Logs.KQLDatabase"
    shutil.move(str(database), str(sibling))
    _write_platform(sibling, "Logs")
    fabric.list_items.return_value = [
        {"id": "eh-1", "type": "Eventhouse", "displayName": "Telemetry"},
    ]

    report = _deploy(root, item_types=["KQLDatabase"])

    assert [(r.display_name, r.action) for r in report.results] == [
        ("Logs", "created")
    ]
    assert _parent(fabric.create.call_args.kwargs["item_definition"]) == (
        "eh-1"
    )


def test_a_database_bound_to_an_eventhouse_of_the_workspace_goes_as_it_is(
    root: Path, fabric: SimpleNamespace
) -> None:
    """A translated copy already holds the ID of the target eventhouse."""
    database = _write_item(root, "Logs.KQLDatabase")
    _write_database_properties(database, "EH-1")
    fabric.list_items.return_value = [
        {"id": "eh-1", "type": "Eventhouse", "displayName": "Telemetry"},
    ]

    report = _deploy(root)

    assert report.ok
    assert _parent(fabric.create.call_args.kwargs["item_definition"]) == (
        "EH-1"
    )


def test_a_database_of_an_unknown_eventhouse_fails(
    root: Path, fabric: SimpleNamespace
) -> None:
    database = _write_item(root, "Logs.KQLDatabase")
    _write_database_properties(
        database, "00000000-0000-4000-8000-00000000dead"
    )

    report = _deploy(root)

    assert report.results[0].action == "failed"
    assert "is no eventhouse of the source or of the workspace" in (
        report.results[0].error or ""
    )
    fabric.create.assert_not_called()


def test_a_database_whose_eventhouse_failed_is_not_deployed(
    root: Path, fabric: SimpleNamespace
) -> None:
    _write_eventhouse(root)
    fabric.create.return_value = _failure("SomethingWrong")

    report = _deploy(root)

    assert [(r.item_type, r.action) for r in report.results] == [
        ("Eventhouse", "failed"),
        ("KQLDatabase", "skipped"),
    ]


def test_each_action_logs_its_start_before_its_outcome(
    root: Path, fabric: SimpleNamespace
) -> None:
    """A create takes a while: the log tells what is going on meanwhile."""
    _write_item(root, "Orders.Notebook")

    with patch("pyfabricops.helpers.deployment.logger") as logger:
        _deploy(root)

    messages = [c.args[0] for c in logger.info.call_args_list]
    start = messages.index("Creating Orders.Notebook...")
    assert any(
        m.startswith("Orders.Notebook created") for m in messages[start + 1 :]
    )
