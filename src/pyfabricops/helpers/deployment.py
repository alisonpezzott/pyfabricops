"""
Deployment engine shared by the ``deploy_all_*`` helpers.

A run plans first, then applies. It finds the local items in dependency
order, lists the workspace items and folders once, and builds a
``DeploymentPlan`` from them without changing anything. ``DeploymentExecutor``
then applies the plan, and the run returns a ``DeploymentReport`` with the
outcome of each item, so a partial failure reaches the caller instead of
being logged and lost. Nothing is ever deleted.
"""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Literal, TypeAlias, cast

from pandas import DataFrame

from ..api.api import ApiResult, api_request
from ..core.folders import create_folder, list_folders
from ..core.workspaces import resolve_workspace
from ..helpers.deployment_plan import (
    DeploymentAction,
    DeploymentActionType,
    DeploymentPlan,
    DeploymentPlanner,
    SourceItem,
)
from ..items.items import list_items
from ..utils.exceptions import (
    ConfigurationError,
    PyFabricOpsError,
    RequestError,
)
from ..utils.logging import SUCCESS_LEVEL, get_logger
from ..utils.utils import (
    extract_middle_path,
    list_paths_of_type,
    pack_item_definition,
)

__all__ = ["DEPLOY_ORDER", "DeploymentReport", "DeploymentResult"]

logger = get_logger(__name__)

# Item types deployed by default, in dependency order: each type comes after
# the types its items can reference.
DEPLOY_ORDER: tuple[str, ...] = (
    "VariableLibrary",
    "Lakehouse",
    "Warehouse",
    "Environment",
    "Notebook",
    "Dataflow",
    "CopyJob",
    "DataPipeline",
    "SemanticModel",
    "Report",
)

DeploymentOutcome: TypeAlias = Literal[
    "created", "updated", "failed", "skipped"
]

_ACTIONS: tuple[DeploymentOutcome, ...] = (
    "created",
    "updated",
    "failed",
    "skipped",
)


@dataclass(frozen=True)
class DeploymentResult:
    """
    Outcome of deploying one local item.

    Attributes:
        item_type (str): The Fabric item type, from the folder suffix.
        display_name (str | None): The display name from ``.platform``, or
            None when it could not be read.
        path (str): The local item folder.
        action (str): ``"created"``, ``"updated"``, ``"failed"``, or
            ``"skipped"`` when the item was not attempted because an earlier
            one failed with ``fail_fast=True``.
        item_id (str | None): The item ID in the workspace, when known.
        moved (bool): Whether the item was moved to another folder.
        duration_seconds (float): Wall-clock time spent on the item.
        error (str | None): Why the item failed.
    """

    item_type: str
    display_name: str | None
    path: str
    action: DeploymentOutcome
    item_id: str | None = None
    moved: bool = False
    duration_seconds: float = 0.0
    error: str | None = None


@dataclass
class DeploymentReport:
    """
    Per-item outcome of a ``deploy_all_*`` run.

    Attributes:
        workspace (str): The workspace name or ID the run targeted.
        workspace_id (str | None): The resolved workspace ID.
        results (list[DeploymentResult]): One result per local item, in
            deployment order.

    Examples:
        ```python
        report = deploy_all_items('Sales-PRD', 'stg/workspace')
        if report.failed:
            raise SystemExit(1)
        report.durations_by_type()
        ```
    """

    workspace: str
    workspace_id: str | None = None
    results: list[DeploymentResult] = field(default_factory=list)

    @property
    def failed(self) -> list[DeploymentResult]:
        """The items that failed."""
        return [r for r in self.results if r.action == "failed"]

    @property
    def skipped(self) -> list[DeploymentResult]:
        """The items not attempted after a failure with ``fail_fast``."""
        return [r for r in self.results if r.action == "skipped"]

    @property
    def ok(self) -> bool:
        """True when every item was created or updated."""
        return all(r.action in ("created", "updated") for r in self.results)

    @property
    def duration_seconds(self) -> float:
        """Total wall-clock time spent on the items."""
        return sum(r.duration_seconds for r in self.results)

    def summary(self) -> dict[str, int]:
        """
        Count the items by action.

        Returns:
            dict[str, int]: The number of items created, updated, failed and
                skipped.
        """
        counts: dict[str, int] = {action: 0 for action in _ACTIONS}
        for result in self.results:
            counts[result.action] += 1
        return counts

    def durations_by_type(self) -> dict[str, float]:
        """
        Sum the wall-clock time spent per item type.

        Returns:
            dict[str, float]: Seconds per item type, in deployment order.
        """
        durations: dict[str, float] = {}
        for result in self.results:
            durations[result.item_type] = (
                durations.get(result.item_type, 0.0) + result.duration_seconds
            )
        return durations

    def to_df(self) -> DataFrame:
        """
        Return the results as a DataFrame.

        Returns:
            DataFrame: One row per item, one column per result attribute.
        """
        columns = [f.name for f in fields(DeploymentResult)]
        return DataFrame([asdict(r) for r in self.results], columns=columns)


@dataclass
class _WorkspaceIndex:
    """Items and folders of a workspace, listed once per deployment run."""

    workspace_id: str
    items: dict[tuple[str, str], dict[str, Any]]
    folders: dict[str, str]

    @classmethod
    def load(cls, workspace_id: str) -> _WorkspaceIndex | None:
        """List the workspace items and folders, or None if either fails."""
        items = list_items(workspace_id, df=False)
        folders = list_folders(workspace_id, df=False)
        if items is None or folders is None:
            return None

        return cls(
            workspace_id=workspace_id,
            items={
                (item["type"], item["displayName"]): {
                    "id": item["id"],
                    "folderId": item.get("folderId"),
                }
                for item in items
            },
            folders=_folder_ids_by_path(folders),
        )

    def ensure_folder(self, folder_path: str | None) -> str | None:
        """
        Return the ID of a folder path, creating the missing folders.

        Args:
            folder_path (str | None): A path such as ``"Sales/Staging"``, or
                None for the workspace root.

        Returns:
            str | None: The ID of the deepest folder, or None for the root.

        Raises:
            RequestError: If a folder cannot be created.
        """
        parent_id: str | None = None
        current = ""
        for name in [part for part in (folder_path or "").split("/") if part]:
            current = f"{current}/{name}" if current else name
            folder_id = self.folders.get(current)
            if folder_id is None:
                created = create_folder(
                    self.workspace_id, name, parent_folder=parent_id, df=False
                )
                if not created or not created.get("id"):
                    raise RequestError(f"Could not create folder '{current}'.")
                folder_id = cast(str, created["id"])
                self.folders[current] = folder_id
                logger.info(f"Folder '{current}' created.")
            parent_id = folder_id
        return parent_id


def _folder_ids_by_path(folders: list[dict[str, Any]]) -> dict[str, str]:
    """Map each folder's full path (``Parent/Child``) to its ID."""
    by_id = {folder["id"]: folder for folder in folders}
    paths: dict[str, str] = {}
    for folder_id in by_id:
        _folder_path(folder_id, by_id, paths)
    return {path: folder_id for folder_id, path in paths.items()}


def _folder_path(
    folder_id: str,
    by_id: dict[str, dict[str, Any]],
    paths: dict[str, str],
) -> str:
    """Resolve and memoize the full path of a folder."""
    if folder_id in paths:
        return paths[folder_id]

    folder = by_id[folder_id]
    parent_id = folder.get("parentFolderId")
    name = cast(str, folder["displayName"])
    if parent_id in by_id:
        path = f"{_folder_path(parent_id, by_id, paths)}/{name}"
    else:
        path = name
    paths[folder_id] = path
    return path


def _ordered_types(item_types: Sequence[str] | None) -> list[str]:
    """Put the requested item types in dependency order."""
    if item_types is None:
        return list(DEPLOY_ORDER)
    if isinstance(item_types, str):
        item_types = [item_types]

    requested = list(dict.fromkeys(item_types))
    known = [t for t in DEPLOY_ORDER if t in requested]
    unknown = [t for t in requested if t not in DEPLOY_ORDER]
    return known + unknown


def _find_local_items(
    path: str, item_types: Sequence[str]
) -> list[tuple[str, str]]:
    """List the local item folders as ``(item_type, path)`` pairs."""
    found: list[tuple[str, str]] = []
    for item_type in item_types:
        item_paths = sorted(
            str(p) for p in list_paths_of_type(path, item_type)
        )
        found.extend(
            (item_type, item_path)
            for item_path in item_paths
            if Path(item_path).is_dir()
        )
    return found


def _read_display_name(item_path: str) -> str:
    """
    Read the display name from an item's ``.platform`` file.

    Raises:
        ConfigurationError: If the file is missing, is not valid JSON or has
            no ``metadata.displayName``.
    """
    platform_path = Path(item_path) / ".platform"
    try:
        with open(platform_path, encoding="utf-8-sig") as f:
            platform = json.load(f)
    except FileNotFoundError as e:
        raise ConfigurationError(f"{platform_path} not found.") from e
    except ValueError as e:
        raise ConfigurationError(
            f"{platform_path} is not valid JSON: {e}"
        ) from e

    metadata = platform.get("metadata") if isinstance(platform, dict) else None
    display_name = (
        metadata.get("displayName") if isinstance(metadata, dict) else None
    )
    if not isinstance(display_name, str) or not display_name:
        raise ConfigurationError(
            f"{platform_path} has no metadata.displayName."
        )
    return display_name


def _try_display_name(item_path: str) -> str | None:
    """Read the display name, or None when ``.platform`` is unusable."""
    try:
        return _read_display_name(item_path)
    except ConfigurationError:
        return None


def _read_source_items(
    local_items: Sequence[tuple[str, str]], *, start_path: str | None
) -> list[SourceItem]:
    """Describe each local item for the planner, reading its ``.platform``."""
    return [
        _read_source_item(item_type, item_path, start_path=start_path)
        for item_type, item_path in local_items
    ]


def _read_source_item(
    item_type: str, item_path: str, *, start_path: str | None
) -> SourceItem:
    """Describe one local item, or record why it cannot be deployed."""
    folder_path = extract_middle_path(item_path, start_path=start_path)
    try:
        display_name = _read_display_name(item_path)
    except (PyFabricOpsError, OSError) as e:
        return SourceItem(
            item_type=item_type,
            source_path=item_path,
            folder_path=folder_path,
            error=str(e),
        )
    return SourceItem(
        item_type=item_type,
        source_path=item_path,
        display_name=display_name,
        folder_path=folder_path,
    )


def _describe_error(result: ApiResult) -> str:
    """Summarize a failed API result as ``status: errorCode - message``."""
    detail = result.error or ""
    try:
        body = json.loads(detail)
    except ValueError:
        body = None
    if isinstance(body, dict):
        parts = [
            str(body[key]) for key in ("errorCode", "message") if body.get(key)
        ]
        if parts:
            detail = " - ".join(parts)
    return (
        f"{result.status_code}: {detail}"
        if detail
        else f"HTTP {result.status_code}"
    )


def _raise_for_failure(result: ApiResult, step: str) -> None:
    """Raise RequestError when an API step failed."""
    if not result.success:
        raise RequestError(f"{step} failed with {_describe_error(result)}")


def _request_create_item(
    workspace_id: str,
    *,
    display_name: str,
    item_type: str,
    item_definition: dict[str, Any],
    folder_id: str | None,
) -> ApiResult:
    """Create an item from its definition, polling the operation to the end."""
    payload: dict[str, Any] = {
        "displayName": display_name,
        "type": item_type,
        "definition": item_definition,
    }
    if folder_id:
        payload["folderId"] = folder_id
    return cast(
        ApiResult,
        api_request(
            endpoint=f"/workspaces/{workspace_id}/items",
            method="post",
            payload=payload,
            support_lro=True,
            return_result=True,
        ),
    )


def _request_update_item_definition(
    workspace_id: str, item_id: str, item_definition: dict[str, Any]
) -> ApiResult:
    """Replace an item definition, polling the operation to the end."""
    return cast(
        ApiResult,
        api_request(
            endpoint=f"/workspaces/{workspace_id}/items/{item_id}/updateDefinition",
            method="post",
            payload={"definition": item_definition},
            params={"updateMetadata": True},
            support_lro=True,
            return_result=True,
        ),
    )


def _request_move_item(
    workspace_id: str, item_id: str, folder_id: str
) -> ApiResult:
    """Move an item into a folder."""
    return cast(
        ApiResult,
        api_request(
            endpoint=f"/workspaces/{workspace_id}/items/{item_id}/move",
            method="post",
            payload={"targetFolderId": folder_id},
            return_result=True,
        ),
    )


def _action_result(
    action: DeploymentAction,
    outcome: DeploymentOutcome,
    *,
    item_id: str | None = None,
    moved: bool = False,
    duration_seconds: float = 0.0,
    error: str | None = None,
) -> DeploymentResult:
    """Report the outcome of a planned action."""
    return DeploymentResult(
        item_type=action.item_type,
        display_name=action.display_name,
        path=action.source_path,
        action=outcome,
        item_id=item_id,
        moved=moved,
        duration_seconds=duration_seconds,
        error=error,
    )


def _identity(action: DeploymentAction) -> tuple[str, str]:
    """Return the ``(item_type, display_name)`` a CREATE or UPDATE targets."""
    # DeploymentAction guarantees a display name for CREATE and UPDATE.
    return action.item_type, cast(str, action.display_name)


def _planned_target(
    index: _WorkspaceIndex, action: DeploymentAction
) -> dict[str, Any]:
    """
    Return the workspace item an UPDATE action replaces.

    Raises:
        ConfigurationError: If the item is not in the workspace, which means
            the plan does not match the workspace it is applied to.
    """
    item_type, display_name = _identity(action)
    existing = index.items.get((item_type, display_name))
    if existing is None:
        raise ConfigurationError(
            f"{display_name}.{item_type} is planned as an update but is not "
            "in the workspace."
        )
    return existing


def _create_planned_item(
    index: _WorkspaceIndex,
    action: DeploymentAction,
    definition: dict[str, Any],
    folder_id: str | None,
) -> str | None:
    """Create the item of a CREATE action and add it to the index."""
    item_type, display_name = _identity(action)
    created = _request_create_item(
        index.workspace_id,
        display_name=display_name,
        item_type=item_type,
        item_definition=definition,
        folder_id=folder_id,
    )
    _raise_for_failure(created, "Create")
    item_id: str | None = (created.data or {}).get("id")
    index.items[(item_type, display_name)] = {
        "id": item_id,
        "folderId": folder_id,
    }
    return item_id


def _move_if_needed(
    index: _WorkspaceIndex,
    item_id: str,
    existing: dict[str, Any],
    folder_id: str | None,
) -> bool:
    """Move an existing item into its folder when it is elsewhere."""
    if not folder_id or existing.get("folderId") == folder_id:
        return False
    _raise_for_failure(
        _request_move_item(index.workspace_id, item_id, folder_id), "Move"
    )
    existing["folderId"] = folder_id
    return True


def _apply_action(
    index: _WorkspaceIndex, action: DeploymentAction
) -> DeploymentResult:
    """Execute one planned action and report the outcome."""
    if action.action is DeploymentActionType.BLOCKED:
        return _action_result(action, "failed", error=action.detail)

    started = time.monotonic()
    item_id: str | None = None
    moved = False
    outcome: DeploymentOutcome

    try:
        if action.action is DeploymentActionType.CREATE:
            definition = pack_item_definition(action.source_path)
            folder_id = index.ensure_folder(action.folder_path)
            item_id = _create_planned_item(
                index, action, definition, folder_id
            )
            outcome = "created"
        elif action.action is DeploymentActionType.UPDATE:
            # Check the target before the first change to the workspace.
            existing = _planned_target(index, action)
            definition = pack_item_definition(action.source_path)
            folder_id = index.ensure_folder(action.folder_path)
            item_id = cast(str, existing["id"])
            moved = _move_if_needed(index, item_id, existing, folder_id)
            _raise_for_failure(
                _request_update_item_definition(
                    index.workspace_id, item_id, definition
                ),
                "Update definition",
            )
            outcome = "updated"
        else:
            raise ConfigurationError(
                f"Unsupported deployment action: {action.action.value}."
            )
    except (PyFabricOpsError, OSError) as e:
        return _action_result(
            action,
            "failed",
            item_id=item_id,
            moved=moved,
            duration_seconds=time.monotonic() - started,
            error=str(e),
        )

    return _action_result(
        action,
        outcome,
        item_id=item_id,
        moved=moved,
        duration_seconds=time.monotonic() - started,
    )


def _label(result: DeploymentResult) -> str:
    """Name an item as ``DisplayName.Type`` for log messages."""
    if result.display_name:
        return f"{result.display_name}.{result.item_type}"
    return Path(result.path).name


def _log_result(result: DeploymentResult) -> None:
    """Log the outcome of one item."""
    if result.action == "failed":
        logger.error(f"{_label(result)} failed: {result.error}")
    else:
        logger.info(
            f"{_label(result)} {result.action} "
            f"({result.duration_seconds:.1f}s)."
        )


def _log_report(report: DeploymentReport) -> None:
    """Log the outcome of the whole run."""
    counts = report.summary()
    if report.ok:
        logger.log(
            SUCCESS_LEVEL,
            f"{len(report.results)} item(s) deployed to workspace "
            f"'{report.workspace}' ({counts['created']} created, "
            f"{counts['updated']} updated) in "
            f"{report.duration_seconds:.1f}s.",
        )
        return

    failed = ", ".join(_label(r) for r in report.failed)
    logger.error(
        f"Deployment to workspace '{report.workspace}' finished with "
        f"{counts['failed']} failed and {counts['skipped']} skipped item(s) "
        f"out of {len(report.results)}. Failed: {failed}."
    )


def _fail_all(
    report: DeploymentReport,
    local_items: list[tuple[str, str]],
    error: str,
) -> DeploymentReport:
    """Mark every local item as failed with the same error."""
    report.results.extend(
        DeploymentResult(
            item_type=item_type,
            display_name=_try_display_name(item_path),
            path=item_path,
            action="failed",
            error=error,
        )
        for item_type, item_path in local_items
    )
    _log_report(report)
    return report


class DeploymentExecutor:
    """
    Apply a deployment plan to a workspace through the Fabric API.

    The executor decides nothing: it creates the items planned as CREATE,
    updates the items planned as UPDATE (moving them first when their folder
    differs) and reports BLOCKED items as failed, creating missing folders on
    the way. Used by ``deploy_all_items``; not exported from ``pyfabricops``
    yet.

    Args:
        index (_WorkspaceIndex): The workspace items and folders the plan was
            built from.
        fail_fast (bool, optional): Stop at the first failed action and
            report the remaining ones as skipped. Defaults to False.
    """

    def __init__(
        self, index: _WorkspaceIndex, *, fail_fast: bool = False
    ) -> None:
        self._index = index
        self._fail_fast = fail_fast

    def apply(self, plan: DeploymentPlan) -> list[DeploymentResult]:
        """
        Execute the actions of a plan, in order.

        Args:
            plan (DeploymentPlan): The plan to execute.

        Returns:
            list[DeploymentResult]: One result per action, in plan order.
        """
        results: list[DeploymentResult] = []
        for position, action in enumerate(plan.actions):
            result = _apply_action(self._index, action)
            results.append(result)
            _log_result(result)

            if result.action == "failed" and self._fail_fast:
                results.extend(
                    _action_result(skipped, "skipped")
                    for skipped in plan.actions[position + 1 :]
                )
                break
        return results


def _deploy_all(
    workspace: str,
    path: str,
    *,
    start_path: str | None = None,
    item_types: Sequence[str] | None = None,
    fail_fast: bool = False,
) -> DeploymentReport:
    """
    Plan, then apply, the deployment of every local item of the given types.

    Until the plan is built the run only reads: the local items and one
    listing of the workspace. Every change is made by the executor. See
    ``deploy_all_items`` for the public contract.
    """
    report = DeploymentReport(workspace=workspace)

    local_items = _find_local_items(path, _ordered_types(item_types))
    if not local_items:
        logger.warning(f"No items to deploy were found under {path}.")
        return report

    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return _fail_all(
            report, local_items, f"Workspace '{workspace}' not found."
        )
    report.workspace_id = workspace_id

    index = _WorkspaceIndex.load(workspace_id)
    if index is None:
        return _fail_all(
            report,
            local_items,
            f"Could not list the items and folders of workspace "
            f"'{workspace}'.",
        )

    planner = DeploymentPlanner(existing_items=index.items.keys())
    plan = planner.plan(_read_source_items(local_items, start_path=start_path))

    executor = DeploymentExecutor(index, fail_fast=fail_fast)
    report.results.extend(executor.apply(plan))

    _log_report(report)
    return report
