"""Tests for items that refer to their workspace by logical ID."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pyfabricops.api.api import ApiResult
from pyfabricops.helpers.dependencies import LocalCatalog, scan_references
from pyfabricops.helpers.deployment import DEPLOY_ORDER
from pyfabricops.helpers.deployment_plan import (
    DeploymentActionType,
    name_problem,
)
from pyfabricops.helpers.items import plan_all_items
from tests.helpers import test_deployment as engine_tests
from tests.helpers.test_deployment import _WORKSPACE_ID, _deploy

# The fixtures of the engine tests: the local root and the patched Fabric.
root = engine_tests.root
fabric = engine_tests.fabric

THIS_WORKSPACE = "00000000-0000-0000-0000-000000000000"
LAKEHOUSE_LOGICAL = "00000000-0000-4000-8000-0000000000f1"
EVENTSTREAM_LOGICAL = "00000000-0000-4000-8000-0000000000f2"
AGENT_LOGICAL = "00000000-0000-4000-8000-0000000000f3"


def _item(
    root: Path,
    relative: str,
    *,
    logical_id: str | None = None,
    files: dict[str, Any] | None = None,
) -> Path:
    """An item folder with a .platform and files, JSON when not text."""
    folder = root / relative
    folder.mkdir(parents=True)
    name, item_type = folder.name.rsplit(".", 1)
    platform: dict[str, Any] = {
        "metadata": {"type": item_type, "displayName": name}
    }
    if logical_id is not None:
        platform["config"] = {"logicalId": logical_id}
    (folder / ".platform").write_text(json.dumps(platform), encoding="utf-8")
    for path, content in (files or {}).items():
        file = folder / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(
            content if isinstance(content, str) else json.dumps(content),
            encoding="utf-8",
        )
    return folder


def _eventstream(root: Path, item_id: str = LAKEHOUSE_LOGICAL) -> Path:
    return _item(
        root,
        "Telemetry.Eventstream",
        logical_id=EVENTSTREAM_LOGICAL,
        files={
            "eventstream.json": {
                "sources": [{"type": "CustomEndpoint", "properties": {}}],
                "destinations": [
                    {
                        "type": "Lakehouse",
                        "properties": {
                            "workspaceId": THIS_WORKSPACE,
                            "itemId": item_id,
                            "deltaTable": "events",
                        },
                    }
                ],
            },
            "eventstreamProperties.json": {"retentionTimeInDays": 1},
        },
    )


def _lakehouse(root: Path) -> Path:
    return _item(root, "Bronze.Lakehouse", logical_id=LAKEHOUSE_LOGICAL)


def _sent(fabric: SimpleNamespace, item_type: str) -> dict[str, Any]:
    """The JSON parts of the definition a create sent for an item type."""
    call = next(
        c
        for c in fabric.create.call_args_list
        if c.kwargs["item_type"] == item_type
    )
    return {
        part["path"]: json.loads(base64.b64decode(part["payload"]))
        for part in call.kwargs["item_definition"]["parts"]
        if part["path"].endswith(".json")
    }


def _created_by_type(
    workspace_id: str, *, item_type: str, **kwargs: Any
) -> ApiResult:
    return ApiResult(True, 201, data={"id": f"{item_type}-id"})


def test_the_new_types_come_after_what_they_read() -> None:
    order = list(DEPLOY_ORDER)
    assert order[-3:] == ["Eventstream", "Ontology", "DataAgent"]
    assert order.index("KQLDatabase") < order.index("Eventstream")


def test_any_logical_id_of_a_local_item_is_a_dependency(
    tmp_path: Path,
) -> None:
    _lakehouse(tmp_path)
    _item(
        tmp_path,
        "Sales.DataAgent",
        logical_id=AGENT_LOGICAL,
        files={
            "Files/Config/draft/lakehouse_tables-Bronze/datasource.json": {
                "artifactId": LAKEHOUSE_LOGICAL.upper(),
                "workspaceId": THIS_WORKSPACE,
            },
            "Files/Config/published/lakehouse_tables-Bronze/datasource.json": {
                "artifactId": LAKEHOUSE_LOGICAL,
            },
            # Itself, and an item outside the source: no dependency.
            "Files/Config/data_agent.json": {
                "self": AGENT_LOGICAL,
                "other": "00000000-0000-4000-8000-0000000000ff",
            },
        },
    )
    catalog = LocalCatalog.read(str(tmp_path), DEPLOY_ORDER)

    scan = scan_references(catalog, [("DataAgent", "Sales")])

    assert [(d.target, d.via) for d in scan.dependencies] == [
        (
            ("Lakehouse", "Bronze"),
            "Files/Config/draft/lakehouse_tables-Bronze/datasource.json "
            "artifactId",
        )
    ]


def test_an_eventstream_is_sent_with_the_ids_of_the_workspace(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Its destination gets the lakehouse's ID and the workspace's."""
    _lakehouse(root)
    eventstream = _eventstream(root)
    on_disk = (eventstream / "eventstream.json").read_text()
    fabric.create.side_effect = _created_by_type

    report = _deploy(root)

    assert [(r.item_type, r.action) for r in report.results] == [
        ("Lakehouse", "created"),
        ("Eventstream", "created"),
    ]
    parts = _sent(fabric, "Eventstream")
    destination = parts["eventstream.json"]["destinations"][0]["properties"]
    assert destination == {
        "workspaceId": _WORKSPACE_ID,
        "itemId": "Lakehouse-id",
        "deltaTable": "events",
    }
    assert parts["eventstreamProperties.json"] == {"retentionTimeInDays": 1}
    assert (eventstream / "eventstream.json").read_text() == on_disk


def test_an_eventstream_brings_its_destination_within_the_run_types(
    root: Path, fabric: SimpleNamespace
) -> None:
    _lakehouse(root)
    _eventstream(root)
    fabric.create.side_effect = _created_by_type

    alone = _deploy(root, item_types=["Eventstream"])
    both = _deploy(root, item_types=["Eventstream", "Lakehouse"])

    assert [(r.item_type, r.action) for r in alone.results] == [
        ("Eventstream", "failed")
    ]
    assert "Needs Bronze.Lakehouse" in (alone.results[0].error or "")
    assert [r.item_type for r in both.results] == ["Lakehouse", "Eventstream"]


def test_a_reference_to_a_local_item_the_workspace_lacks_fails(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Without dependencies, nothing creates the lakehouse first."""
    _lakehouse(root)
    _eventstream(root)

    report = _deploy(
        root, item_types=["Eventstream"], resolve_dependencies=False
    )

    assert report.results[0].action == "failed"
    assert "Bronze.Lakehouse, which the workspace lacks" in (
        report.results[0].error or ""
    )
    fabric.create.assert_not_called()


def test_a_reference_to_an_item_outside_the_source_goes_as_it_is(
    root: Path, fabric: SimpleNamespace
) -> None:
    outside = "00000000-0000-4000-8000-0000000000aa"
    _eventstream(root, item_id=outside)

    report = _deploy(root)

    assert report.ok
    destination = _sent(fabric, "Eventstream")["eventstream.json"][
        "destinations"
    ][0]["properties"]
    assert destination["itemId"] == outside
    # The empty GUID still means this workspace.
    assert destination["workspaceId"] == _WORKSPACE_ID


def test_an_ontology_binding_is_sent_with_the_ids_of_the_workspace(
    root: Path, fabric: SimpleNamespace
) -> None:
    fabric.list_items.return_value = [
        {"id": "lh-1", "type": "Lakehouse", "displayName": "Bronze"},
    ]
    _lakehouse(root)
    _item(
        root,
        "Plant.Ontology",
        files={
            "definition.json": {},
            "EntityTypes/1/DataBindings/b.json": {
                "dataBindingConfiguration": {
                    "sourceTableProperties": {
                        "sourceType": "LakehouseTable",
                        "workspaceId": THIS_WORKSPACE,
                        "itemId": LAKEHOUSE_LOGICAL,
                    }
                }
            },
        },
    )

    report = _deploy(root, item_types=["Ontology"])

    assert [(r.item_type, r.action) for r in report.results] == [
        ("Ontology", "created")
    ]
    binding = _sent(fabric, "Ontology")["EntityTypes/1/DataBindings/b.json"]
    assert binding["dataBindingConfiguration"]["sourceTableProperties"] == {
        "sourceType": "LakehouseTable",
        "workspaceId": _WORKSPACE_ID,
        "itemId": "lh-1",
    }


def test_a_shortcut_database_is_blocked_in_the_plan(
    root: Path, fabric: SimpleNamespace
) -> None:
    _item(
        root,
        "Follower.KQLDatabase",
        files={"DatabaseProperties.json": {"databaseType": "Shortcut"}},
    )

    plan = plan_all_items("Sales-DEV", str(root), start_path=str(root))

    action = plan.actions[0]
    assert action.action is DeploymentActionType.BLOCKED
    assert "databaseType is Shortcut" in (action.detail or "")


def test_an_ontology_name_fabric_refuses_is_named() -> None:
    assert name_problem("Ontology", "Plant_2") is None
    assert "ontology name" in (name_problem("Ontology", "Plant 2") or "")
    assert name_problem("Ontology", "a" * 100) is not None
