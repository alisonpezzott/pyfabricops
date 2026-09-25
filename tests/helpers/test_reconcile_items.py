"""Tests for reconcile_items, which compares a workspace with the source."""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from pyfabricops.api.api import ApiResult
from pyfabricops.helpers.content_hash import definition_hash
from pyfabricops.helpers.deployment_plan import DeployedItem
from pyfabricops.helpers.deployment_state import (
    DeploymentState,
    LocalJsonStateBackend,
)
from pyfabricops.helpers.items import reconcile_items
from pyfabricops.helpers.reconciliation import Reconciliation, UnmanagedItem
from pyfabricops.utils.utils import pack_item_definition

_ENGINE = "pyfabricops.helpers.deployment"
_WORKSPACE = "Sales-PRD"
_WORKSPACE_ID = "00000000-0000-0000-0000-0000000000a1"


def _write_item(root: Path, relative: str, content: str = "v1") -> Path:
    """A local item folder with a .platform and one content file."""
    item_dir = root / relative
    item_dir.mkdir(parents=True)
    name, item_type = item_dir.name.rsplit(".", 1)
    platform = {"metadata": {"type": item_type, "displayName": name}}
    (item_dir / ".platform").write_text(json.dumps(platform), encoding="utf-8")
    (item_dir / "content.txt").write_text(content, encoding="utf-8")
    return item_dir


def _served(item_dir: Path, **changes: str) -> ApiResult:
    """The getDefinition answer for a local item, with parts changed."""
    definition = pack_item_definition(str(item_dir))
    for part in definition["parts"]:
        if part["path"] in changes:
            part["payload"] = base64.b64encode(
                changes[part["path"]].encode("utf-8")
            ).decode("ascii")
    return ApiResult(True, 200, data={"definition": definition})


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    """The local root that maps to the workspace root."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


@pytest.fixture()
def fabric() -> Iterator[SimpleNamespace]:
    """A workspace to list and read; anything that would change it fails."""
    workspace = SimpleNamespace(items=[], folders=[], definitions={}, read=[])

    def read(workspace_id: str, item_id: str) -> ApiResult:
        workspace.read.append(item_id)
        result: ApiResult = workspace.definitions[item_id]
        return result

    with (
        patch(f"{_ENGINE}.resolve_workspace", return_value=_WORKSPACE_ID),
        patch(
            f"{_ENGINE}.list_items",
            side_effect=lambda *a, **k: workspace.items,
        ),
        patch(
            f"{_ENGINE}.list_folders",
            side_effect=lambda *a, **k: workspace.folders,
        ),
        patch(f"{_ENGINE}._request_item_definition", side_effect=read),
        patch(f"{_ENGINE}._request_create_item") as create,
        patch(f"{_ENGINE}._request_update_item_definition") as update,
        patch(f"{_ENGINE}._request_move_item") as move,
        patch(f"{_ENGINE}.create_folder") as create_folder,
    ):
        yield workspace
        for mutation in (create, update, move, create_folder):
            mutation.assert_not_called()


def _listed(
    item_id: str, item_type: str, name: str, **extra: Any
) -> dict[str, Any]:
    return {"id": item_id, "type": item_type, "displayName": name, **extra}


def _reconcile(root: Path, **kwargs: Any) -> Reconciliation:
    return reconcile_items(
        _WORKSPACE, str(root), start_path=str(root), **kwargs
    )


def _lines(result: Reconciliation) -> list[tuple[str, str, str, str | None]]:
    return [
        (a.action.value, a.display_name or "", a.reason.value, a.detail)
        for a in result.plan.actions
    ]


def test_a_workspace_that_matches_the_source_is_in_sync(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Each item found on both sides is read once, and matches."""
    orders = _write_item(root, "Orders.Notebook")
    fabric.items = [_listed("nb-1", "Notebook", "Orders")]
    fabric.definitions = {"nb-1": _served(orders)}

    result = _reconcile(root)

    assert result.ok
    assert result.in_sync == (("Notebook", "Orders"),)
    assert fabric.read == ["nb-1"]


def test_a_change_made_in_the_workspace_shows_the_part(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Without a deployment state, a difference counts as drift."""
    orders = _write_item(root, "Orders.Notebook")
    fabric.items = [_listed("nb-1", "Notebook", "Orders")]
    fabric.definitions = {"nb-1": _served(orders, **{"content.txt": "edited"})}

    result = _reconcile(root)

    assert _lines(result) == [
        (
            "UPDATE",
            "Orders",
            "WORKSPACE_DRIFT",
            "Differs from the source: content.txt.",
        )
    ]
    assert not result.ok


def test_an_item_missing_from_the_workspace_would_be_created(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Nothing to read: the workspace does not have it."""
    _write_item(root, "Orders.Notebook")

    result = _reconcile(root)

    assert _lines(result) == [
        (
            "CREATE",
            "Orders",
            "TARGET_MISSING",
            "In the source, not in the workspace.",
        )
    ]
    assert fabric.read == []


def test_items_the_source_lacks_are_unmanaged(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Of any type, but the SQL endpoint that comes with a lakehouse."""
    bronze = _write_item(root, "Bronze.Lakehouse")
    fabric.items = [
        _listed("lh-1", "Lakehouse", "Bronze"),
        _listed("se-1", "SQLEndpoint", "Bronze"),
        _listed("nb-9", "Notebook", "Draft"),
        _listed("kq-1", "KQLDatabase", "Logs"),
    ]
    fabric.definitions = {"lh-1": _served(bronze)}

    result = _reconcile(root)

    assert result.unmanaged == (
        UnmanagedItem("Notebook", "Draft", None, deployable=True),
        UnmanagedItem("KQLDatabase", "Logs", None, deployable=False),
    )


def test_a_report_bound_to_its_model_is_in_sync(
    root: Path, fabric: SimpleNamespace
) -> None:
    """By path in Git, by connection to the model's ID in the workspace."""
    model = _write_item(root, "Sales.SemanticModel")
    report = _write_item(root, "Sales.Report")
    pbir = {
        "version": "4.0",
        "datasetReference": {"byPath": {"path": "../Sales.SemanticModel"}},
    }
    (report / "definition.pbir").write_text(json.dumps(pbir), encoding="utf-8")
    bound = {
        "version": "4.0",
        "datasetReference": {
            "byConnection": {
                "connectionString": "Data Source=powerbi://api.powerbi.com/"
                "v1.0/myorg/Sales-PRD;initial catalog=Sales;integrated "
                "security=ClaimsToken;semanticmodelid=SM-1"
            }
        },
    }
    fabric.items = [
        _listed("sm-1", "SemanticModel", "Sales"),
        _listed("rp-1", "Report", "Sales"),
    ]
    fabric.definitions = {
        "sm-1": _served(model),
        "rp-1": _served(report, **{"definition.pbir": json.dumps(bound)}),
    }

    result = _reconcile(root)

    assert result.ok
    assert set(result.in_sync) == {
        ("SemanticModel", "Sales"),
        ("Report", "Sales"),
    }


def test_a_report_bound_to_another_model_differs(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Someone pointed the report to another model in the workspace."""
    _write_item(root, "Sales.SemanticModel")
    report = _write_item(root, "Sales.Report")
    pbir = {
        "version": "4.0",
        "datasetReference": {"byPath": {"path": "../Sales.SemanticModel"}},
    }
    (report / "definition.pbir").write_text(json.dumps(pbir), encoding="utf-8")
    rebound = {
        "version": "4.0",
        "datasetReference": {
            "byConnection": {"connectionString": "semanticmodelid=fm-1"}
        },
    }
    fabric.items = [
        _listed("sm-1", "SemanticModel", "Sales"),
        _listed("fm-1", "SemanticModel", "Finance"),
        _listed("rp-1", "Report", "Sales"),
    ]
    fabric.definitions = {
        "sm-1": _served(root / "Sales.SemanticModel"),
        "rp-1": _served(report, **{"definition.pbir": json.dumps(rebound)}),
    }

    result = _reconcile(root)

    assert _lines(result) == [
        (
            "UPDATE",
            "Sales",
            "WORKSPACE_DRIFT",
            "Differs from the source: definition.pbir.",
        )
    ]


def test_an_item_whose_definition_cannot_be_read_is_unchecked(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Fabric's reason is kept, and the item is not claimed in sync."""
    _write_item(root, "Bronze.Lakehouse")
    fabric.items = [_listed("lh-1", "Lakehouse", "Bronze")]
    error = {"errorCode": "OperationNotSupportedForItem", "message": "No."}
    fabric.definitions = {
        "lh-1": ApiResult(False, 400, error=json.dumps(error))
    }

    result = _reconcile(root)

    assert dict(result.unchecked) == {
        ("Lakehouse", "Bronze"): "Fabric returned no definition: 400: "
        "OperationNotSupportedForItem - No.."
    }
    assert result.in_sync == ()


@pytest.mark.parametrize(
    ("recorded", "reason", "detail"),
    [
        (
            "source",
            "WORKSPACE_DRIFT",
            "Changed in the workspace since the last deployment: content.txt.",
        ),
        (
            "older",
            "SOURCE_CHANGED",
            "Changed in the source since the last deployment: content.txt.",
        ),
    ],
)
def test_the_deployment_state_tells_where_a_difference_comes_from(
    root: Path,
    fabric: SimpleNamespace,
    tmp_path: Path,
    recorded: str,
    reason: str,
    detail: str,
) -> None:
    """The state's hash is what the last successful deployment sent."""
    orders = _write_item(root, "Orders.Notebook")
    sent = (
        definition_hash(pack_item_definition(str(orders)))
        if recorded == "source"
        else "an-older-hash"
    )
    backend = LocalJsonStateBackend(tmp_path / "state")
    backend.save(
        "prd",
        DeploymentState(
            environment="prd",
            workspace=_WORKSPACE,
            workspace_id=_WORKSPACE_ID,
            source_commit="abc",
            commits={"Notebook": "abc"},
            deployed_at_utc="2026-09-25T12:00:00Z",
            items={("Notebook", "Orders"): DeployedItem(sent)},
        ),
    )
    fabric.items = [_listed("nb-1", "Notebook", "Orders")]
    fabric.definitions = {"nb-1": _served(orders, **{"content.txt": "edited"})}

    result = _reconcile(root, state_backend=backend, environment="prd")

    assert _lines(result) == [("UPDATE", "Orders", reason, detail)]


def test_item_types_limit_the_comparison_not_what_counts_as_source(
    root: Path, fabric: SimpleNamespace
) -> None:
    """The lakehouse is not compared, yet it is not unmanaged either."""
    orders = _write_item(root, "Orders.Notebook")
    _write_item(root, "Bronze.Lakehouse")
    fabric.items = [
        _listed("nb-1", "Notebook", "Orders"),
        _listed("lh-1", "Lakehouse", "Bronze"),
    ]
    fabric.definitions = {"nb-1": _served(orders)}

    result = _reconcile(root, item_types=["Notebook"])

    assert result.ok
    assert fabric.read == ["nb-1"]
    assert result.unmanaged == ()


def test_an_item_in_another_folder_would_be_moved(
    root: Path, fabric: SimpleNamespace
) -> None:
    """The workspace folders are listed once, and named by path."""
    orders = _write_item(root, "Orders.Notebook")
    fabric.folders = [{"id": "f-1", "displayName": "Archive"}]
    fabric.items = [_listed("nb-1", "Notebook", "Orders", folderId="f-1")]
    fabric.definitions = {"nb-1": _served(orders)}

    result = _reconcile(root)

    assert _lines(result) == [
        (
            "MOVE",
            "Orders",
            "WORKSPACE_DRIFT",
            "In 'Archive' in the workspace, the workspace root in the source.",
        )
    ]
