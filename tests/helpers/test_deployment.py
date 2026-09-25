"""Tests for the deploy_all_* engine in pyfabricops.helpers.deployment."""

from __future__ import annotations

import base64
import importlib
import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pyfabricops.api.api import ApiResult
from pyfabricops.helpers.content_hash import definition_hash
from pyfabricops.helpers.deployment import (
    DEPLOY_ORDER,
    DeploymentExecutor,
    DeploymentReport,
    DeploymentResult,
    _WorkspaceIndex,
)
from pyfabricops.helpers.deployment_plan import (
    DeploymentAction,
    DeploymentActionType,
    DeploymentPlan,
    DeploymentReason,
)
from pyfabricops.helpers.deployment_state import (
    DeploymentState,
    LocalJsonStateBackend,
)
from pyfabricops.helpers.items import deploy_all_items, plan_all_items
from pyfabricops.utils.exceptions import ConfigurationError, RequestError
from pyfabricops.utils.utils import pack_item_definition
from tests.helpers.git_repo import GitRepo

_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
_ENGINE = "pyfabricops.helpers.deployment"


def _write_item(
    root: Path, relative: str, display_name: str | None = None
) -> Path:
    """Create a local item folder with a .platform and one content file."""
    item_dir = root / relative
    item_dir.mkdir(parents=True)
    name, item_type = item_dir.name.rsplit(".", 1)
    platform = {
        "metadata": {"type": item_type, "displayName": display_name or name}
    }
    (item_dir / ".platform").write_text(json.dumps(platform), encoding="utf-8")
    (item_dir / "content.txt").write_text("content", encoding="utf-8")
    return item_dir


def _failure(error_code: str) -> ApiResult:
    """A failed API result shaped like a Fabric error response."""
    body = {"errorCode": error_code, "message": "Something went wrong."}
    return ApiResult(success=False, status_code=400, error=json.dumps(body))


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    """The local root that maps to the workspace root."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


@pytest.fixture()
def fabric() -> Iterator[SimpleNamespace]:
    """Patch every Fabric call the engine makes."""

    def _create_folder(
        workspace: str,
        name: str,
        *,
        parent_folder: str | None = None,
        df: bool = True,
    ) -> dict[str, Any]:
        return {"id": f"folder-{name}", "parentFolderId": parent_folder}

    with (
        patch(
            f"{_ENGINE}.resolve_workspace", return_value=_WORKSPACE_ID
        ) as resolve_workspace,
        patch(f"{_ENGINE}.list_items", return_value=[]) as list_items,
        patch(f"{_ENGINE}.list_folders", return_value=[]) as list_folders,
        patch(
            f"{_ENGINE}.create_folder", side_effect=_create_folder
        ) as create_folder,
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
    ):
        yield SimpleNamespace(
            resolve_workspace=resolve_workspace,
            list_items=list_items,
            list_folders=list_folders,
            create_folder=create_folder,
            create=create,
            update=update,
            move=move,
        )


def _deploy(root: Path, **kwargs: Any) -> DeploymentReport:
    return deploy_all_items(
        "Sales-DEV", str(root), start_path=str(root), **kwargs
    )


# ---------------------------------------------------------------------------
# Create, update and order
# ---------------------------------------------------------------------------


def test_items_are_deployed_in_dependency_order(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Types follow DEPLOY_ORDER whatever the folder layout."""
    _write_item(root, "Sales.Report")
    _write_item(root, "Sales.SemanticModel")
    _write_item(root, "Orders.Notebook")
    _write_item(root, "Bronze.Lakehouse")

    report = _deploy(root)

    assert [r.item_type for r in report.results] == [
        "Lakehouse",
        "Notebook",
        "SemanticModel",
        "Report",
    ]
    assert report.summary()["created"] == 4
    assert report.ok


def test_create_sends_type_and_display_name(
    root: Path, fabric: SimpleNamespace
) -> None:
    """New items are created with their type, as the API requires."""
    _write_item(root, "Orders.Notebook", display_name="Orders Load")

    report = _deploy(root)

    kwargs = fabric.create.call_args.kwargs
    assert kwargs["item_type"] == "Notebook"
    assert kwargs["display_name"] == "Orders Load"
    assert kwargs["folder_id"] is None
    assert {p["path"] for p in kwargs["item_definition"]["parts"]} == {
        ".platform",
        "content.txt",
    }
    assert report.results[0].item_id == "new-id"


def test_existing_items_are_matched_by_type_and_display_name(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Only the same type and display name counts as the same item."""
    fabric.list_items.return_value = [
        {"id": "nb-1", "type": "Notebook", "displayName": "Orders"},
        {"id": "sm-1", "type": "SemanticModel", "displayName": "Orders"},
    ]
    _write_item(root, "Orders.Notebook")
    _write_item(root, "Orders.Report")

    report = _deploy(root)

    actions = {r.item_type: r.action for r in report.results}
    assert actions == {"Notebook": "updated", "Report": "created"}
    assert fabric.update.call_args.args[:2] == (_WORKSPACE_ID, "nb-1")


def test_workspace_is_listed_once_per_run(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Items and folders are listed once, not once per item."""
    for name in ("A", "B", "C"):
        _write_item(root, f"{name}.Notebook")

    _deploy(root)

    fabric.list_items.assert_called_once_with(_WORKSPACE_ID, df=False)
    fabric.list_folders.assert_called_once_with(_WORKSPACE_ID, df=False)


def test_item_types_filter_keeps_dependency_order(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Only the requested types are deployed, still in dependency order."""
    _write_item(root, "Sales.Report")
    _write_item(root, "Orders.Notebook")
    _write_item(root, "Sales.SemanticModel")

    report = _deploy(root, item_types=["Report", "Notebook"])

    assert [r.item_type for r in report.results] == ["Notebook", "Report"]


def test_a_single_item_type_string_is_accepted(
    root: Path, fabric: SimpleNamespace
) -> None:
    """item_types="Notebook" is not iterated character by character."""
    _write_item(root, "Orders.Notebook")

    report = _deploy(root, item_types="Notebook")

    assert [r.item_type for r in report.results] == ["Notebook"]


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------


def test_missing_folders_are_created_once_and_reused(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Folder paths are created once per run, parents first."""
    _write_item(root, "Sales/Staging/A.Notebook")
    _write_item(root, "Sales/Staging/B.Notebook")

    _deploy(root)

    created = [
        (c.args[1], c.kwargs["parent_folder"])
        for c in fabric.create_folder.call_args_list
    ]
    assert created == [("Sales", None), ("Staging", "folder-Sales")]
    folder_ids = {c.kwargs["folder_id"] for c in fabric.create.call_args_list}
    assert folder_ids == {"folder-Staging"}


def test_existing_folders_are_reused(
    root: Path, fabric: SimpleNamespace
) -> None:
    """A folder path that already exists is not created again."""
    fabric.list_folders.return_value = [
        {"id": "f-sales", "displayName": "Sales"},
        {
            "id": "f-staging",
            "displayName": "Staging",
            "parentFolderId": "f-sales",
        },
    ]
    _write_item(root, "Sales/Staging/A.Notebook")

    _deploy(root)

    fabric.create_folder.assert_not_called()
    assert fabric.create.call_args.kwargs["folder_id"] == "f-staging"


def test_items_are_moved_only_when_the_folder_differs(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Moves happen only for items in another folder, never to the root."""
    fabric.list_folders.return_value = [
        {"id": "f-sales", "displayName": "Sales"},
        {"id": "f-old", "displayName": "Old"},
    ]
    fabric.list_items.return_value = [
        {
            "id": "a",
            "type": "Notebook",
            "displayName": "A",
            "folderId": "f-old",
        },
        {
            "id": "b",
            "type": "Notebook",
            "displayName": "B",
            "folderId": "f-sales",
        },
        {
            "id": "c",
            "type": "Notebook",
            "displayName": "C",
            "folderId": "f-old",
        },
    ]
    _write_item(root, "Sales/A.Notebook")
    _write_item(root, "Sales/B.Notebook")
    _write_item(root, "C.Notebook")

    report = _deploy(root)

    fabric.move.assert_called_once_with(_WORKSPACE_ID, "a", "f-sales")
    assert {r.display_name: r.moved for r in report.results} == {
        "A": True,
        "B": False,
        "C": False,
    }


def test_folder_creation_failure_fails_the_item(
    root: Path, fabric: SimpleNamespace
) -> None:
    """An item whose folder cannot be created is reported as failed."""
    fabric.create_folder.side_effect = None
    fabric.create_folder.return_value = None
    _write_item(root, "Sales/A.Notebook")

    report = _deploy(root)

    assert report.results[0].action == "failed"
    assert "Could not create folder 'Sales'" in (report.results[0].error or "")
    fabric.create.assert_not_called()


# ---------------------------------------------------------------------------
# Failures
# ---------------------------------------------------------------------------


def test_a_failure_does_not_stop_the_run(
    root: Path, fabric: SimpleNamespace
) -> None:
    """The remaining items are still deployed after a failure."""
    fabric.list_items.return_value = [
        {"id": "a", "type": "Notebook", "displayName": "A"},
    ]
    fabric.update.return_value = _failure("InvalidDefinition")
    _write_item(root, "A.Notebook")
    _write_item(root, "B.Notebook")

    report = _deploy(root)

    assert [r.action for r in report.results] == ["failed", "created"]
    assert report.results[0].error == (
        "Update definition failed with 400: InvalidDefinition - "
        "Something went wrong."
    )
    assert report.failed == [report.results[0]]
    assert not report.ok


def test_fail_fast_skips_the_remaining_items(
    root: Path, fabric: SimpleNamespace
) -> None:
    """With fail_fast, items after the first failure are skipped."""
    fabric.create.return_value = _failure("ItemDisplayNameAlreadyInUse")
    _write_item(root, "Bronze.Lakehouse")
    _write_item(root, "A.Notebook")
    _write_item(root, "B.Notebook")

    report = _deploy(root, fail_fast=True)

    assert [r.action for r in report.results] == [
        "failed",
        "skipped",
        "skipped",
    ]
    assert [r.display_name for r in report.skipped] == ["A", "B"]
    assert fabric.create.call_count == 1


def test_duplicate_identity_fails_the_second_item(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Two local folders for the same item would overwrite each other."""
    _write_item(root, "A/Orders.Notebook")
    _write_item(root, "B/Orders.Notebook")

    report = _deploy(root)

    assert [r.action for r in report.results] == ["created", "failed"]
    assert "is also defined at A/Orders.Notebook;" in (
        report.results[1].error or ""
    )
    assert fabric.create.call_count == 1


def test_missing_platform_file_is_reported(
    root: Path, fabric: SimpleNamespace
) -> None:
    """A folder without .platform fails with a clear error."""
    (root / "Broken.Notebook").mkdir()
    _write_item(root, "Orders.Notebook")

    report = _deploy(root)

    broken = next(
        r for r in report.results if r.path.endswith("Broken.Notebook")
    )
    assert broken.action == "failed"
    assert broken.display_name is None
    assert ".platform not found" in (broken.error or "")
    assert report.summary() == {
        "created": 1,
        "updated": 0,
        "moved": 0,
        "failed": 1,
        "skipped": 0,
    }


def test_unknown_workspace_fails_every_item(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Nothing is attempted when the workspace cannot be resolved."""
    fabric.resolve_workspace.return_value = None
    _write_item(root, "A.Notebook")
    _write_item(root, "B.Notebook")

    report = _deploy(root)

    assert [r.action for r in report.results] == ["failed", "failed"]
    assert report.results[0].error == "Workspace 'Sales-DEV' not found."
    fabric.list_items.assert_not_called()


def test_listing_failure_fails_every_item(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Without an item listing, creating items could duplicate them."""
    fabric.list_items.return_value = None
    _write_item(root, "A.Notebook")

    report = _deploy(root)

    assert report.results[0].action == "failed"
    assert "Could not list" in (report.results[0].error or "")
    fabric.create.assert_not_called()


def test_no_local_items_returns_an_empty_report(
    root: Path, fabric: SimpleNamespace
) -> None:
    """An empty path deploys nothing and calls nothing."""
    report = _deploy(root)

    assert report.results == []
    assert report.ok
    fabric.resolve_workspace.assert_not_called()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def test_report_helpers() -> None:
    """summary, durations_by_type and to_df describe the results."""
    report = DeploymentReport(
        workspace="Sales-DEV",
        results=[
            DeploymentResult("Notebook", "A", "a", "created", "1", False, 1.5),
            DeploymentResult("Notebook", "B", "b", "updated", "2", True, 0.5),
            DeploymentResult(
                "SemanticModel", "S", "s", "failed", error="boom"
            ),
        ],
    )

    assert report.summary() == {
        "created": 1,
        "updated": 1,
        "moved": 0,
        "failed": 1,
        "skipped": 0,
    }
    assert report.durations_by_type() == {
        "Notebook": 2.0,
        "SemanticModel": 0.0,
    }
    assert report.duration_seconds == 2.0
    df = report.to_df()
    assert list(df["action"]) == ["created", "updated", "failed"]
    assert list(df.columns)[:4] == [
        "item_type",
        "display_name",
        "path",
        "action",
    ]


def test_empty_report_to_df_keeps_the_columns() -> None:
    """An empty report still has the result columns."""
    df = DeploymentReport(workspace="Sales-DEV").to_df()

    assert df.empty
    assert "duration_seconds" in df.columns


def test_a_moved_item_is_a_success() -> None:
    """Moving is what the plan asked for, so the run is still ok."""
    report = DeploymentReport(
        workspace="Sales-DEV",
        results=[DeploymentResult("Notebook", "A", "a", "moved", moved=True)],
    )

    assert report.ok
    assert report.summary()["moved"] == 1


# ---------------------------------------------------------------------------
# Type-specific helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("module", "function", "item_type"),
    [
        ("notebooks", "deploy_all_notebooks", "Notebook"),
        ("semantic_models", "deploy_all_semantic_models", "SemanticModel"),
        ("reports", "deploy_all_reports", "Report"),
        ("environments", "deploy_all_environments", "Environment"),
        ("data_pipelines", "deploy_all_data_pipelines", "DataPipeline"),
        ("dataflows_gen2", "deploy_all_dataflows_gen2", "Dataflow"),
    ],
)
def test_type_specific_helpers_delegate_to_deploy_all_items(
    module: str, function: str, item_type: str
) -> None:
    """deploy_all_<type> is deploy_all_items scoped to one type."""
    helpers = importlib.import_module(f"pyfabricops.helpers.{module}")
    expected = DeploymentReport(workspace="Sales-DEV")
    with patch.object(
        helpers, "deploy_all_items", return_value=expected
    ) as deploy:
        result = getattr(helpers, function)("Sales-DEV", "src", "src")

    assert result is expected
    deploy.assert_called_once_with(
        "Sales-DEV", "src", "src", item_types=[item_type]
    )


def test_deploy_all_items_delegates_to_the_engine() -> None:
    """The public function forwards every argument to the engine."""
    backend = MagicMock()
    with patch(
        "pyfabricops.helpers.items._deploy_all",
        return_value=MagicMock(spec=DeploymentReport),
    ) as engine:
        deploy_all_items(
            "Sales-DEV",
            "stg",
            "stg",
            item_types=["Notebook"],
            fail_fast=True,
            baseline_commit="abc123",
            repository_path="src",
            state_backend=backend,
            environment="dev",
            resolve_dependencies=False,
        )

    engine.assert_called_once_with(
        "Sales-DEV",
        "stg",
        start_path="stg",
        item_types=["Notebook"],
        fail_fast=True,
        baseline_commit="abc123",
        repository_path="src",
        state_backend=backend,
        environment="dev",
        resolve_dependencies=False,
    )


# ---------------------------------------------------------------------------
# Plan, then apply
# ---------------------------------------------------------------------------


def _planned(
    action: DeploymentActionType,
    item_dir: Path,
    *,
    folder_path: str | None = None,
) -> DeploymentAction:
    """A planned action for an item folder written by _write_item."""
    name, item_type = item_dir.name.rsplit(".", 1)
    return DeploymentAction(
        action=action,
        item_type=item_type,
        display_name=name,
        source_path=str(item_dir),
        reason=DeploymentReason.FULL_DEPLOYMENT,
        folder_path=folder_path,
    )


def _index(
    items: dict[tuple[str, str], dict[str, Any]] | None = None,
    folders: dict[str, str] | None = None,
) -> _WorkspaceIndex:
    """A workspace index with the given items and folders."""
    return _WorkspaceIndex(
        workspace_id=_WORKSPACE_ID, items=items or {}, folders=folders or {}
    )


def _assert_no_change(fabric: SimpleNamespace) -> None:
    """No folder or item was created, updated or moved."""
    for mutation in (
        fabric.create_folder,
        fabric.create,
        fabric.update,
        fabric.move,
    ):
        mutation.assert_not_called()


def test_planning_makes_no_change_to_the_workspace(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Up to the plan the run only reads; every change is the executor's."""
    fabric.list_items.return_value = [
        {"id": "lh-1", "type": "Lakehouse", "displayName": "Bronze"},
    ]
    _write_item(root, "Bronze.Lakehouse")
    _write_item(root, "Sales/Orders.Notebook")
    (root / "Broken.Notebook").mkdir()

    with patch(
        f"{_ENGINE}.DeploymentExecutor.apply", return_value=[]
    ) as apply:
        _deploy(root)

    _assert_no_change(fabric)
    plan = apply.call_args.args[0]
    assert [
        (a.action, a.item_type, a.display_name, a.folder_path)
        for a in plan.actions
    ] == [
        (DeploymentActionType.UPDATE, "Lakehouse", "Bronze", None),
        (DeploymentActionType.BLOCKED, "Notebook", None, None),
        (DeploymentActionType.CREATE, "Notebook", "Orders", "Sales"),
    ]


def test_executor_applies_the_actions_in_plan_order(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Each action goes to the matching Fabric call, in plan order."""
    index = _index({("Notebook", "B"): {"id": "nb-b", "folderId": None}})
    plan = DeploymentPlan(
        actions=[
            _planned(
                DeploymentActionType.CREATE, _write_item(root, "A.Notebook")
            ),
            _planned(
                DeploymentActionType.UPDATE, _write_item(root, "B.Notebook")
            ),
        ]
    )

    results = DeploymentExecutor(index).apply(plan)

    assert [(r.display_name, r.action) for r in results] == [
        ("A", "created"),
        ("B", "updated"),
    ]
    assert fabric.create.call_args.kwargs["display_name"] == "A"
    assert fabric.update.call_args.args[:2] == (_WORKSPACE_ID, "nb-b")


def test_executor_does_what_the_plan_says(
    root: Path, fabric: SimpleNamespace
) -> None:
    """The executor does not decide again: a planned CREATE is created."""
    index = _index({("Notebook", "A"): {"id": "nb-a", "folderId": None}})
    plan = DeploymentPlan(
        actions=[
            _planned(
                DeploymentActionType.CREATE, _write_item(root, "A.Notebook")
            )
        ]
    )

    DeploymentExecutor(index).apply(plan)

    fabric.create.assert_called_once()
    fabric.update.assert_not_called()


def test_blocked_action_fails_without_calling_fabric(
    root: Path, fabric: SimpleNamespace
) -> None:
    """A blocked item is reported as failed with the planner's reason."""
    blocked = DeploymentAction(
        action=DeploymentActionType.BLOCKED,
        item_type="Notebook",
        display_name=None,
        source_path=str(root / "Broken.Notebook"),
        reason=DeploymentReason.FULL_DEPLOYMENT,
        detail="Broken.Notebook/.platform not found.",
    )

    (result,) = DeploymentExecutor(_index()).apply(
        DeploymentPlan(actions=[blocked])
    )

    assert (result.action, result.error) == (
        "failed",
        "Broken.Notebook/.platform not found.",
    )
    _assert_no_change(fabric)


def test_update_missing_from_the_workspace_fails_before_any_change(
    root: Path, fabric: SimpleNamespace
) -> None:
    """A plan that does not match the workspace is not forced onto it."""
    plan = DeploymentPlan(
        actions=[
            _planned(
                DeploymentActionType.UPDATE,
                _write_item(root, "Sales/A.Notebook"),
                folder_path="Sales",
            )
        ]
    )

    (result,) = DeploymentExecutor(_index()).apply(plan)

    assert result.action == "failed"
    assert result.error == (
        "A.Notebook is planned as an update but is not in the workspace."
    )
    _assert_no_change(fabric)


def test_a_move_sends_no_definition(
    root: Path, fabric: SimpleNamespace
) -> None:
    """A MOVE moves the item, to the root too, and updates nothing."""
    index = _index(
        {
            ("Notebook", "A"): {"id": "nb-a", "folderId": None},
            ("Notebook", "B"): {"id": "nb-b", "folderId": "f-sales"},
        },
        folders={"Sales": "f-sales"},
    )
    plan = DeploymentPlan(
        actions=[
            _planned(
                DeploymentActionType.MOVE,
                _write_item(root, "Sales/A.Notebook"),
                folder_path="Sales",
            ),
            _planned(
                DeploymentActionType.MOVE, _write_item(root, "B.Notebook")
            ),
        ]
    )

    results = DeploymentExecutor(index).apply(plan)

    assert [(r.display_name, r.action, r.moved) for r in results] == [
        ("A", "moved", True),
        ("B", "moved", True),
    ]
    assert [c.args for c in fabric.move.call_args_list] == [
        (_WORKSPACE_ID, "nb-a", "f-sales"),
        (_WORKSPACE_ID, "nb-b", None),
    ]
    fabric.update.assert_not_called()


def test_a_move_to_where_the_item_already_is_calls_nothing(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Someone moved it already: the plan is met without a call."""
    index = _index(
        {("Notebook", "A"): {"id": "nb-a", "folderId": "f-sales"}},
        folders={"Sales": "f-sales"},
    )
    plan = DeploymentPlan(
        actions=[
            _planned(
                DeploymentActionType.MOVE,
                _write_item(root, "Sales/A.Notebook"),
                folder_path="Sales",
            )
        ]
    )

    (result,) = DeploymentExecutor(index).apply(plan)

    assert (result.action, result.moved) == ("moved", False)
    _assert_no_change(fabric)


def test_move_missing_from_the_workspace_fails_before_any_change(
    root: Path, fabric: SimpleNamespace
) -> None:
    """Nothing to move: the plan does not match the workspace."""
    plan = DeploymentPlan(
        actions=[
            _planned(
                DeploymentActionType.MOVE,
                _write_item(root, "Sales/A.Notebook"),
                folder_path="Sales",
            )
        ]
    )

    (result,) = DeploymentExecutor(_index()).apply(plan)

    assert result.action == "failed"
    assert result.error == (
        "A.Notebook is planned as a move but is not in the workspace."
    )
    _assert_no_change(fabric)


def test_executor_refuses_to_delete(
    root: Path, fabric: SimpleNamespace
) -> None:
    """No policy allows deletions yet: the item is reported, not deleted."""
    index = _index({("Notebook", "Old"): {"id": "nb-old", "folderId": None}})
    plan = DeploymentPlan(
        actions=[_planned(DeploymentActionType.DELETE, root / "Old.Notebook")]
    )

    (result,) = DeploymentExecutor(index).apply(plan)

    assert result.action == "failed"
    assert result.error == (
        "Deleting items is not supported yet; delete Old.Notebook from the "
        "workspace by hand."
    )
    _assert_no_change(fabric)


def test_noop_actions_get_no_result(
    root: Path, fabric: SimpleNamespace
) -> None:
    """A NOOP calls nothing and is neither reported nor skipped."""
    plan = DeploymentPlan(
        actions=[
            _planned(DeploymentActionType.NOOP, root / "Gone.Notebook"),
            _planned(DeploymentActionType.DELETE, root / "Old.Notebook"),
            _planned(DeploymentActionType.NOOP, root / "Moved.Notebook"),
            _planned(
                DeploymentActionType.CREATE, _write_item(root, "A.Notebook")
            ),
        ]
    )

    results = DeploymentExecutor(_index(), fail_fast=True).apply(plan)

    assert [(r.display_name, r.action) for r in results] == [
        ("Old", "failed"),
        ("A", "skipped"),
    ]


# ---------------------------------------------------------------------------
# Selective deployment: baseline_commit
# ---------------------------------------------------------------------------


def test_selective_deploys_only_what_changed(
    git_repo: GitRepo, root: Path, fabric: SimpleNamespace
) -> None:
    """Unchanged items are left alone; changed ones go as usual."""
    fabric.list_items.return_value = [
        {"id": "nb-a", "type": "Notebook", "displayName": "A"},
        {"id": "nb-b", "type": "Notebook", "displayName": "B"},
    ]
    _write_item(root, "A.Notebook")
    _write_item(root, "B.Notebook")
    baseline = git_repo.commit("baseline")

    (root / "A.Notebook/content.txt").write_text("changed", encoding="utf-8")
    _write_item(root, "Sales/C.Notebook")
    git_repo.commit("head")

    report = _deploy(root, baseline_commit=baseline)

    assert [(r.display_name, r.action) for r in report.results] == [
        ("A", "updated"),
        ("C", "created"),
    ]
    assert fabric.update.call_args.args[:2] == (_WORKSPACE_ID, "nb-a")
    assert fabric.create.call_args.kwargs["folder_id"] == "folder-Sales"


def test_selective_plan_says_why(
    git_repo: GitRepo, root: Path, fabric: SimpleNamespace
) -> None:
    """Each change gets its action and reason; deletions come last."""
    fabric.list_items.return_value = [
        {"id": "nb-a", "type": "Notebook", "displayName": "A"},
        {"id": "rp-old", "type": "Report", "displayName": "Old"},
    ]
    _write_item(root, "A.Notebook")
    _write_item(root, "Old.Report")
    _write_item(root, "Gone.Notebook")
    baseline = git_repo.commit("baseline")

    (root / "A.Notebook/content.txt").write_text("changed", encoding="utf-8")
    _write_item(root, "Sales.Report")
    shutil.rmtree(root / "Old.Report")
    shutil.rmtree(root / "Gone.Notebook")
    git_repo.commit("head")

    with patch(
        f"{_ENGINE}.DeploymentExecutor.apply", return_value=[]
    ) as apply:
        _deploy(root, baseline_commit=baseline)

    _assert_no_change(fabric)
    plan = apply.call_args.args[0]
    assert [
        (a.action, a.item_type, a.display_name, a.reason) for a in plan.actions
    ] == [
        (
            DeploymentActionType.UPDATE,
            "Notebook",
            "A",
            DeploymentReason.SOURCE_CHANGED,
        ),
        (
            DeploymentActionType.CREATE,
            "Report",
            "Sales",
            DeploymentReason.ITEM_ADDED,
        ),
        (
            DeploymentActionType.DELETE,
            "Report",
            "Old",
            DeploymentReason.ITEM_DELETED,
        ),
        (
            DeploymentActionType.NOOP,
            "Notebook",
            "Gone",
            DeploymentReason.ITEM_DELETED,
        ),
    ]


def test_selective_reports_a_deleted_item_still_in_the_workspace(
    git_repo: GitRepo, root: Path, fabric: SimpleNamespace
) -> None:
    """The deletion is refused and fails the run, so it is not missed."""
    fabric.list_items.return_value = [
        {"id": "nb-old", "type": "Notebook", "displayName": "Old"},
    ]
    _write_item(root, "Old.Notebook")
    baseline = git_repo.commit("baseline")
    shutil.rmtree(root / "Old.Notebook")
    git_repo.commit("delete")

    report = _deploy(root, baseline_commit=baseline)

    assert [(r.display_name, r.action) for r in report.results] == [
        ("Old", "failed")
    ]
    assert "delete Old.Notebook from the workspace by hand" in (
        report.results[0].error or ""
    )
    _assert_no_change(fabric)


def test_selective_with_nothing_changed_calls_nothing(
    git_repo: GitRepo, root: Path, fabric: SimpleNamespace
) -> None:
    """No change since the baseline: no call to Fabric at all."""
    _write_item(root, "A.Notebook")
    baseline = git_repo.commit("baseline")

    report = _deploy(root, baseline_commit=baseline)

    assert report.results == []
    fabric.resolve_workspace.assert_not_called()


def test_selective_reads_the_items_from_the_staging_copy(
    git_repo: GitRepo, root: Path, fabric: SimpleNamespace
) -> None:
    """Changes come from the repository; content comes from staging."""
    _write_item(root, "A.Notebook")
    baseline = git_repo.commit("baseline")
    _write_item(root, "Sales/C.Notebook")
    git_repo.commit("head")

    staging = git_repo.root / "_stg" / "workspace"
    shutil.copytree(root, staging)
    (staging / "Sales/C.Notebook/content.txt").write_text(
        "placeholders replaced", encoding="utf-8"
    )

    report = deploy_all_items(
        "Sales-DEV",
        str(staging),
        start_path=str(staging),
        baseline_commit=baseline,
        repository_path=str(root),
    )

    assert [(r.display_name, r.path) for r in report.results] == [
        ("C", (staging / "Sales/C.Notebook").as_posix())
    ]
    kwargs = fabric.create.call_args.kwargs
    assert kwargs["folder_id"] == "folder-Sales"
    content = {
        part["path"]: base64.b64decode(part["payload"]).decode("utf-8")
        for part in kwargs["item_definition"]["parts"]
    }
    assert content["content.txt"] == "placeholders replaced"


def test_selective_with_an_unknown_baseline_raises(
    git_repo: GitRepo, root: Path, fabric: SimpleNamespace
) -> None:
    """A misconfigured baseline stops the run before any Fabric call."""
    _write_item(root, "A.Notebook")
    git_repo.commit("only")

    with pytest.raises(ConfigurationError, match="shallow clone"):
        _deploy(root, baseline_commit="0" * 40)

    fabric.resolve_workspace.assert_not_called()


# ---------------------------------------------------------------------------
# Deployment state: state_backend
# ---------------------------------------------------------------------------


@pytest.fixture()
def state(tmp_path_factory: pytest.TempPathFactory) -> LocalJsonStateBackend:
    """A local state folder, outside the repository."""
    return LocalJsonStateBackend(tmp_path_factory.mktemp("state"))


def _recorded(
    state: LocalJsonStateBackend, environment: str
) -> DeploymentState:
    """The state recorded for an environment, which must exist."""
    recorded = state.load(environment)
    assert recorded is not None
    return recorded


def _change(item_dir: Path, content: str = "changed") -> None:
    """Change the content file of an item written by _write_item."""
    (item_dir / "content.txt").write_text(content, encoding="utf-8")


def test_first_run_deploys_every_item_and_records_head(
    git_repo: GitRepo,
    root: Path,
    fabric: SimpleNamespace,
    state: LocalJsonStateBackend,
) -> None:
    """Without a state the run is full, which bootstraps the state."""
    _write_item(root, "A.Notebook")
    _write_item(root, "Sales.Report")
    head = git_repo.commit("first")

    report = _deploy(root, state_backend=state, environment="dev")

    assert [r.action for r in report.results] == ["created", "created"]
    recorded = _recorded(state, "dev")
    assert recorded.source_commit == head
    assert (recorded.workspace, recorded.workspace_id) == (
        "Sales-DEV",
        _WORKSPACE_ID,
    )
    assert dict(recorded.commits) == dict.fromkeys(DEPLOY_ORDER, head)
    assert recorded.deployed_at_utc.endswith("Z")


def test_the_state_makes_the_next_run_incremental(
    git_repo: GitRepo,
    root: Path,
    fabric: SimpleNamespace,
    state: LocalJsonStateBackend,
) -> None:
    """The next run deploys what changed since the recorded commit."""
    fabric.list_items.return_value = [
        {"id": "nb-a", "type": "Notebook", "displayName": "A"},
        {"id": "nb-b", "type": "Notebook", "displayName": "B"},
    ]
    item = _write_item(root, "A.Notebook")
    _write_item(root, "B.Notebook")
    git_repo.commit("first")
    _deploy(root, state_backend=state, environment="dev")

    _change(item)
    head = git_repo.commit("second")
    report = _deploy(root, state_backend=state, environment="dev")

    assert [(r.display_name, r.action) for r in report.results] == [
        ("A", "updated")
    ]
    assert _recorded(state, "dev").source_commit == head


def test_a_failed_run_leaves_the_state_where_it_was(
    git_repo: GitRepo,
    root: Path,
    fabric: SimpleNamespace,
    state: LocalJsonStateBackend,
) -> None:
    """State A, B fails, repository at C: the next run compares A to C."""
    fabric.list_items.return_value = [
        {"id": "nb-a", "type": "Notebook", "displayName": "A"},
        {"id": "nb-b", "type": "Notebook", "displayName": "B"},
    ]
    a = _write_item(root, "A.Notebook")
    b = _write_item(root, "B.Notebook")
    first = git_repo.commit("A")
    _deploy(root, state_backend=state, environment="dev")

    _change(a)
    git_repo.commit("B")
    fabric.update.return_value = _failure("InvalidDefinition")
    failed = _deploy(root, state_backend=state, environment="dev")
    assert failed.failed
    assert _recorded(state, "dev").source_commit == first

    fabric.update.return_value = ApiResult(True, 200)
    _change(b)
    last = git_repo.commit("C")
    report = _deploy(root, state_backend=state, environment="dev")

    assert [r.display_name for r in report.results] == ["A", "B"]
    assert _recorded(state, "dev").source_commit == last


def test_a_partial_run_advances_only_its_types(
    git_repo: GitRepo,
    root: Path,
    fabric: SimpleNamespace,
    state: LocalJsonStateBackend,
) -> None:
    """Notebooks on every merge do not make the full run lose a Report."""
    fabric.list_items.return_value = [
        {"id": "nb-n", "type": "Notebook", "displayName": "N"},
        {"id": "rp-r", "type": "Report", "displayName": "R"},
    ]
    notebook = _write_item(root, "N.Notebook")
    report_dir = _write_item(root, "R.Report")
    first = git_repo.commit("first")
    _deploy(root, state_backend=state, environment="dev")

    _change(notebook)
    _change(report_dir)
    second = git_repo.commit("second")
    partial = _deploy(
        root, state_backend=state, environment="dev", item_types=["Notebook"]
    )

    assert [r.display_name for r in partial.results] == ["N"]
    commits = _recorded(state, "dev").commits
    assert (commits["Notebook"], commits["Report"]) == (second, first)

    full = _deploy(root, state_backend=state, environment="dev")

    assert [r.display_name for r in full.results] == ["R"]
    assert dict(_recorded(state, "dev").commits) == dict.fromkeys(
        DEPLOY_ORDER, second
    )


def test_a_state_of_another_workspace_is_ignored(
    git_repo: GitRepo,
    root: Path,
    fabric: SimpleNamespace,
    state: LocalJsonStateBackend,
) -> None:
    """Its commits say nothing about this workspace: deploy every item."""
    _write_item(root, "A.Notebook")
    git_repo.commit("first")
    _deploy(root, state_backend=state, environment="shared")

    report = deploy_all_items(
        "Sales-PRD",
        str(root),
        start_path=str(root),
        state_backend=state,
        environment="shared",
    )

    assert [r.display_name for r in report.results] == ["A"]
    assert _recorded(state, "shared").workspace == "Sales-PRD"


def test_an_explicit_baseline_wins_over_the_state(
    git_repo: GitRepo,
    root: Path,
    fabric: SimpleNamespace,
    state: LocalJsonStateBackend,
) -> None:
    """baseline_commit still forces where the comparison starts."""
    b = _write_item(root, "B.Notebook")
    zero = git_repo.commit("B")
    _write_item(root, "A.Notebook")
    git_repo.commit("A")
    _deploy(root, state_backend=state, environment="dev")

    _change(b)
    git_repo.commit("B changed")
    report = _deploy(
        root, state_backend=state, environment="dev", baseline_commit=zero
    )

    assert [r.display_name for r in report.results] == ["A", "B"]


def test_a_run_with_nothing_to_deploy_still_advances_the_state(
    git_repo: GitRepo,
    root: Path,
    fabric: SimpleNamespace,
    state: LocalJsonStateBackend,
) -> None:
    """HEAD is recorded without a Fabric call; the state has the ID."""
    _write_item(root, "A.Notebook")
    git_repo.commit("first")
    _deploy(root, state_backend=state, environment="dev")

    (git_repo.root / "README.md").write_text("docs", encoding="utf-8")
    head = git_repo.commit("docs only")
    fabric.resolve_workspace.reset_mock()
    report = _deploy(root, state_backend=state, environment="dev")

    assert report.results == []
    assert _recorded(state, "dev").source_commit == head
    fabric.resolve_workspace.assert_not_called()


def test_the_environment_defaults_to_the_workspace(
    git_repo: GitRepo,
    root: Path,
    fabric: SimpleNamespace,
    state: LocalJsonStateBackend,
) -> None:
    """Without an environment the state is kept under the workspace."""
    _write_item(root, "A.Notebook")
    git_repo.commit("first")

    _deploy(root, state_backend=state)

    assert _recorded(state, "Sales-DEV").workspace == "Sales-DEV"


def test_uncommitted_changes_are_warned_about(
    git_repo: GitRepo,
    root: Path,
    fabric: SimpleNamespace,
    state: LocalJsonStateBackend,
) -> None:
    """The state records HEAD, which lacks what is not committed."""
    item = _write_item(root, "A.Notebook")
    git_repo.commit("first")
    _change(item, "not committed")

    with patch(f"{_ENGINE}.logger") as logger:
        _deploy(root, state_backend=state, environment="dev")

    warnings = " ".join(str(c.args[0]) for c in logger.warning.call_args_list)
    assert "changes in no commit" in warnings


def test_the_state_needs_the_items_in_a_git_repository(
    root: Path, fabric: SimpleNamespace, state: LocalJsonStateBackend
) -> None:
    """No HEAD to record without Git: stop before any Fabric call."""
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    _write_item(root, "A.Notebook")

    with pytest.raises(ConfigurationError, match="not inside a Git"):
        _deploy(root, state_backend=state, environment="dev")

    fabric.resolve_workspace.assert_not_called()


# ---------------------------------------------------------------------------
# Content hash: what the last successful deployment sent
# ---------------------------------------------------------------------------


def _reformat_platform(item_dir: Path) -> None:
    """Rewrite .platform with another layout and the same content."""
    platform_path = item_dir / ".platform"
    platform = json.loads(platform_path.read_text(encoding="utf-8"))
    platform_path.write_text(json.dumps(platform, indent=4), encoding="utf-8")


def test_an_item_sent_unchanged_is_not_deployed_again(
    git_repo: GitRepo,
    root: Path,
    fabric: SimpleNamespace,
    state: LocalJsonStateBackend,
) -> None:
    """A layout-only change is a candidate in Git, but needs nothing."""
    fabric.list_items.return_value = [
        {"id": "nb-a", "type": "Notebook", "displayName": "A"},
    ]
    item = _write_item(root, "A.Notebook")
    git_repo.commit("first")
    _deploy(root, state_backend=state, environment="dev")

    _reformat_platform(item)
    head = git_repo.commit("reformat")
    fabric.update.reset_mock()
    report = _deploy(root, state_backend=state, environment="dev")

    assert report.results == []
    fabric.update.assert_not_called()
    assert _recorded(state, "dev").source_commit == head


def test_without_a_state_every_candidate_is_deployed(
    git_repo: GitRepo, root: Path, fabric: SimpleNamespace
) -> None:
    """Nothing recorded, nothing to compare: the candidate goes."""
    fabric.list_items.return_value = [
        {"id": "nb-a", "type": "Notebook", "displayName": "A"},
    ]
    item = _write_item(root, "A.Notebook")
    baseline = git_repo.commit("first")
    _reformat_platform(item)
    git_repo.commit("reformat")

    report = _deploy(root, baseline_commit=baseline)

    assert [(r.display_name, r.action) for r in report.results] == [
        ("A", "updated")
    ]


def test_a_moved_item_is_moved_without_its_definition(
    git_repo: GitRepo,
    root: Path,
    fabric: SimpleNamespace,
    state: LocalJsonStateBackend,
) -> None:
    """The definition was already sent, so only the move happens."""
    fabric.list_items.return_value = [
        {"id": "nb-a", "type": "Notebook", "displayName": "A"},
    ]
    _write_item(root, "A.Notebook")
    git_repo.commit("first")
    _deploy(root, state_backend=state, environment="dev")

    (root / "Sales").mkdir()
    (root / "A.Notebook").rename(root / "Sales" / "A.Notebook")
    git_repo.commit("move")
    fabric.update.reset_mock()
    report = _deploy(root, state_backend=state, environment="dev")

    assert [(r.display_name, r.action, r.moved) for r in report.results] == [
        ("A", "moved", True)
    ]
    fabric.move.assert_called_once_with(_WORKSPACE_ID, "nb-a", "folder-Sales")
    fabric.update.assert_not_called()
    items = _recorded(state, "dev").items
    assert items[("Notebook", "A")].folder_path == "Sales"


def test_an_item_moved_to_the_root_in_git_is_moved_there(
    git_repo: GitRepo,
    root: Path,
    fabric: SimpleNamespace,
    state: LocalJsonStateBackend,
) -> None:
    """The state shows Git moved it, so it leaves its workspace folder."""
    fabric.list_folders.return_value = [
        {"id": "f-sales", "displayName": "Sales"},
    ]
    fabric.list_items.return_value = [
        {
            "id": "nb-a",
            "type": "Notebook",
            "displayName": "A",
            "folderId": "f-sales",
        },
    ]
    _write_item(root, "Sales/A.Notebook")
    git_repo.commit("first")
    _deploy(root, state_backend=state, environment="dev")

    (root / "Sales" / "A.Notebook").rename(root / "A.Notebook")
    git_repo.commit("move to the root")
    fabric.update.reset_mock()
    report = _deploy(root, state_backend=state, environment="dev")

    assert [(r.display_name, r.action, r.moved) for r in report.results] == [
        ("A", "moved", True)
    ]
    fabric.move.assert_called_once_with(_WORKSPACE_ID, "nb-a", None)
    fabric.update.assert_not_called()
    items = _recorded(state, "dev").items
    assert items[("Notebook", "A")].folder_path is None


def test_the_state_records_each_item_and_forgets_deleted_ones(
    git_repo: GitRepo,
    root: Path,
    fabric: SimpleNamespace,
    state: LocalJsonStateBackend,
) -> None:
    """Hash and folder per item; an item gone from source and workspace goes."""
    a = _write_item(root, "A.Notebook")
    _write_item(root, "Sales/B.Report")
    git_repo.commit("first")
    _deploy(root, state_backend=state, environment="dev")

    items = _recorded(state, "dev").items
    assert set(items) == {("Notebook", "A"), ("Report", "B")}
    assert items[("Report", "B")].folder_path == "Sales"
    assert items[("Notebook", "A")].content_hash == definition_hash(
        pack_item_definition(str(a))
    )

    shutil.rmtree(a)
    git_repo.commit("delete A")
    _deploy(root, state_backend=state, environment="dev")

    assert set(_recorded(state, "dev").items) == {("Report", "B")}


# ---------------------------------------------------------------------------
# plan_all_items: see the plan without applying it
# ---------------------------------------------------------------------------


def _plan(root: Path, **kwargs: Any) -> DeploymentPlan:
    return plan_all_items(
        "Sales-DEV", str(root), start_path=str(root), **kwargs
    )


def test_plan_all_items_changes_nothing(
    root: Path, fabric: SimpleNamespace
) -> None:
    """The plan comes from reads only; nothing is created or updated."""
    fabric.list_items.return_value = [
        {"id": "nb-a", "type": "Notebook", "displayName": "A"},
    ]
    _write_item(root, "A.Notebook")
    _write_item(root, "Sales/B.Notebook")

    plan = _plan(root)

    assert [
        (a.action, a.display_name, a.folder_path) for a in plan.actions
    ] == [
        (DeploymentActionType.UPDATE, "A", None),
        (DeploymentActionType.CREATE, "B", "Sales"),
    ]
    _assert_no_change(fabric)


def test_the_plan_is_what_deploy_all_items_then_does(
    git_repo: GitRepo,
    root: Path,
    fabric: SimpleNamespace,
    state: LocalJsonStateBackend,
) -> None:
    """Planning reads the state and leaves it; deploying records it."""
    fabric.list_items.return_value = [
        {"id": "nb-a", "type": "Notebook", "displayName": "A"},
        {"id": "nb-b", "type": "Notebook", "displayName": "B"},
    ]
    a = _write_item(root, "A.Notebook")
    _write_item(root, "B.Notebook")
    first = git_repo.commit("first")
    _deploy(root, state_backend=state, environment="dev")

    _change(a)
    head = git_repo.commit("second")
    fabric.update.reset_mock()
    plan = _plan(root, state_backend=state, environment="dev")

    assert [action.describe() for action in plan.actions] == [
        "UPDATE   A.Notebook  SOURCE_CHANGED"
    ]
    assert _recorded(state, "dev").source_commit == first
    fabric.update.assert_not_called()

    report = _deploy(root, state_backend=state, environment="dev")

    assert [(r.display_name, r.action) for r in report.results] == [
        ("A", "updated")
    ]
    assert _recorded(state, "dev").source_commit == head


def test_plan_all_items_with_nothing_selected_calls_nothing(
    root: Path, fabric: SimpleNamespace
) -> None:
    """An empty selection is an empty plan, without a Fabric call."""
    assert _plan(root) == DeploymentPlan()
    fabric.resolve_workspace.assert_not_called()


def test_plan_details_show_folders_relative_to_the_items_path(
    git_repo: GitRepo, root: Path, fabric: SimpleNamespace
) -> None:
    """A moved item points to its new folder under path, not the full path."""
    fabric.list_items.return_value = [
        {"id": "nb-a", "type": "Notebook", "displayName": "A"},
    ]
    _write_item(root, "A.Notebook")
    baseline = git_repo.commit("first")
    (root / "Sales").mkdir()
    (root / "A.Notebook").rename(root / "Sales" / "A.Notebook")
    git_repo.commit("move")

    plan = _plan(root, baseline_commit=baseline)

    assert [(a.action, a.detail) for a in plan.actions] == [
        (DeploymentActionType.UPDATE, None),
        (DeploymentActionType.NOOP, "Still defined at Sales/A.Notebook."),
    ]


def test_plan_all_items_needs_the_workspace(
    root: Path, fabric: SimpleNamespace
) -> None:
    """No workspace or no listing, no plan: the call raises."""
    _write_item(root, "A.Notebook")

    fabric.resolve_workspace.return_value = None
    with pytest.raises(ConfigurationError, match="not found"):
        _plan(root)

    fabric.resolve_workspace.return_value = _WORKSPACE_ID
    fabric.list_items.return_value = None
    with pytest.raises(RequestError, match="Could not list"):
        _plan(root)


def test_plan_all_items_delegates_to_the_engine() -> None:
    """The public function forwards every argument to the engine."""
    backend = MagicMock()
    with patch(
        "pyfabricops.helpers.items._plan_all",
        return_value=DeploymentPlan(),
    ) as engine:
        plan_all_items(
            "Sales-DEV",
            "stg",
            "stg",
            item_types=["Notebook"],
            baseline_commit="abc123",
            repository_path="src",
            state_backend=backend,
            environment="dev",
            resolve_dependencies=False,
        )

    engine.assert_called_once_with(
        "Sales-DEV",
        "stg",
        start_path="stg",
        item_types=["Notebook"],
        baseline_commit="abc123",
        repository_path="src",
        state_backend=backend,
        environment="dev",
        resolve_dependencies=False,
    )


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def _write_report(root: Path, relative: str, model_path: str) -> Path:
    """A report whose definition.pbir points to a semantic model by path."""
    report = _write_item(root, relative)
    pbir = {
        "version": "4.0",
        "datasetReference": {"byPath": {"path": model_path}},
    }
    (report / "definition.pbir").write_text(json.dumps(pbir), encoding="utf-8")
    return report


def _sales(root: Path) -> Path:
    """The Sales model and the Sales report that reads it."""
    _write_item(root, "Sales.SemanticModel")
    return _write_report(root, "Sales.Report", "../Sales.SemanticModel")


def test_a_model_missing_from_the_workspace_is_created_before_its_report(
    git_repo: GitRepo, root: Path, fabric: SimpleNamespace
) -> None:
    """Only the report changed, but the workspace lacks its model."""
    fabric.list_items.return_value = [
        {"id": "rp-sales", "type": "Report", "displayName": "Sales"},
    ]
    report_dir = _sales(root)
    baseline = git_repo.commit("baseline")
    _change(report_dir)
    git_repo.commit("change the report")

    report = _deploy(root, baseline_commit=baseline)

    assert [
        (r.item_type, r.display_name, r.action) for r in report.results
    ] == [
        ("SemanticModel", "Sales", "created"),
        ("Report", "Sales", "updated"),
    ]
    assert fabric.create.call_args.kwargs["item_type"] == "SemanticModel"
    assert fabric.update.call_args.args[:2] == (_WORKSPACE_ID, "rp-sales")


def test_without_dependency_resolution_only_the_selection_goes(
    git_repo: GitRepo, root: Path, fabric: SimpleNamespace
) -> None:
    """resolve_dependencies=False deploys as before: the report alone."""
    fabric.list_items.return_value = [
        {"id": "rp-sales", "type": "Report", "displayName": "Sales"},
    ]
    report_dir = _sales(root)
    baseline = git_repo.commit("baseline")
    _change(report_dir)
    git_repo.commit("change the report")

    report = _deploy(
        root, baseline_commit=baseline, resolve_dependencies=False
    )

    assert [(r.display_name, r.action) for r in report.results] == [
        ("Sales", "updated")
    ]
    fabric.create.assert_not_called()


def test_the_state_records_a_model_created_for_its_report(
    git_repo: GitRepo,
    root: Path,
    fabric: SimpleNamespace,
    state: LocalJsonStateBackend,
) -> None:
    """What was sent to meet a dependency is what was sent, too."""
    report_dir = _sales(root)
    git_repo.commit("first")
    _deploy(root, state_backend=state, environment="dev")

    # The model is deleted from the workspace by hand; the report changes.
    fabric.list_items.return_value = [
        {"id": "rp-sales", "type": "Report", "displayName": "Sales"},
    ]
    _change(report_dir)
    git_repo.commit("change the report")
    with patch(f"{_ENGINE}._StateTracker.record", autospec=True) as record:
        report = _deploy(root, state_backend=state, environment="dev")

    assert [(r.item_type, r.action) for r in report.results] == [
        ("SemanticModel", "created"),
        ("Report", "updated"),
    ]
    recorded = record.call_args.args[3]
    assert {(i.item_type, i.display_name) for i in recorded} == {
        ("Report", "Sales"),
        ("SemanticModel", "Sales"),
    }
    assert all(i.content_hash for i in recorded)


def test_plan_all_items_validates_a_needed_item_in_the_workspace(
    git_repo: GitRepo, root: Path, fabric: SimpleNamespace
) -> None:
    """The model is in the workspace: validated, not deployed."""
    fabric.list_items.return_value = [
        {"id": "rp-sales", "type": "Report", "displayName": "Sales"},
        {"id": "sm-sales", "type": "SemanticModel", "displayName": "Sales"},
    ]
    report_dir = _sales(root)
    baseline = git_repo.commit("baseline")
    _change(report_dir)
    git_repo.commit("change the report")

    plan = _plan(root, baseline_commit=baseline)

    assert [a.describe() for a in plan.actions] == [
        "NOOP     Sales.SemanticModel  DEPENDENCY_REQUIRED: Required by "
        "Sales.Report (definition.pbir byPath); already in the workspace.",
        "UPDATE   Sales.Report  SOURCE_CHANGED",
    ]
    _assert_no_change(fabric)


def test_a_report_pointing_to_no_model_is_blocked(
    root: Path, fabric: SimpleNamespace
) -> None:
    """A report without its data is not deployed."""
    _write_report(root, "Sales.Report", "../Gone.SemanticModel")

    report = _deploy(root)

    assert [(r.display_name, r.action) for r in report.results] == [
        ("Sales", "failed")
    ]
    assert report.results[0].error == (
        "definition.pbir points to ../Gone.SemanticModel, which is not a "
        "semantic model of the source."
    )
    _assert_no_change(fabric)


def test_a_lakehouse_missing_from_the_workspace_is_created_before_its_notebook(
    git_repo: GitRepo, root: Path, fabric: SimpleNamespace
) -> None:
    """The notebook's default lakehouse, found by name, is created first."""
    fabric.list_items.return_value = [
        {"id": "nb-load", "type": "Notebook", "displayName": "Load"},
    ]
    _write_item(root, "Gold.Lakehouse")
    notebook = _write_item(root, "Load.Notebook")
    lakehouse = {
        "default_lakehouse": "<lakehouse-id>",
        "default_lakehouse_name": "Gold",
    }
    meta = json.dumps({"dependencies": {"lakehouse": lakehouse}}, indent=2)
    (notebook / "notebook-content.py").write_text(
        "# Fabric notebook source\n\n# METADATA ********************\n\n"
        + "\n".join(f"# META {line}" for line in meta.splitlines())
        + "\n",
        encoding="utf-8",
    )
    baseline = git_repo.commit("baseline")
    _change(notebook)
    git_repo.commit("change the notebook")

    report = _deploy(root, baseline_commit=baseline)

    assert [
        (r.item_type, r.display_name, r.action) for r in report.results
    ] == [
        ("Lakehouse", "Gold", "created"),
        ("Notebook", "Load", "updated"),
    ]
