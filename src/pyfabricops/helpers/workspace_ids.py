"""
The IDs of one workspace translated into those of another.

Fabric Git integration writes the items of a workspace with the IDs of that
workspace: the default lakehouse of a notebook, the OneLake path of a Direct
Lake model, the items a pipeline runs, the target of a shortcut. Sent as
they are to another workspace, such as PRD from the repository of DEV, they
would read and write the first one.

``WorkspaceIdMap`` maps each ID of the source workspace to the ID of the
item of the same type and display name in the target, by its ID and by its
logical ID, and the source workspace to the target, as well as the query
URI of each eventhouse and the SQL endpoint of the workspace, which items
hold as text. ``translate()`` puts the
IDs of the target in a copy of the items, such as the staging copy a
deployment sends; ``references()`` tells what an item still refers to in the
source, so that a run deploys first the items the others refer to, and
stops before it sends an item that would still refer to the source.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from ..api.api import ApiResult, api_request
from ..core.workspaces import resolve_workspace
from ..items.items import list_items
from ..utils.exceptions import RequestError, ResourceNotFoundError
from ..utils.logging import get_logger
from ..utils.utils import CHILDREN_FOLDER, find_and_replace
from .dependencies import _read_platform
from .dependency_graph import ItemKey

__all__ = ["IdReferences", "WorkspaceIdMap"]

logger = get_logger(__name__)

# The empty GUID, which Fabric writes for "this workspace".
THIS_WORKSPACE = "00000000-0000-0000-0000-000000000000"
# The shortcuts of a lakehouse, which get the IDs of the target one by one.
_SHORTCUTS = "shortcuts.metadata.json"
# The files that get the IDs of the target as text: all but the shortcuts, a
# .platform, which holds the identity of its item, and the files of the
# variable libraries, whose value sets hold the IDs of each environment.
_MAPPED = (
    r"^(?!.*\.VariableLibrary[\\/])(?!.*shortcuts\.metadata\.json$)"
    r".*(?<!\.platform)$"
)
# In pipelines and notebooks, the empty GUID of a workspace gets the target.
_REFERRERS = r"(pipeline-content\.json|notebook-content\.\w+)$"
_EMPTY_WORKSPACE = (
    r'("(?:workspaceId|default_lakehouse_workspace_id)"\s*:\s*")'
    + THIS_WORKSPACE
    + r'(")'
)
# The item types whose endpoints other items hold as text, the collection
# of the API that reads them, and where each endpoint is in its properties:
# the query and ingestion URIs of an eventhouse, which a KQL database's
# queryset or an ontology's binding holds, and the SQL endpoint of the
# workspace, which an ontology's or a model's expressions hold.
_ENDPOINTS: dict[str, tuple[str, tuple[tuple[str, ...], ...]]] = {
    "Eventhouse": (
        "eventhouses",
        (("queryServiceUri",), ("ingestionServiceUri",)),
    ),
    "Lakehouse": (
        "lakehouses",
        (("sqlEndpointProperties", "connectionString"),),
    ),
    "Warehouse": ("warehouses", (("connectionString",),)),
}
# The endpoints every item of a workspace shares: one pair is enough.
_WORKSPACE_ENDPOINTS = frozenset({"Lakehouse", "Warehouse"})

# Reads the endpoints of an item of a workspace, in the order of _ENDPOINTS;
# an endpoint not provisioned yet is empty.
EndpointReader = Callable[[str, Mapping[str, Any]], Sequence[str]]


@dataclass(frozen=True)
class IdReferences:
    """
    What an item still refers to in the source workspace.

    Attributes:
        missing (frozenset[ItemKey]): The items of the source it refers to
            by ID that the target lacks yet, by type and display name.
        source_workspace (bool): Whether it refers to the source workspace
            itself, which no item of the target may.
    """

    missing: frozenset[ItemKey]
    source_workspace: bool

    @property
    def ok(self) -> bool:
        """Whether the item refers to nothing of the source."""
        return not self.missing and not self.source_workspace


class WorkspaceIdMap:
    """
    The ID in the target workspace of each ID of the source workspace.

    An item of the source workspace maps to the item of the same type and
    display name in the target, by its ID and by its logical ID, and so does
    each logical ID of ``logical_ids``, such as those of the ``.platform``
    files of the repository. The source workspace maps to the target. An ID
    whose item the target lacks maps to nothing until the target is listed
    again with ``reload_target()``.

    With ``endpoint_reader``, as ``load()`` gives it, the endpoints items
    hold as text map too: the query and ingestion URIs of an eventhouse to
    those of the eventhouse of the same name in the target, and the SQL
    endpoint of the source workspace, which its lakehouses and warehouses
    share, to that of the target.

    IDs are compared in lowercase, as Fabric returns them.

    Args:
        source_workspace_id (str): The ID of the workspace whose IDs the
            items hold, such as the one connected to the repository.
        target_workspace_id (str): The ID of the workspace to deploy to.
        source_items (Iterable[Mapping[str, Any]]): The items of the source
            workspace, as ``list_items(df=False)`` returns them.
        target_items (Iterable[Mapping[str, Any]]): The items of the target
            workspace, likewise.
        logical_ids (Mapping[str, ItemKey], optional): More logical IDs of
            the source, with the type and display name of their item.
        endpoint_reader (EndpointReader, optional): Reads the endpoints of
            an eventhouse, a lakehouse or a warehouse of a workspace.
            Defaults to none: no endpoint maps.

    Examples:
        ```python
        ids = WorkspaceIdMap.load("Sales-DEV", "Sales-PRD", staging)
        ids.translate(staging)
        for key, path in items:
            if not ids.references(key, path).ok:
                ...
        ```
    """

    def __init__(
        self,
        source_workspace_id: str,
        target_workspace_id: str,
        *,
        source_items: Iterable[Mapping[str, Any]],
        target_items: Iterable[Mapping[str, Any]],
        logical_ids: Mapping[str, ItemKey] | None = None,
        endpoint_reader: EndpointReader | None = None,
    ) -> None:
        self._source = source_workspace_id.lower()
        self._target = target_workspace_id
        known: dict[str, ItemKey] = {}
        self._source_items: dict[ItemKey, Mapping[str, Any]] = {}
        for item in source_items:
            key = (str(item["type"]), str(item["displayName"]))
            self._source_items[key] = item
            for value in (item.get("id"), item.get("logicalId")):
                if value:
                    known[str(value).lower()] = key
        for logical_id, key in (logical_ids or {}).items():
            known[logical_id.lower()] = key
        self._known = known
        self._target_items: dict[ItemKey, Mapping[str, Any]] = {}
        self._missing: dict[str, ItemKey] = {}
        # Each shortcuts file translated, as it was before the first time.
        self._shortcuts: dict[Path, str] = {}
        self._endpoint_reader = endpoint_reader
        # The endpoints read, by workspace and item ID; never an empty one.
        self._endpoint_cache: dict[tuple[str, str], tuple[str, ...]] = {}
        self._endpoints: dict[str, str] = {}
        self._missing_endpoints: dict[str, ItemKey] = {}
        self._set_target(target_items)

    @classmethod
    def load(
        cls,
        source_workspace: str,
        target_workspace: str,
        path: str | os.PathLike[str] | None = None,
    ) -> WorkspaceIdMap:
        """
        List both workspaces, and read the logical IDs under a folder.

        The endpoints of the eventhouses, lakehouses and warehouses of both
        are read too, as the map needs them.

        Args:
            source_workspace (str): The source workspace, by name or ID.
            target_workspace (str): The target workspace, by name or ID.
            path (str | PathLike, optional): A folder of items, such as the
                repository or its staging copy, whose ``.platform`` files
                give more logical IDs of the source.

        Returns:
            WorkspaceIdMap: The map between the two workspaces.

        Raises:
            ResourceNotFoundError: If a workspace is not found, or the
                identity cannot see it.
            RequestError: If the items of a workspace cannot be listed.
        """
        source = _require_workspace(source_workspace)
        target = _require_workspace(target_workspace)
        return cls(
            source,
            target,
            source_items=_list_workspace(source),
            target_items=_list_workspace(target),
            logical_ids=_read_logical_ids(path) if path is not None else None,
            endpoint_reader=_fetch_endpoints,
        )

    @property
    def source_workspace_id(self) -> str:
        """The ID of the source workspace, in lowercase."""
        return self._source

    @property
    def target_workspace_id(self) -> str:
        """The ID of the target workspace."""
        return self._target

    @property
    def target_items(self) -> Mapping[ItemKey, Mapping[str, Any]]:
        """The items of the target, by type and display name."""
        return MappingProxyType(self._target_items)

    @property
    def missing(self) -> Mapping[str, ItemKey]:
        """The IDs of the source whose item the target lacks yet."""
        return MappingProxyType(self._missing)

    @property
    def endpoints(self) -> Mapping[str, str]:
        """The endpoint in the target of each endpoint of the source."""
        return MappingProxyType(self._endpoints)

    def reload_target(self) -> None:
        """
        List the target again, for the items deployed since.

        Raises:
            RequestError: If the items of the target cannot be listed.
        """
        self._set_target(_list_workspace(self._target))

    def translate(self, path: str | os.PathLike[str]) -> None:
        """
        Put the IDs of the target in the items under a folder.

        The folder is changed in place, so give it a copy of the items, such
        as the staging copy of ``copy_to_staging()``. It can be translated
        again after ``reload_target()``: the shortcuts are translated from
        what they were the first time, and an ID already translated is
        left as it is. An ID whose item the target lacks stays, which
        ``references()`` reports.

        Args:
            path (str | PathLike): The folder of the items.
        """
        root = Path(path)
        # Endpoints first, before an ID inside one could change it.
        replacements = {
            (_MAPPED, "(?i)" + re.escape(old)): new
            for old, new in self._endpoints.items()
        }
        replacements[(_MAPPED, "(?i)" + re.escape(self._source))] = (
            self._target
        )
        for old, key in self._known.items():
            if key in self._target_items:
                new = str(self._target_items[key]["id"])
                replacements[(_MAPPED, "(?i)" + re.escape(old))] = new
        replacements[(_REFERRERS, _EMPTY_WORKSPACE)] = (
            rf"\g<1>{self._target}\g<2>"
        )
        find_and_replace(str(root), replacements)
        for file in sorted(root.glob(f"**/*.Lakehouse/{_SHORTCUTS}")):
            text = self._shortcuts.setdefault(
                file.resolve(), file.read_text(encoding="utf-8-sig")
            )
            pointed = [self.point_shortcut(s) for s in json.loads(text)]
            file.write_text(json.dumps(pointed, indent=2), encoding="utf-8")

    def point_shortcut(self, shortcut: Mapping[str, Any]) -> dict[str, Any]:
        """
        A OneLake shortcut to an item of the source workspace, pointed at the
        same item in the target.

        Fabric looks the logical ID of a shortcut to its own workspace up
        among the items of the workspace, so the shortcut gets the logical ID
        of the item in the target; the ID of the item, with the ID of the
        target workspace, when the item has none. Any other shortcut stays as
        it is, as does one to an item the target lacks yet: the lakehouse
        waits for it.

        Args:
            shortcut (Mapping[str, Any]): A shortcut of
                ``shortcuts.metadata.json``.

        Returns:
            dict[str, Any]: The shortcut, pointed at the target, as a copy.
        """
        pointed: dict[str, Any] = json.loads(json.dumps(shortcut))
        one_lake = pointed.get("target", {}).get("oneLake")
        if not isinstance(one_lake, dict):
            return pointed
        workspace = str(one_lake.get("workspaceId", "")).lower()
        key = self._known.get(str(one_lake.get("itemId", "")).lower())
        target = self._target_items.get(key) if key else None
        if workspace not in (THIS_WORKSPACE, self._source) or target is None:
            return pointed
        if target.get("logicalId"):
            one_lake.update(
                workspaceId=THIS_WORKSPACE, itemId=str(target["logicalId"])
            )
        else:
            one_lake.update(workspaceId=self._target, itemId=str(target["id"]))
        return pointed

    def references(
        self, key: ItemKey, path: str | os.PathLike[str]
    ) -> IdReferences:
        """
        What an item, translated or not, still refers to in the source.

        A variable library refers to nothing: its value sets hold the IDs
        of each environment, which ``translate()`` leaves as they are. Nor
        does an item to itself. The items nested in its ``.children``
        folder, such as the KQL databases of an eventhouse, are items of
        their own: what they refer to is not the item's.

        Args:
            key (ItemKey): The type and display name of the item.
            path (str | PathLike): The folder of the item.

        Returns:
            IdReferences: The items of the source the target lacks that it
                refers to by ID, and whether it refers to the source
                workspace.
        """
        found: set[ItemKey] = set()
        workspace = False
        if key[0] == "VariableLibrary":
            return IdReferences(frozenset(), False)
        root = Path(path)
        files = sorted(
            p
            for p in root.rglob("*")
            if p.is_file() and p.relative_to(root).parts[0] != CHILDREN_FOLDER
        )
        for file in files:
            if file.name == ".platform":
                continue
            text = file.read_text(encoding="utf-8", errors="replace").lower()
            found |= {k for old, k in self._missing.items() if old in text}
            found |= {
                k for old, k in self._missing_endpoints.items() if old in text
            }
            workspace = workspace or self._source in text
        found.discard(key)
        return IdReferences(frozenset(found), workspace)

    def _set_target(self, items: Iterable[Mapping[str, Any]]) -> None:
        """Take the items of the target, and what it lacks of the source."""
        self._target_items = {
            (str(item["type"]), str(item["displayName"])): item
            for item in items
        }
        self._missing = {
            old: key
            for old, key in self._known.items()
            if key not in self._target_items
        }
        if self._endpoint_reader is not None:
            self._map_endpoints()

    def _map_endpoints(self) -> None:
        """
        Pair the endpoints of the source with those of the target.

        An eventhouse the target lacks leaves its endpoints missing, as an
        ID is, until the target has it. The SQL endpoint the lakehouses and
        warehouses of a workspace share takes one pair.
        """
        endpoints: dict[str, str] = {}
        missing: dict[str, ItemKey] = {}
        shared = False
        for key, item in self._source_items.items():
            if key[0] not in _ENDPOINTS:
                continue
            target = self._target_items.get(key)
            workspace_wide = key[0] in _WORKSPACE_ENDPOINTS
            if workspace_wide and (shared or target is None):
                continue
            source = self._read_endpoints(self._source, item)
            if target is None:
                missing.update(dict.fromkeys((e.lower() for e in source), key))
                continue
            pairs = [
                (old, new)
                for old, new in zip(
                    source,
                    self._read_endpoints(self._target, target),
                    strict=True,
                )
                if old and new
            ]
            endpoints.update(
                (old, new) for old, new in pairs if old.lower() != new.lower()
            )
            shared = shared or (workspace_wide and bool(pairs))
        self._endpoints = endpoints
        self._missing_endpoints = {
            old: key for old, key in missing.items() if old
        }

    def _read_endpoints(
        self, workspace_id: str, item: Mapping[str, Any]
    ) -> tuple[str, ...]:
        """The endpoints of an item, read once each once provisioned."""
        cache_key = (workspace_id.lower(), str(item["id"]).lower())
        cached = self._endpoint_cache.get(cache_key)
        if cached is not None:
            return cached
        assert self._endpoint_reader is not None
        found = tuple(
            str(e or "") for e in self._endpoint_reader(workspace_id, item)
        )
        if all(found):
            self._endpoint_cache[cache_key] = found
        return found


def _require_workspace(workspace: str) -> str:
    """The ID of a workspace, given by name or ID."""
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        raise ResourceNotFoundError(
            f"Workspace '{workspace}' not found, or the identity has no "
            "access to it."
        )
    return str(workspace_id)


def _fetch_endpoints(
    workspace_id: str, item: Mapping[str, Any]
) -> tuple[str, ...]:
    """
    Read the endpoints of an item from its properties, as ``_ENDPOINTS``
    names them; all empty when it cannot be read.
    """
    collection, paths = _ENDPOINTS[str(item["type"])]
    result = cast(
        ApiResult,
        api_request(
            f"/workspaces/{workspace_id}/{collection}/{item['id']}",
            return_result=True,
        ),
    )
    if not result.success:
        logger.warning(
            f"Could not read the endpoints of {item['displayName']}."
            f"{item['type']}: {result.error}"
        )
        return tuple("" for _ in paths)
    properties = (result.data or {}).get("properties") or {}
    found: list[str] = []
    for path in paths:
        value: Any = properties
        for name in path:
            value = value.get(name) if isinstance(value, dict) else None
        found.append(value if isinstance(value, str) else "")
    return tuple(found)


def _list_workspace(workspace_id: str) -> list[dict[str, Any]]:
    """The items of a workspace, as the API returns them."""
    items = list_items(workspace_id, df=False)
    if items is None:
        raise RequestError(
            f"Could not list the items of workspace '{workspace_id}'."
        )
    return list(items)


def _read_logical_ids(path: str | os.PathLike[str]) -> dict[str, ItemKey]:
    """The logical ID of each item under a folder, from its ``.platform``."""
    logical_ids: dict[str, ItemKey] = {}
    for platform in sorted(Path(path).rglob(".platform")):
        folder = platform.parent
        identity = _read_platform(str(folder))
        item_type = folder.suffix[1:]
        if identity is None or not item_type:
            continue
        display_name, logical_id = identity
        if logical_id is not None:
            logical_ids[logical_id] = (item_type, display_name)
    return logical_ids
