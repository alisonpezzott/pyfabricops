"""Tests for restore_items, which brings back what drifted in a workspace."""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pyfabricops.api.api import ApiResult
from pyfabricops.helpers.content_hash import definition_hash
from pyfabricops.helpers.deployment import DeploymentReport
from pyfabricops.helpers.deployment_plan import DeployedItem
from pyfabricops.helpers.deployment_state import (
    DeploymentLock,
    DeploymentState,
    LocalJsonStateBackend,
)
from pyfabricops.helpers.items import restore_items
from pyfabricops.utils.exceptions import DeploymentLockedError
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


def _listed(
    item_id: str, item_type: str, name: str, **extra: Any
) -> dict[str, Any]:
    return {"id": item_id, "type": item_type, "displayName": name, **extra}


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    """The local root that maps to the workspace root."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


@pytest.fixture()
def fabric() -> Iterator[SimpleNamespace]:
    """A workspace to list, read and change, with each change recorded."""
    workspace = SimpleNamespace(items=[], folders=[], definitions={})

    def read(workspace_id: str, item_id: str) -> ApiResult:
        result: ApiResult = workspace.definitions[item_id]
        return result

    def create_folder(
        workspace_id: str,
        name: str,
        *,
        parent_folder: str | None = None,
        df: bool = True,
    ) -> dict[str, Any]:
        return {"id": f"folder-{name}", "parentFolderId": parent_folder}

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
        patch(
            f"{_ENGINE}._request_create_item",
            return_value=ApiResult(True, 201, data={"id": "new-id"}),
        ) as create,
        patch(
            f"{_ENGINE}._request_update_item_definition",
            return_value=ApiResult(True, 200),
        ) as update,
        patch(
            f"{_ENGINE}._request_move_item",
            return_value=ApiResult(True, 200),
        ) as move,
        patch(
            f"{_ENGINE}._request_delete_item",
            return_value=ApiResult(True, 200),
        ) as delete,
        patch(f"{_ENGINE}.create_folder", side_effect=create_folder),
    ):
        workspace.create = create
        workspace.update = update
        workspace.move = move
        workspace.delete = delete
        yield workspace


def _restore(root: Path, **kwargs: Any) -> DeploymentReport:
    return restore_items(_WORKSPACE, str(root), start_path=str(root), **kwargs)


def _outcomes(report: DeploymentReport) -> list[tuple[str | None, str]]:
    return [(r.display_name, r.action) for r in report.results]


def _state_backend(
    folder: Path, items: dict[tuple[str, str], DeployedItem]
) -> LocalJsonStateBackend:
    """A state of the last deployment to prd, recording some items."""
    backend = LocalJsonStateBackend(folder)
    backend.save(
        "prd",
        DeploymentState(
            environment="prd",
            workspace=_WORKSPACE,
            workspace_id=_WORKSPACE_ID,
            source_commit="abc",
            commits={"Notebook": "abc"},
            deployed_at_utc="2026-09-25T12:00:00Z",
            items=items,
        ),
    )
    return backend


def test_an_item_edited_in_the_workspace_is_updated_back(
    root: Path, fabric: SimpleNamespace
) -> None:
    """The source's definition goes back to the workspace item."""
    orders = _write_item(root, "Orders.Notebook")
    fabric.items = [_listed("nb-1", "Notebook", "Orders")]
    fabric.definitions = {"nb-1": _served(orders, **{"content.txt": "edit"})}

    report = _restore(root)

    assert _outcomes(report) == [("Orders", "updated")]
    assert report.ok
    assert fabric.update.call_args.args[:2] == (_WORKSPACE_ID, "nb-1")


def test_an_item_deleted_from_the_workspace_is_created_again(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Deleted by hand, it comes back from the source."""
    _write_item(root, "Orders.Notebook")

    report = _restore(root)

    assert _outcomes(report) == [("Orders", "created")]
    assert fabric.create.call_args.kwargs["display_name"] == "Orders"


def test_an_item_moved_in_the_workspace_is_moved_back(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Its definition matches; only its folder goes back."""
    orders = _write_item(root, "Sales/Orders.Notebook")
    fabric.folders = [
        {"id": "f-sales", "displayName": "Sales"},
        {"id": "f-archive", "displayName": "Archive"},
    ]
    fabric.items = [
        _listed("nb-1", "Notebook", "Orders", folderId="f-archive")
    ]
    fabric.definitions = {"nb-1": _served(orders)}

    report = _restore(root)

    assert _outcomes(report) == [("Orders", "moved")]
    assert fabric.move.call_args.args == (_WORKSPACE_ID, "nb-1", "f-sales")
    fabric.update.assert_not_called()


def test_a_workspace_in_sync_gets_nothing(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Nothing drifted, nothing changes."""
    orders = _write_item(root, "Orders.Notebook")
    fabric.items = [_listed("nb-1", "Notebook", "Orders")]
    fabric.definitions = {"nb-1": _served(orders)}

    report = _restore(root)

    assert report.results == []
    assert report.ok
    fabric.update.assert_not_called()


def test_a_change_in_the_source_is_left_to_the_next_deployment(
    root: Path, fabric: SimpleNamespace, tmp_path: Path
) -> None:
    """Not drift: the deployment pipeline sends it, and records the state."""
    orders = _write_item(root, "Orders.Notebook")
    backend = _state_backend(
        tmp_path / "state", {("Notebook", "Orders"): DeployedItem("older")}
    )
    fabric.items = [_listed("nb-1", "Notebook", "Orders")]
    fabric.definitions = {"nb-1": _served(orders, **{"content.txt": "v0"})}

    with patch(f"{_ENGINE}.logger") as logger:
        report = _restore(root, state_backend=backend, environment="prd")

    assert report.results == []
    fabric.update.assert_not_called()
    logger.info.assert_any_call(
        "Orders.Notebook: changed in the source since the last deployment; "
        "left to the next deployment."
    )


def test_drift_is_told_from_a_pending_deployment_by_the_state(
    root: Path, fabric: SimpleNamespace, tmp_path: Path
) -> None:
    """The source is as deployed, so the workspace drifted: it goes back."""
    orders = _write_item(root, "Orders.Notebook")
    sent = definition_hash(pack_item_definition(str(orders)))
    backend = _state_backend(
        tmp_path / "state", {("Notebook", "Orders"): DeployedItem(sent)}
    )
    fabric.items = [_listed("nb-1", "Notebook", "Orders")]
    fabric.definitions = {"nb-1": _served(orders, **{"content.txt": "edit"})}

    report = _restore(root, state_backend=backend, environment="prd")

    assert _outcomes(report) == [("Orders", "updated")]


def test_an_unmanaged_item_is_never_deleted(
    root: Path, fabric: SimpleNamespace
) -> None:
    """An item only the workspace holds is only reported."""
    orders = _write_item(root, "Orders.Notebook")
    fabric.items = [
        _listed("nb-1", "Notebook", "Orders"),
        _listed("nb-2", "Notebook", "Draft"),
    ]
    fabric.definitions = {"nb-1": _served(orders)}

    report = _restore(root)

    assert report.results == []
    fabric.delete.assert_not_called()


def test_an_item_whose_definition_cannot_be_read_is_left_alone(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Not compared, so there is nothing to tell it drifted."""
    _write_item(root, "Bronze.Lakehouse")
    fabric.items = [_listed("lh-1", "Lakehouse", "Bronze")]
    error = {"errorCode": "OperationNotSupportedForItem", "message": "No."}
    fabric.definitions = {
        "lh-1": ApiResult(False, 400, error=json.dumps(error))
    }

    report = _restore(root)

    assert report.results == []
    fabric.update.assert_not_called()


def test_an_unreadable_local_item_fails_the_restore(
    root: Path, fabric: SimpleNamespace
) -> None:
    """It cannot be brought back, and the report says so."""
    (root / "Broken.Notebook").mkdir()

    report = _restore(root)

    assert [r.action for r in report.results] == ["failed"]
    assert not report.ok


def test_a_report_comes_back_bound_to_its_model(
    root: Path, fabric: SimpleNamespace
) -> None:
    """As a deployment sends it: by connection to the model's ID."""
    model = _write_item(root, "Sales.SemanticModel")
    report_dir = _write_item(root, "Sales.Report")
    pbir = {
        "version": "4.0",
        "datasetReference": {"byPath": {"path": "../Sales.SemanticModel"}},
    }
    (report_dir / "definition.pbir").write_text(
        json.dumps(pbir), encoding="utf-8"
    )
    fabric.items = [_listed("sm-1", "SemanticModel", "Sales")]
    fabric.definitions = {"sm-1": _served(model)}

    report = _restore(root)

    assert _outcomes(report) == [("Sales", "created")]
    sent = fabric.create.call_args.kwargs["item_definition"]
    (part,) = [p for p in sent["parts"] if p["path"] == "definition.pbir"]
    bound = json.loads(base64.b64decode(part["payload"]))
    assert bound["datasetReference"] == {
        "byConnection": {"connectionString": "semanticmodelid=sm-1"}
    }


def test_a_restore_holds_the_lock_and_records_no_state(
    root: Path, fabric: SimpleNamespace, tmp_path: Path
) -> None:
    """It changes the workspace, but what it sends is already recorded."""
    orders = _write_item(root, "Orders.Notebook")
    sent = definition_hash(pack_item_definition(str(orders)))
    backend = _state_backend(
        tmp_path / "state", {("Notebook", "Orders"): DeployedItem(sent)}
    )
    recorded = (tmp_path / "state" / "prd.json").read_bytes()
    fabric.items = [_listed("nb-1", "Notebook", "Orders")]
    fabric.definitions = {"nb-1": _served(orders, **{"content.txt": "edit"})}
    locked = MagicMock(wraps=backend.lock)

    with patch.object(backend, "lock", locked):
        _restore(root, state_backend=backend, environment="prd")

    locked.assert_called_once_with("prd")
    assert (tmp_path / "state" / "prd.json").read_bytes() == recorded
    assert not (tmp_path / "state" / "prd.lock").exists()


def test_a_locked_environment_gets_nothing_restored(
    root: Path, fabric: SimpleNamespace, tmp_path: Path
) -> None:
    """Another run deploys meanwhile: the restore stops before reading."""
    _write_item(root, "Orders.Notebook")
    backend = LocalJsonStateBackend(tmp_path / "state")
    (tmp_path / "state").mkdir()
    lock = DeploymentLock(
        environment="prd",
        lock_id="other-run",
        holder="ci@runner",
        acquired_at_utc="2026-09-25T10:00:00Z",
        expires_at_utc="2999-01-01T00:00:00Z",
    )
    (tmp_path / "state" / "prd.lock").write_text(
        json.dumps(lock.to_dict()), encoding="utf-8"
    )

    with pytest.raises(DeploymentLockedError):
        _restore(root, state_backend=backend, environment="prd")

    fabric.create.assert_not_called()


def test_restore_items_delegates_to_the_engine() -> None:
    """The public function forwards every argument to the engine."""
    backend = MagicMock()
    with patch(
        "pyfabricops.helpers.items._restore_all",
        return_value=MagicMock(spec=DeploymentReport),
    ) as engine:
        restore_items(
            "Sales-PRD",
            "stg",
            "stg",
            item_types=["Notebook"],
            state_backend=backend,
            environment="prd",
        )

    engine.assert_called_once_with(
        "Sales-PRD",
        "stg",
        start_path="stg",
        item_types=["Notebook"],
        state_backend=backend,
        environment="prd",
    )
