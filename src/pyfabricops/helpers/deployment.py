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

import base64
import json
import os
import time
import uuid
from collections.abc import Collection, Mapping, Sequence
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
    CatalogItem,
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
from ..helpers.drift import comparable_parts, differing_parts
from ..helpers.reconciliation import (
    Reconciliation,
    WorkspaceItem,
    reconcile,
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
    "created", "updated", "moved", "deleted", "failed", "skipped"
]

_ACTIONS: tuple[DeploymentOutcome, ...] = (
    "created",
    "updated",
    "moved",
    "deleted",
    "failed",
    "skipped",
)

# The planned actions that change the workspace.
_APPLIED = frozenset(
    {
        DeploymentActionType.CREATE,
        DeploymentActionType.UPDATE,
        DeploymentActionType.MOVE,
    }
)

# How an outcome that deployed nothing is told to the items that need it.
_NOT_DEPLOYED: dict[str, str] = {"failed": "failed", "skipped": "was skipped"}

# Fabric frees the name of a deleted item only minutes later, and answers a
# create under that name with this error code until then. The create is
# tried again every _NAME_WAIT_SECONDS, for about five minutes.
_NAME_NOT_AVAILABLE = "ItemDisplayNameNotAvailableYet"
_NAME_WAIT_SECONDS = 30.0
_NAME_WAIT_ATTEMPTS = 10


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
            folder changed, so its definition was not sent), ``"deleted"``,
            ``"failed"``, or ``"skipped"`` when the item was not attempted:
            an item it needs was not deployed, an earlier one failed with
            ``fail_fast=True``, or, for a deletion, an earlier item was not
            deployed.
        item_id (str | None): The item ID in the workspace, when known.
        moved (bool): Whether the item was moved to another folder.
        duration_seconds (float): Wall-clock time spent on the item.
        error (str | None): Why the item failed, or which item it needs
            was not deployed.
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
        """
        The items not attempted.

        An item they need was not deployed, or an earlier item failed with
        ``fail_fast``.
        """
        return [r for r in self.results if r.action == "skipped"]

    @property
    def ok(self) -> bool:
        """True when every item was created, updated, moved or deleted."""
        return all(
            r.action in ("created", "updated", "moved", "deleted")
            for r in self.results
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
                deleted, failed and skipped.
        """
        counts: dict[str, int] = {action: 0 for action in _ACTIONS}
        for result in self.results:
            counts[result.action] += 1
        return counts

    def describe(self) -> str:
        """
        Describe the run: one line per item, then the counts and the time.

        Returns:
            str: Such as ``updated  Orders.Notebook  (2.1s)``, a failed or
                skipped item followed by why, and a last line of counts.

        Examples:
            ```python
            report = deploy_all_items('Sales-PRD', staging)
            print(report.describe())
            ```
        """
        lines = []
        for result in self.results:
            line = f"{result.action:<8} {_label(result)}"
            if result.error:
                line += f": {result.error}"
            elif result.duration_seconds:
                line += f"  ({result.duration_seconds:.1f}s)"
            lines.append(line)
        counts = self.summary()
        lines.append(
            ", ".join(f"{counts[action]} {action}" for action in _ACTIONS)
            + f" in {self.duration_seconds:.1f}s"
        )
        return "\n".join(lines)

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


def _parse_logical_id(content: bytes) -> str | None:
    """Read ``config.logicalId`` from a ``.platform`` file, if it has one."""
    try:
        platform = json.loads(content)
    except ValueError:
        return None
    config = platform.get("config") if isinstance(platform, dict) else None
    logical_id = config.get("logicalId") if isinstance(config, dict) else None
    return logical_id if isinstance(logical_id, str) and logical_id else None


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
        content = detector.read_baseline_file(platform)
        display_name = _parse_display_name(
            content, f"{platform} at commit {detector.baseline[:12]}"
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
        logical_id=_parse_logical_id(content),
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
            # Replacing a definition twice gives the same item.
            retry=True,
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
            retry=True,
        ),
    )


def _request_delete_item(workspace_id: str, item_id: str) -> ApiResult:
    """
    Delete an item, as Fabric deletes it by default.

    Fabric keeps a deleted item in the workspace recycle bin for a while
    when its type supports it, and deletes any other at once.
    """
    return cast(
        ApiResult,
        api_request(
            endpoint=f"/workspaces/{workspace_id}/items/{item_id}",
            method="delete",
            return_result=True,
            # A deletion tried again finds the item gone, which it accepts.
            retry=True,
        ),
    )


def _request_item_definition(workspace_id: str, item_id: str) -> ApiResult:
    """Read an item's definition, polling the operation to the end."""
    return cast(
        ApiResult,
        api_request(
            endpoint=f"/workspaces/{workspace_id}/items/{item_id}/getDefinition",
            method="post",
            support_lro=True,
            return_result=True,
            retry=True,
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
    Return the workspace item an UPDATE, MOVE or DELETE action changes.

    Raises:
        ConfigurationError: If the item is not in the workspace, which means
            the plan does not match the workspace it is applied to.
    """
    item_type, display_name = _identity(action)
    existing = index.items.get((item_type, display_name))
    if existing is None:
        planned = _PLANNED_AS.get(action.action, "an update")
        raise ConfigurationError(
            f"{display_name}.{item_type} is planned as {planned} but is not "
            "in the workspace."
        )
    return existing


# How an action that changes an existing item is named in an error.
_PLANNED_AS: dict[DeploymentActionType, str] = {
    DeploymentActionType.MOVE: "a move",
    DeploymentActionType.DELETE: "a deletion",
}


def _definition_to_send(
    index: _WorkspaceIndex, action: DeploymentAction
) -> dict[str, Any]:
    """Pack an item's definition, with a report bound to its model."""
    definition = pack_item_definition(action.source_path)
    if action.item_type == "Report":
        definition = _bind_report(index, action, definition)
    return definition


def _bind_report(
    index: _WorkspaceIndex,
    action: DeploymentAction,
    definition: dict[str, Any],
) -> dict[str, Any]:
    """
    Point a report's definition to its semantic model by ID.

    In Git, ``definition.pbir`` refers to the semantic model by the path of
    its folder (``byPath``), which the Fabric API does not accept. Such a
    reference is sent as a connection to the ID of that model in the
    workspace, created earlier in the run or already there. The file itself
    is left alone, and any other reference goes as it is.

    Raises:
        ConfigurationError: If the path does not lead to a semantic model
            of the source, or the workspace has no such model.
    """
    parts: list[dict[str, Any]] = definition.get("parts", [])
    position = next(
        (
            n
            for n, part in enumerate(parts)
            if part["path"] == "definition.pbir"
        ),
        None,
    )
    if position is None:
        return definition
    try:
        pbir = json.loads(base64.b64decode(parts[position]["payload"]))
    except (KeyError, TypeError, ValueError):
        # Fabric refuses it with a reason of its own.
        return definition
    reference = (
        pbir.get("datasetReference") if isinstance(pbir, dict) else None
    )
    by_path = reference.get("byPath") if isinstance(reference, dict) else None
    path = by_path.get("path") if isinstance(by_path, dict) else None
    if not isinstance(path, str):
        return definition

    folder = os.path.normpath(os.path.join(action.source_path, path))
    if Path(folder).suffix != ".SemanticModel":
        raise ConfigurationError(
            f"definition.pbir points to {path}, which is not a semantic "
            "model folder."
        )
    try:
        model_name = _read_display_name(folder)
    except ConfigurationError as e:
        raise ConfigurationError(
            f"definition.pbir points to {path}: {e}"
        ) from e
    model_id = (index.items.get(("SemanticModel", model_name)) or {}).get("id")
    if not model_id:
        raise ConfigurationError(
            f"definition.pbir points to {path}, but the workspace has no "
            f"semantic model {model_name}."
        )

    pbir["datasetReference"] = {
        "byConnection": {"connectionString": f"semanticmodelid={model_id}"}
    }
    bound = {
        **parts[position],
        "payload": base64.b64encode(
            json.dumps(pbir, indent=2).encode("utf-8")
        ).decode("ascii"),
    }
    logger.info(
        f"{action.display_name}.Report: definition.pbir points to {path}, "
        f"sent as a connection to semantic model {model_name}."
    )
    return {
        **definition,
        "parts": [*parts[:position], bound, *parts[position + 1 :]],
    }


def _create_planned_item(
    index: _WorkspaceIndex,
    action: DeploymentAction,
    definition: dict[str, Any],
    folder_id: str | None,
) -> str | None:
    """
    Create the item of a CREATE action and add it to the index.

    While Fabric has not freed the name of an item deleted moments ago, the
    create is tried again: that answer means nothing was created.
    """
    item_type, display_name = _identity(action)
    for attempt in range(1, _NAME_WAIT_ATTEMPTS + 1):
        created = _request_create_item(
            index.workspace_id,
            display_name=display_name,
            item_type=item_type,
            item_definition=definition,
            folder_id=folder_id,
        )
        if (
            created.success
            or _NAME_NOT_AVAILABLE not in (created.error or "")
            or attempt == _NAME_WAIT_ATTEMPTS
        ):
            break
        logger.warning(
            f"{display_name}.{item_type}: Fabric has not freed the name of "
            f"a deleted item yet; trying again in {_NAME_WAIT_SECONDS:g}s "
            f"(attempt {attempt}/{_NAME_WAIT_ATTEMPTS - 1})."
        )
        time.sleep(_NAME_WAIT_SECONDS)
    _raise_for_failure(created, "Create")
    item_id: str | None = (created.data or {}).get("id")
    index.items[(item_type, display_name)] = {
        "id": item_id,
        "folderId": folder_id,
    }
    return item_id


def _delete_planned_item(
    index: _WorkspaceIndex, action: DeploymentAction
) -> str:
    """
    Delete the item of a DELETE action and drop it from the index.

    An item no longer in the workspace, as when someone deleted it since it
    was listed, counts as deleted.
    """
    existing = _planned_target(index, action)
    item_id = cast(str, existing["id"])
    result = _request_delete_item(index.workspace_id, item_id)
    if result.status_code == 404:
        logger.info(
            f"{action.display_name}.{action.item_type} was already gone from "
            "the workspace."
        )
    else:
        _raise_for_failure(result, "Delete")
    del index.items[_identity(action)]
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
    index: _WorkspaceIndex,
    action: DeploymentAction,
    *,
    allow_deletions: bool = False,
) -> DeploymentResult:
    """Execute one planned action and report the outcome."""
    if action.action is DeploymentActionType.BLOCKED:
        return _action_result(action, "failed", error=action.detail)
    if action.action is DeploymentActionType.DELETE and not allow_deletions:
        return _action_result(
            action,
            "failed",
            error=(
                "Deletions are not allowed in this run: "
                f"{action.display_name}.{action.item_type} stays in the "
                "workspace."
            ),
        )

    started = time.monotonic()
    item_id: str | None = None
    moved = False
    outcome: DeploymentOutcome

    try:
        if action.action is DeploymentActionType.CREATE:
            definition = _definition_to_send(index, action)
            folder_id = index.ensure_folder(action.folder_path)
            item_id = _create_planned_item(
                index, action, definition, folder_id
            )
            outcome = "created"
        elif action.action is DeploymentActionType.UPDATE:
            # Check the target before the first change to the workspace.
            existing = _planned_target(index, action)
            definition = _definition_to_send(index, action)
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
        elif action.action is DeploymentActionType.DELETE:
            item_id = _delete_planned_item(index, action)
            outcome = "deleted"
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
    elif result.action == "skipped":
        why = f": {result.error}" if result.error else "."
        logger.warning(f"{_label(result)} skipped{why}")
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
            f"{counts['updated']} updated, {counts['moved']} moved, "
            f"{counts['deleted']} deleted) in "
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
    definition, deletes the items planned as DELETE, and reports BLOCKED
    items as failed, creating missing folders on the way. A NOOP gets a log
    line but no result. An item to create, update or move is skipped when
    an item of its ``needs`` failed or was skipped, so nothing is deployed
    without what it needs. A deletion is refused, and reported as failed,
    unless ``allow_deletions`` is set; it is skipped when any action before
    it failed or was skipped. A report that points to its semantic model by
    path is sent with a connection to the model's ID in the workspace
    instead, since the Fabric API accepts no path. Used by
    ``deploy_all_items``; not exported from ``pyfabricops`` yet.

    Args:
        index (_WorkspaceIndex): The workspace items and folders the plan was
            built from.
        fail_fast (bool, optional): Stop at the first failed action and
            report the remaining ones as skipped. Defaults to False.
        allow_deletions (bool, optional): Delete the items planned as
            DELETE. Defaults to False: each is reported as failed and left
            in the workspace.
    """

    def __init__(
        self,
        index: _WorkspaceIndex,
        *,
        fail_fast: bool = False,
        allow_deletions: bool = False,
    ) -> None:
        self._index = index
        self._fail_fast = fail_fast
        self._allow_deletions = allow_deletions

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
        # Each item of the run that was not deployed, as a detail for what
        # needs it: "Name.Type, which failed".
        not_deployed: dict[tuple[str, str], str] = {}
        # Whether every action so far succeeded, which a deletion needs.
        clean = True
        for position, action in enumerate(plan.actions):
            if action.action is DeploymentActionType.NOOP:
                _log_noop(action)
                continue

            unmet = [key for key in action.needs if key in not_deployed]
            if unmet and action.action in _APPLIED:
                result = _action_result(
                    action, "skipped", error=f"Needs {not_deployed[unmet[0]]}."
                )
            elif action.action is DeploymentActionType.DELETE and not clean:
                result = _action_result(
                    action,
                    "skipped",
                    error="Not deleted: an item before it failed or was "
                    "skipped.",
                )
            else:
                result = _apply_action(
                    self._index,
                    action,
                    allow_deletions=self._allow_deletions,
                )
            results.append(result)
            _log_result(result)
            which = _NOT_DEPLOYED.get(result.action)
            if which is not None:
                clean = False
                if action.display_name:
                    not_deployed[_identity(action)] = (
                        f"{_label(result)}, which {which}"
                    )

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
        deletions=_read_deletions(path, items, index),
    )
    return planner.plan(
        items, available=dependencies.available if dependencies else ()
    )


def _reconcile_all(
    workspace: str,
    path: str,
    *,
    start_path: str | None = None,
    item_types: Sequence[str] | None = None,
    state_backend: DeploymentStateBackend | None = None,
    environment: str | None = None,
) -> Reconciliation:
    """
    Compare every local item in scope with the workspace, and report.

    Only reads happen: the local items, one listing of the workspace, the
    definition of each item found on both sides, and the deployment state
    when there is one. See ``reconcile_items`` for the public contract.

    Raises:
        ConfigurationError: If the workspace is not found, or the state is
            invalid.
        RequestError: If its items and folders cannot be listed.
    """
    types = _ordered_types(item_types)
    # Every local item, whatever the scope: what the source holds is never
    # unmanaged.
    local = _read_source_items(
        _find_local_items(path, DEPLOY_ORDER), start_path=start_path
    )
    items = _in_deployment_order(
        [item for item in local if item.item_type in types], types
    )
    deployed = _deployed_items(
        state_backend,
        environment=environment or workspace,
        workspace=workspace,
    )
    if deployed:
        items = _with_content_hashes(items)

    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        raise ConfigurationError(f"Workspace '{workspace}' not found.")
    index = _WorkspaceIndex.load(workspace_id)
    if index is None:
        raise RequestError(
            f"Could not list the items and folders of workspace '{workspace}'."
        )

    folder_paths = {
        folder_id: folder for folder, folder_id in index.folders.items()
    }
    listed = [
        WorkspaceItem(
            item_type,
            display_name,
            # An item at the root has no folder ID.
            folder_paths.get(entry.get("folderId") or ""),
        )
        for (item_type, display_name), entry in index.items.items()
    ]
    differences, unchecked = _compare_definitions(index, items)
    reconciliation = reconcile(
        items,
        listed,
        differences=differences,
        unchecked=unchecked,
        deployed=deployed,
        source_keys={
            (item.item_type, item.display_name)
            for item in local
            if item.display_name is not None
        },
        deployable_types=DEPLOY_ORDER,
        root=path,
    )
    _log_reconciliation(workspace, reconciliation)
    return reconciliation


def _deployed_items(
    backend: DeploymentStateBackend | None, *, environment: str, workspace: str
) -> dict[ItemKey, DeployedItem]:
    """What the last successful deployment sent, from the state if any."""
    if backend is None:
        return {}
    state = backend.load(environment)
    if state is None:
        logger.info(
            f"No deployment state '{environment}': every difference counts "
            "as drift."
        )
        return {}
    if not state.targets(workspace):
        logger.warning(
            f"Deployment state '{environment}' was recorded for workspace "
            f"'{state.workspace}', not '{workspace}'; ignoring it."
        )
        return {}
    return dict(state.items)


def _compare_definitions(
    index: _WorkspaceIndex, items: Sequence[SourceItem]
) -> tuple[dict[ItemKey, tuple[str, ...]], dict[ItemKey, str]]:
    """
    Compare the definition of each local item the workspace has.

    Returns the parts that differ for each item compared, empty when it
    matches, and why each of the others could not be compared.
    """
    models = {
        str(entry["id"]).lower(): display_name
        for (item_type, display_name), entry in index.items.items()
        if item_type == "SemanticModel"
    }
    differences: dict[ItemKey, tuple[str, ...]] = {}
    unchecked: dict[ItemKey, str] = {}
    for item in items:
        if item.error is not None or item.display_name is None:
            continue
        key = (item.item_type, item.display_name)
        target = index.items.get(key)
        if target is None or key in differences or key in unchecked:
            continue

        result = _request_item_definition(
            index.workspace_id, cast(str, target["id"])
        )
        found = (
            (result.data or {}).get("definition") if result.success else None
        )
        if not isinstance(found, dict):
            unchecked[key] = (
                "Fabric returned no definition."
                if result.success
                else f"Fabric returned no definition: {_describe_error(result)}."
            )
            continue
        try:
            desired = pack_item_definition(item.source_path)
        except (PyFabricOpsError, OSError) as e:
            unchecked[key] = f"Its definition could not be read: {e}"
            continue

        report = item.item_type == "Report"
        differences[key] = differing_parts(
            comparable_parts(
                desired,
                semantic_model=(
                    _report_model(desired, item.source_path, models)
                    if report
                    else None
                ),
            ),
            comparable_parts(
                found,
                semantic_model=(
                    _report_model(found, None, models) if report else None
                ),
            ),
        )
    return differences, unchecked


def _report_model(
    definition: Mapping[str, Any],
    report_folder: str | None,
    models: Mapping[str, str],
) -> str | None:
    """
    Name the semantic model a report's ``definition.pbir`` points to.

    By path, the display name of the model folder; by connection, the
    workspace model with that ID, else the ``initial catalog``. None when
    the reference cannot be read, so that it is compared as it is.
    """
    pbirs = [
        part["payload"]
        for part in definition.get("parts", [])
        if part.get("path") == "definition.pbir"
    ]
    try:
        pbir = json.loads(base64.b64decode(pbirs[0])) if pbirs else None
    except (TypeError, ValueError):
        return None
    reference = (
        pbir.get("datasetReference") if isinstance(pbir, dict) else None
    )
    if not isinstance(reference, dict):
        return None

    by_path = reference.get("byPath")
    path = by_path.get("path") if isinstance(by_path, dict) else None
    if isinstance(path, str) and report_folder is not None:
        try:
            return _read_display_name(
                os.path.normpath(os.path.join(report_folder, path))
            )
        except ConfigurationError:
            return None

    by_connection = reference.get("byConnection")
    connection = (
        by_connection.get("connectionString")
        if isinstance(by_connection, dict)
        else None
    )
    if not isinstance(connection, str):
        return None
    settings = {
        name.strip().lower(): value.strip()
        for name, _, value in (
            setting.partition("=") for setting in connection.split(";")
        )
    }
    model_id = settings.get("semanticmodelid", "").lower()
    if model_id in models:
        return models[model_id]
    return settings.get("initial catalog") or None


def _log_reconciliation(
    workspace: str, reconciliation: Reconciliation
) -> None:
    """Log what a reconciliation found, in one line."""
    if reconciliation.ok:
        logger.log(
            SUCCESS_LEVEL,
            f"Workspace '{workspace}' matches the source: "
            f"{len(reconciliation.in_sync)} item(s) in sync.",
        )
        return
    logger.warning(
        f"Workspace '{workspace}' differs from the source: "
        f"{len(reconciliation.plan.actions)} item(s) to bring back, "
        f"{len(reconciliation.unmanaged)} unmanaged."
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


@dataclass(frozen=True)
class _Deletions:
    """What stays in the source, for the items a run would delete."""

    # Every item of the source, with its folder.
    source: Mapping[ItemKey, str]
    # For each item to delete, what still refers to it, and how.
    referenced_by: Mapping[ItemKey, tuple[str, ...]]


def _read_deletions(
    path: str, items: Sequence[SourceItem], index: _WorkspaceIndex
) -> _Deletions | None:
    """
    Read what stays in the source, when the run has an item to delete.

    Nothing is read unless an item deleted from the source is still in the
    workspace. Then every local item is listed, so that an item the source
    still defines elsewhere is kept, and what still refers to an item to
    delete is found: by the references the dependency scan reads, checked
    against the item as it was at the baseline commit, and by the ID of the
    item in the workspace (for a lakehouse, its SQL analytics endpoint's
    too) in the files of the items that stay.
    """
    candidates = {
        (item.item_type, item.display_name): item
        for item in items
        if item.change is SourceChange.DELETED
        and item.error is None
        and item.display_name is not None
        and (item.item_type, item.display_name) in index.items
    }
    if not candidates:
        return None

    catalog = LocalCatalog.read(path, DEPLOY_ORDER)
    source = {entry.key: entry.path for entry in catalog}
    gone = {key: item for key, item in candidates.items() if key not in source}
    if not gone:
        return _Deletions(source=source, referenced_by={})

    # For each item to delete, each item that refers to it, and how.
    referrers: dict[ItemKey, dict[ItemKey, str]] = {}
    scan = scan_references(
        LocalCatalog(
            [
                *catalog,
                *(
                    CatalogItem(key, item.source_path, item.logical_id)
                    for key, item in gone.items()
                ),
            ]
        ),
        list(source),
    )
    for dependency in scan.dependencies:
        if dependency.target in gone:
            referrers.setdefault(dependency.target, {}).setdefault(
                dependency.source, dependency.via
            )

    ids: dict[str, tuple[ItemKey, str]] = {}
    for key in gone:
        owned = [(index.items[key], "its ID")]
        # Fabric deletes a lakehouse's SQL analytics endpoint with it.
        endpoint = (
            index.items.get(("SQLEndpoint", key[1]))
            if key[0] == "Lakehouse"
            else None
        )
        if endpoint is not None:
            owned.append((endpoint, "the ID of its SQL analytics endpoint"))
        for entry, what in owned:
            item_id = _normal_id(str(entry["id"]))
            if item_id is not None:
                ids[item_id] = (key, what)
    if ids:
        for local in catalog:
            for item_id, file in _ids_in(local.path, ids).items():
                key, what = ids[item_id]
                referrers.setdefault(key, {}).setdefault(
                    local.key, f"{what}, in {file}"
                )

    return _Deletions(
        source=source,
        referenced_by={
            key: tuple(
                f"{name}.{item_type} ({how})"
                for (item_type, name), how in found.items()
            )
            for key, found in referrers.items()
        },
    )


def _ids_in(folder: str, ids: Collection[str]) -> dict[str, str]:
    """Find which IDs the files of an item folder hold, and the first file."""
    base = Path(folder)
    found: dict[str, str] = {}
    for file in sorted(p for p in base.rglob("*") if p.is_file()):
        try:
            content = file.read_bytes().lower()
        except OSError:
            continue
        for item_id in ids:
            if item_id not in found and item_id.encode() in content:
                found[item_id] = file.relative_to(base).as_posix()
    return found


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
    deletions: _Deletions | None = None,
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
        source=deletions.source if deletions else None,
        referenced_by=deletions.referenced_by if deletions else None,
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
        deletions=(
            _read_deletions(root, items, index) if root is not None else None
        ),
    )
    plan = planner.plan(
        items, available=dependencies.available if dependencies else ()
    )

    executor = DeploymentExecutor(index, fail_fast=fail_fast)
    report.results.extend(executor.apply(plan))

    _log_report(report)
    return report
