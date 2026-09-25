"""
Deployment engine shared by the ``deploy_all_*`` helpers.

A run plans first, then applies. It selects the local items (every item, or
only those changed in Git since a baseline commit, which a deployment state
can supply per item type), lists the workspace items and folders once, and
builds a ``DeploymentPlan`` from them without changing anything.
``DeploymentExecutor`` then applies the plan, and the run returns a
``DeploymentReport`` with the outcome of each item, so a partial failure
reaches the caller instead of being logged and lost. The state is recorded
only when every item succeeded. Nothing is ever deleted.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TypeAlias, cast

from pandas import DataFrame

from ..api.api import ApiResult, _error_detail, api_request
from ..core.folders import create_folder, list_folders
from ..core.workspaces import resolve_workspace
from ..helpers.content_hash import definition_hash
from ..helpers.dependencies import (
    IdReference,
    LocalCatalog,
    pipeline_references,
    scan_references,
)
from ..helpers.dependency_graph import DependencyGraph, ItemKey
from ..helpers.deployment_plan import (
    DeployedItem,
    DeploymentAction,
    DeploymentActionType,
    DeploymentPlan,
    DeploymentPlanner,
    SourceChange,
    SourceItem,
)
from ..helpers.deployment_state import (
    DeploymentState,
    DeploymentStateBackend,
)
from ..helpers.source_changes import (
    GitChangeDetector,
    ItemChange,
    ItemResolver,
    has_uncommitted_changes,
    head_commit,
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
    "created", "updated", "moved", "failed", "skipped"
]

_ACTIONS: tuple[DeploymentOutcome, ...] = (
    "created",
    "updated",
    "moved",
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
        action (str): ``"created"``, ``"updated"``, ``"moved"`` (only its
            folder changed, so its definition was not sent), ``"failed"``,
            or ``"skipped"`` when the item was not attempted because an
            earlier one failed with ``fail_fast=True``.
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
        results (list[DeploymentResult]): One result per item acted on, in
            deployment order. An item that needs nothing has none.

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
        """True when every item was created, updated or moved."""
        return all(
            r.action in ("created", "updated", "moved") for r in self.results
        )

    @property
    def duration_seconds(self) -> float:
        """Total wall-clock time spent on the items."""
        return sum(r.duration_seconds for r in self.results)

    def summary(self) -> dict[str, int]:
        """
        Count the items by action.

        Returns:
            dict[str, int]: The number of items created, updated, moved,
                failed and skipped.
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
        content = platform_path.read_bytes()
    except FileNotFoundError as e:
        raise ConfigurationError(f"{platform_path} not found.") from e
    return _parse_display_name(content, str(platform_path))


def _parse_display_name(content: bytes, source: str) -> str:
    """
    Read the display name from the content of a ``.platform`` file.

    Raises:
        ConfigurationError: If the content is not valid JSON or has no
            ``metadata.displayName``.
    """
    try:
        platform = json.loads(content)
    except ValueError as e:
        raise ConfigurationError(f"{source} is not valid JSON: {e}") from e

    metadata = platform.get("metadata") if isinstance(platform, dict) else None
    display_name = (
        metadata.get("displayName") if isinstance(metadata, dict) else None
    )
    if not isinstance(display_name, str) or not display_name:
        raise ConfigurationError(f"{source} has no metadata.displayName.")
    return display_name


def _read_source_items(
    local_items: Sequence[tuple[str, str]], *, start_path: str | None
) -> list[SourceItem]:
    """Describe each local item for the planner, reading its ``.platform``."""
    return [
        _read_source_item(item_type, item_path, start_path=start_path)
        for item_type, item_path in local_items
    ]


def _read_source_item(
    item_type: str,
    item_path: str,
    *,
    start_path: str | None,
    change: SourceChange | None = None,
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
            change=change,
        )
    return SourceItem(
        item_type=item_type,
        source_path=item_path,
        display_name=display_name,
        folder_path=folder_path,
        change=change,
    )


def _read_deleted_item(
    detector: GitChangeDetector,
    change: ItemChange,
    *,
    path: str,
    start_path: str | None,
) -> SourceItem:
    """Describe an item deleted since the baseline, named as it was then."""
    item_path = Path(path, change.path).as_posix()
    folder_path = extract_middle_path(item_path, start_path=start_path)
    platform = f"{change.path}/.platform"
    try:
        display_name = _parse_display_name(
            detector.read_baseline_file(platform),
            f"{platform} at commit {detector.baseline[:12]}",
        )
    except PyFabricOpsError as e:
        return SourceItem(
            item_type=change.item_type,
            source_path=item_path,
            folder_path=folder_path,
            error=str(e),
            change=SourceChange.DELETED,
        )
    return SourceItem(
        item_type=change.item_type,
        source_path=item_path,
        display_name=display_name,
        folder_path=folder_path,
        change=SourceChange.DELETED,
    )


def _read_changed_items(
    path: str,
    item_types: Sequence[str],
    *,
    start_path: str | None,
    baseline_commit: str,
    target_commit: str,
    repository_path: str,
) -> list[SourceItem]:
    """
    Describe the items of the given types changed in Git between commits.

    Changes are found in ``repository_path`` and the items are read from the
    same place under ``path``, which may be a staging copy.

    Raises:
        ConfigurationError: If git cannot compare the commits.
    """
    detector = GitChangeDetector(
        repository_path, baseline_commit, target_commit
    )
    return [
        _read_deleted_item(detector, c, path=path, start_path=start_path)
        if c.change is SourceChange.DELETED
        else _read_source_item(
            c.item_type,
            Path(path, c.path).as_posix(),
            start_path=start_path,
            change=c.change,
        )
        for c in detector.changed_items(ItemResolver(item_types))
    ]


def _in_deployment_order(
    items: list[SourceItem], item_types: Sequence[str]
) -> list[SourceItem]:
    """Order items by type and path; deleted ones last, dependents first."""
    rank = {item_type: n for n, item_type in enumerate(item_types)}
    kept = sorted(
        (i for i in items if i.change is not SourceChange.DELETED),
        key=lambda i: (rank[i.item_type], i.source_path),
    )
    deleted = sorted(
        (i for i in items if i.change is SourceChange.DELETED),
        key=lambda i: (-rank[i.item_type], i.source_path),
    )
    return kept + deleted


def _select_items(
    path: str,
    baselines: Mapping[str, str | None],
    *,
    start_path: str | None,
    target_commit: str,
    repository_path: str | None,
) -> list[SourceItem]:
    """
    Select the items of a run and describe them for the planner.

    ``baselines`` maps each item type, in dependency order, to the commit
    its changes are compared from. A type without one gets every local item
    of that type; a type with one gets its items changed since then. Items
    come in dependency order, deleted ones last with dependents first.
    """
    types = list(baselines)
    every = [t for t in types if baselines[t] is None]
    groups: dict[str, list[str]] = {}
    for item_type in types:
        baseline = baselines[item_type]
        if baseline is not None:
            groups.setdefault(baseline, []).append(item_type)

    items = _read_source_items(
        _find_local_items(path, every), start_path=start_path
    )
    if not groups and not items:
        logger.warning(f"No items to deploy were found under {path}.")

    compared = repository_path or path
    for baseline, group in groups.items():
        changed = _read_changed_items(
            path,
            group,
            start_path=start_path,
            baseline_commit=baseline,
            target_commit=target_commit,
            repository_path=compared,
        )
        scope = "" if len(group) == len(types) else f" ({', '.join(group)})"
        logger.info(
            f"{len(changed)} item(s) changed under {compared} since "
            f"{baseline}{scope}."
        )
        items += changed
    return _in_deployment_order(items, types)


def _describe_error(result: ApiResult) -> str:
    """
    Summarize a failed API result as ``status: errorCode - message``.

    The messages of the error's ``moreDetails`` follow, when it has any.
    """
    detail = result.error or ""
    try:
        body = json.loads(detail)
    except ValueError:
        body = None
    if isinstance(body, dict):
        detail = _error_detail(body) or detail
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
    workspace_id: str, item_id: str, folder_id: str | None
) -> ApiResult:
    """Move an item into a folder, or to the workspace root for None."""
    return cast(
        ApiResult,
        api_request(
            endpoint=f"/workspaces/{workspace_id}/items/{item_id}/move",
            method="post",
            payload={"targetFolderId": folder_id} if folder_id else {},
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
    """Return the ``(item_type, display_name)`` an action targets."""
    # DeploymentAction guarantees a display name to every action but BLOCKED.
    return action.item_type, cast(str, action.display_name)


def _planned_target(
    index: _WorkspaceIndex, action: DeploymentAction
) -> dict[str, Any]:
    """
    Return the workspace item an UPDATE or MOVE action changes.

    Raises:
        ConfigurationError: If the item is not in the workspace, which means
            the plan does not match the workspace it is applied to.
    """
    item_type, display_name = _identity(action)
    existing = index.items.get((item_type, display_name))
    if existing is None:
        planned = (
            "a move"
            if action.action is DeploymentActionType.MOVE
            else "an update"
        )
        raise ConfigurationError(
            f"{display_name}.{item_type} is planned as {planned} but is not "
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
    """
    Move an existing item into its folder when it is elsewhere.

    An item at the root of the source is left in its workspace folder: only
    a MOVE, planned when the source moved the item, takes it to the root.
    """
    if not folder_id:
        return False
    return _move_to(index, item_id, existing, folder_id)


def _move_to(
    index: _WorkspaceIndex,
    item_id: str,
    existing: dict[str, Any],
    folder_id: str | None,
) -> bool:
    """Move an existing item to a folder, or to the root for None."""
    if existing.get("folderId") == folder_id:
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
    if action.action is DeploymentActionType.DELETE:
        # No policy allows deletions yet: refuse, and say what to do.
        return _action_result(
            action,
            "failed",
            error=(
                "Deleting items is not supported yet; delete "
                f"{action.display_name}.{action.item_type} from the "
                "workspace by hand."
            ),
        )

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
        elif action.action is DeploymentActionType.MOVE:
            existing = _planned_target(index, action)
            folder_id = index.ensure_folder(action.folder_path)
            item_id = cast(str, existing["id"])
            moved = _move_to(index, item_id, existing, folder_id)
            outcome = "moved"
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
            f"{counts['updated']} updated, {counts['moved']} moved) in "
            f"{report.duration_seconds:.1f}s.",
        )
        return

    failed = ", ".join(_label(r) for r in report.failed)
    logger.error(
        f"Deployment to workspace '{report.workspace}' finished with "
        f"{counts['failed']} failed and {counts['skipped']} skipped item(s) "
        f"out of {len(report.results)}. Failed: {failed}."
    )


def _log_noop(action: DeploymentAction) -> None:
    """Log an action that needs no change to the workspace."""
    logger.info(
        f"{action.display_name}.{action.item_type}: nothing to do. "
        f"{action.detail or ''}".rstrip()
    )


def _fail_all(
    report: DeploymentReport,
    items: Sequence[SourceItem],
    error: str,
) -> DeploymentReport:
    """Mark every selected item as failed with the same error."""
    report.results.extend(
        DeploymentResult(
            item_type=item.item_type,
            display_name=item.display_name,
            path=item.source_path,
            action="failed",
            error=error,
        )
        for item in items
    )
    _log_report(report)
    return report


class DeploymentExecutor:
    """
    Apply a deployment plan to a workspace through the Fabric API.

    The executor decides nothing: it creates the items planned as CREATE,
    updates the items planned as UPDATE (moving them first when their folder
    differs), moves the items planned as MOVE without sending their
    definition, and reports BLOCKED items as failed, creating missing
    folders on the way. It refuses DELETE, which no policy allows yet,
    reporting it as failed, and a NOOP gets a log line but no result. Used
    by ``deploy_all_items``; not exported from ``pyfabricops`` yet.

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
            list[DeploymentResult]: One result per action other than NOOP,
                in plan order.
        """
        results: list[DeploymentResult] = []
        for position, action in enumerate(plan.actions):
            if action.action is DeploymentActionType.NOOP:
                _log_noop(action)
                continue

            result = _apply_action(self._index, action)
            results.append(result)
            _log_result(result)

            if result.action == "failed" and self._fail_fast:
                results.extend(
                    _action_result(skipped, "skipped")
                    for skipped in plan.actions[position + 1 :]
                    if skipped.action is not DeploymentActionType.NOOP
                )
                break
        return results


def _utc_now() -> str:
    """Return the current UTC time as ``YYYY-MM-DDTHH:MM:SSZ``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _deployed_after(
    previous: Mapping[tuple[str, str], DeployedItem],
    items: Sequence[SourceItem],
) -> dict[tuple[str, str], DeployedItem]:
    """
    What was sent for each item once a successful run is over.

    Deletions go first, so an item moved to another folder keeps a record
    under its new place.
    """
    deployed = dict(previous)
    for item in items:
        if item.change is SourceChange.DELETED and item.display_name:
            deployed.pop((item.item_type, item.display_name), None)
    for item in items:
        if (
            item.change is not SourceChange.DELETED
            and item.display_name
            and item.content_hash
        ):
            deployed[(item.item_type, item.display_name)] = DeployedItem(
                item.content_hash, item.folder_path
            )
    return deployed


@dataclass
class _StateTracker:
    """The state of an environment, read before a run and recorded after."""

    backend: DeploymentStateBackend
    environment: str
    workspace: str
    head: str
    previous: DeploymentState | None

    @classmethod
    def open(
        cls,
        backend: DeploymentStateBackend,
        *,
        environment: str,
        workspace: str,
        repository_path: str,
    ) -> _StateTracker:
        """
        Resolve HEAD and load the state of the environment.

        A state recorded for another workspace is ignored, so this workspace
        gets every item.

        Raises:
            ConfigurationError: If git cannot resolve HEAD in
                ``repository_path``, or the stored state is invalid.
        """
        head = head_commit(repository_path)
        if has_uncommitted_changes(repository_path):
            logger.warning(
                f"{repository_path} has changes in no commit; the deployment "
                f"state will still record commit {head[:12]}."
            )
        previous = backend.load(environment)
        if previous is not None and not previous.targets(workspace):
            logger.warning(
                f"Deployment state '{environment}' was recorded for workspace "
                f"'{previous.workspace}', not '{workspace}'; ignoring it."
            )
            previous = None
        return cls(backend, environment, workspace, head, previous)

    def baselines(
        self, item_types: Sequence[str], baseline_commit: str | None
    ) -> dict[str, str | None]:
        """Give each type the baseline passed, else the state's commit."""
        if baseline_commit is not None:
            return dict.fromkeys(item_types, baseline_commit)
        if self.previous is None:
            logger.info(
                f"No usable deployment state '{self.environment}': deploying "
                "every item."
            )
            return dict.fromkeys(item_types, None)

        baselines = {t: self.previous.commits.get(t) for t in item_types}
        unrecorded = [t for t in item_types if baselines[t] is None]
        if unrecorded:
            logger.info(
                f"Deployment state '{self.environment}' has no deployment of "
                f"{', '.join(unrecorded)} yet: deploying every item of those "
                "types."
            )
        return baselines

    @property
    def deployed_items(self) -> Mapping[tuple[str, str], DeployedItem]:
        """What the last successful deployment sent for each item."""
        return self.previous.items if self.previous is not None else {}

    def record(
        self,
        report: DeploymentReport,
        item_types: Sequence[str],
        items: Sequence[SourceItem],
    ) -> None:
        """
        Record the run, if every item succeeded.

        HEAD becomes the commit of the run's types, and each item of the run
        gets the hash and folder it was deployed with; items deleted from
        the source lose theirs.
        """
        if not report.ok:
            logger.warning(
                f"Deployment state '{self.environment}' not updated: not "
                "every item succeeded, so the next run compares from the same "
                "commits."
            )
            return

        workspace_id = report.workspace_id or (
            self.previous.workspace_id
            if self.previous is not None
            else resolve_workspace(self.workspace)
        )
        if workspace_id is None:
            logger.warning(
                f"Deployment state '{self.environment}' not updated: "
                f"workspace '{self.workspace}' not found."
            )
            return

        commits = dict(self.previous.commits) if self.previous else {}
        commits.update(dict.fromkeys(item_types, self.head))
        self.backend.save(
            self.environment,
            DeploymentState(
                environment=self.environment,
                workspace=self.workspace,
                workspace_id=workspace_id,
                source_commit=self.head,
                commits=commits,
                deployed_at_utc=_utc_now(),
                items=_deployed_after(self.deployed_items, items),
            ),
        )
        logger.info(
            f"Deployment state '{self.environment}' updated to commit "
            f"{self.head[:12]}."
        )


def _deploy_all(
    workspace: str,
    path: str,
    *,
    start_path: str | None = None,
    item_types: Sequence[str] | None = None,
    fail_fast: bool = False,
    baseline_commit: str | None = None,
    repository_path: str | None = None,
    state_backend: DeploymentStateBackend | None = None,
    environment: str | None = None,
    resolve_dependencies: bool = True,
) -> DeploymentReport:
    """
    Select, plan and apply; with a state backend, record the run.

    The run is recorded only when every item succeeded, with the items it
    created to meet dependencies. See ``deploy_all_items`` for the public
    contract.
    """
    types = _ordered_types(item_types)
    items, tracker = _select_run(
        workspace,
        path,
        types,
        start_path=start_path,
        baseline_commit=baseline_commit,
        repository_path=repository_path,
        state_backend=state_backend,
        environment=environment,
    )
    dependencies = (
        _read_dependencies(
            path, items, start_path=start_path, hashes=tracker is not None
        )
        if resolve_dependencies and items
        else None
    )
    report = _deploy_items(
        workspace,
        items,
        fail_fast=fail_fast,
        deployed_items=tracker.deployed_items if tracker else None,
        root=path,
        dependencies=dependencies,
        item_types=types,
    )
    if tracker is not None:
        tracker.record(
            report, types, [*items, *_created(report, dependencies)]
        )
    return report


def _plan_all(
    workspace: str,
    path: str,
    *,
    start_path: str | None = None,
    item_types: Sequence[str] | None = None,
    baseline_commit: str | None = None,
    repository_path: str | None = None,
    state_backend: DeploymentStateBackend | None = None,
    environment: str | None = None,
    resolve_dependencies: bool = True,
) -> DeploymentPlan:
    """
    Build the plan ``_deploy_all`` would apply, and stop there.

    Only reads happen: the local items, Git and one listing of the
    workspace. The state is read, never recorded. See ``plan_all_items``
    for the public contract.

    Raises:
        ConfigurationError: If the workspace is not found.
        RequestError: If its items and folders cannot be listed.
    """
    types = _ordered_types(item_types)
    items, tracker = _select_run(
        workspace,
        path,
        types,
        start_path=start_path,
        baseline_commit=baseline_commit,
        repository_path=repository_path,
        state_backend=state_backend,
        environment=environment,
    )
    if not items:
        return DeploymentPlan()

    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        raise ConfigurationError(f"Workspace '{workspace}' not found.")
    index = _WorkspaceIndex.load(workspace_id)
    if index is None:
        raise RequestError(
            f"Could not list the items and folders of workspace '{workspace}'."
        )

    dependencies = (
        _read_dependencies(
            path, items, start_path=start_path, hashes=tracker is not None
        )
        if resolve_dependencies
        else None
    )
    planner = _planner(
        index,
        tracker.deployed_items if tracker else None,
        root=path,
        dependencies=dependencies,
        item_types=types,
        warnings=_id_warnings(dependencies, index),
    )
    return planner.plan(
        items, available=dependencies.available if dependencies else ()
    )


def _select_run(
    workspace: str,
    path: str,
    item_types: Sequence[str],
    *,
    start_path: str | None,
    baseline_commit: str | None,
    repository_path: str | None,
    state_backend: DeploymentStateBackend | None,
    environment: str | None,
) -> tuple[list[SourceItem], _StateTracker | None]:
    """
    Select the items of a run, the same way to plan it or to deploy it.

    Without a state backend every type compares from ``baseline_commit``,
    or deploys every item without one. With a backend, each type compares
    from its last successful deployment unless ``baseline_commit`` is given,
    and the items get the hash of their definition; the tracker returned
    can record the run.
    """
    if state_backend is None:
        items = _select_items(
            path,
            dict.fromkeys(item_types, baseline_commit),
            start_path=start_path,
            target_commit="HEAD",
            repository_path=repository_path,
        )
        return items, None

    tracker = _StateTracker.open(
        state_backend,
        environment=environment or workspace,
        workspace=workspace,
        repository_path=repository_path or path,
    )
    items = _with_content_hashes(
        _select_items(
            path,
            tracker.baselines(item_types, baseline_commit),
            start_path=start_path,
            target_commit=tracker.head,
            repository_path=repository_path,
        )
    )
    return items, tracker


def _with_content_hashes(items: list[SourceItem]) -> list[SourceItem]:
    """Hash the definition of each item to deploy, when it can be read."""
    hashed: list[SourceItem] = []
    for item in items:
        if item.error is None and item.change is not SourceChange.DELETED:
            try:
                definition = pack_item_definition(item.source_path)
            except (PyFabricOpsError, OSError):
                # The executor reads it again and reports the failure.
                definition = None
            if definition is not None:
                item = replace(item, content_hash=definition_hash(definition))
        hashed.append(item)
    return hashed


@dataclass(frozen=True)
class _Dependencies:
    """The references of a run's items, and the local items they need."""

    graph: DependencyGraph
    broken: Mapping[ItemKey, tuple[str, ...]]
    available: list[SourceItem]
    # What the selected pipelines refer to by ID, checked against the
    # workspace once it is listed.
    id_references: Mapping[ItemKey, tuple[IdReference, ...]] = field(
        default_factory=dict
    )


def _read_dependencies(
    path: str,
    items: Sequence[SourceItem],
    *,
    start_path: str | None,
    hashes: bool,
) -> _Dependencies:
    """
    Read what the selected items refer to, and the local items they need.

    A local item of any known type can be needed, whatever the item types
    of the run: the planner decides what to do with it. Needed items get
    the hash of their definition when the run keeps a state.
    """
    catalog = LocalCatalog.read(path, DEPLOY_ORDER)
    keys: list[ItemKey] = [
        (item.item_type, item.display_name)
        for item in items
        if item.display_name is not None
        and item.change is not SourceChange.DELETED
    ]
    scan = scan_references(catalog, keys)
    graph = DependencyGraph(scan.dependencies)

    selected = set(keys)
    available: list[SourceItem] = []
    for key in graph.required_by(keys):
        entry = catalog.get(key)
        if key not in selected and entry is not None:
            available.append(
                _read_source_item(key[0], entry.path, start_path=start_path)
            )
    available = _in_deployment_order(available, DEPLOY_ORDER)
    if hashes:
        available = _with_content_hashes(available)

    id_references: dict[ItemKey, tuple[IdReference, ...]] = {}
    for item in items:
        if (
            item.item_type == "DataPipeline"
            and item.display_name is not None
            and item.error is None
            and item.change is not SourceChange.DELETED
        ):
            references = pipeline_references(item.source_path)
            if references:
                id_references[(item.item_type, item.display_name)] = references
    return _Dependencies(graph, scan.broken, available, id_references)


def _id_warnings(
    dependencies: _Dependencies | None, index: _WorkspaceIndex
) -> dict[ItemKey, tuple[str, ...]]:
    """
    Warn about pipeline references by ID that the workspace cannot meet.

    A reference to the workspace itself (or to no workspace in particular)
    is checked against its items; one to another workspace is not. A value
    that is no ID at all is most likely a placeholder left unreplaced. Only
    warnings: an item created in the same run gets its ID when created.
    """
    if dependencies is None:
        return {}
    workspace_id = _normal_id(index.workspace_id)
    item_ids = {_normal_id(str(item["id"])) for item in index.items.values()}
    warnings: dict[ItemKey, tuple[str, ...]] = {}
    for key, references in dependencies.id_references.items():
        texts: list[str] = []
        for reference in references:
            if reference.workspace_id is not None:
                in_workspace = _normal_id(reference.workspace_id)
                if in_workspace is None:
                    texts.append(
                        f"{reference.where} refers to workspace "
                        f"'{reference.workspace_id}', which is not an ID "
                        "(a placeholder left unreplaced?)."
                    )
                    continue
                if in_workspace != workspace_id:
                    continue
            item_id = _normal_id(reference.item_id)
            if item_id is None:
                texts.append(
                    f"{reference.where} refers to {reference.kind} "
                    f"'{reference.item_id}', which is not an ID (a "
                    "placeholder left unreplaced?)."
                )
            elif item_id not in item_ids:
                texts.append(
                    f"{reference.where} refers to {reference.kind} "
                    f"{reference.item_id}, which is not in the workspace."
                )
        if texts:
            warnings[key] = tuple(dict.fromkeys(texts))
    return warnings


def _normal_id(value: str) -> str | None:
    """Return an ID in its canonical form, or None if it is not one."""
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


def _created(
    report: DeploymentReport, dependencies: _Dependencies | None
) -> list[SourceItem]:
    """Return the items a run created to meet dependencies."""
    if dependencies is None:
        return []
    created = {
        (result.item_type, result.display_name)
        for result in report.results
        if result.action == "created"
    }
    return [
        item
        for item in dependencies.available
        if (item.item_type, item.display_name) in created
    ]


def _planner(
    index: _WorkspaceIndex,
    deployed_items: Mapping[tuple[str, str], DeployedItem] | None,
    *,
    root: str | None,
    dependencies: _Dependencies | None,
    item_types: Sequence[str] | None,
    warnings: Mapping[ItemKey, tuple[str, ...]] | None = None,
) -> DeploymentPlanner:
    """Return the planner of a run, resolving dependencies when given."""
    return DeploymentPlanner(
        existing_items=index.items.keys(),
        deployed_items=deployed_items,
        root=root,
        dependencies=dependencies.graph if dependencies else None,
        broken=dependencies.broken if dependencies else None,
        item_types=item_types if dependencies else None,
        warnings=warnings,
    )


def _deploy_items(
    workspace: str,
    items: list[SourceItem],
    *,
    fail_fast: bool,
    deployed_items: Mapping[tuple[str, str], DeployedItem] | None = None,
    root: str | None = None,
    dependencies: _Dependencies | None = None,
    item_types: Sequence[str] | None = None,
) -> DeploymentReport:
    """
    Plan, then apply, the deployment of the selected items.

    Until the plan is built the run only reads: one listing of the
    workspace. Every change is made by the executor. ``root`` is the folder
    the items were read from, for the plan details; with ``dependencies``,
    the plan meets what the items need, within ``item_types``.
    """
    report = DeploymentReport(workspace=workspace)
    if not items:
        return report

    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return _fail_all(report, items, f"Workspace '{workspace}' not found.")
    report.workspace_id = workspace_id

    index = _WorkspaceIndex.load(workspace_id)
    if index is None:
        return _fail_all(
            report,
            items,
            f"Could not list the items and folders of workspace "
            f"'{workspace}'.",
        )

    warnings = _id_warnings(dependencies, index)
    for (item_type, display_name), texts in warnings.items():
        for text in texts:
            logger.warning(f"{display_name}.{item_type}: {text}")
    planner = _planner(
        index,
        deployed_items,
        root=root,
        dependencies=dependencies,
        item_types=item_types,
        warnings=warnings,
    )
    plan = planner.plan(
        items, available=dependencies.available if dependencies else ()
    )

    executor = DeploymentExecutor(index, fail_fast=fail_fast)
    report.results.extend(executor.apply(plan))

    _log_report(report)
    return report
