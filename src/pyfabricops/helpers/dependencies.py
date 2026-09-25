"""
References between local items, read from their definitions.

``LocalCatalog`` lists the items under a folder with the identity the
planner uses (item type and display name), their folder and their logical
ID. ``scan_references`` reads the definitions of the selected items, and of
the items they need, and turns each reference into a ``Dependency`` on a
local item, or into a broken reference when the definition points to a local
item that is not there. A reference to something outside the source, such as
a semantic model of another workspace, is left out: it is neither deployed
nor blocking.

References read:

- Report → SemanticModel: ``datasetReference`` in ``definition.pbir``, by
  path, or by connection through the ``initial catalog`` of the connection
  string.
"""

from __future__ import annotations

import json
import os
import re
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeAlias

from ..utils.utils import list_paths_of_type
from .dependency_graph import Dependency, ItemKey

__all__ = ["CatalogItem", "LocalCatalog", "ReferenceScan", "scan_references"]


@dataclass(frozen=True)
class CatalogItem:
    """
    A local item that references can point to.

    Attributes:
        key (ItemKey): Its item type, from the folder suffix, and its
            display name, from ``.platform``.
        path (str): Its folder.
        logical_id (str | None): ``config.logicalId`` from ``.platform``.
    """

    key: ItemKey
    path: str
    logical_id: str | None = None


class LocalCatalog:
    """
    The local items that references can point to.

    Args:
        items (Iterable[CatalogItem]): The items. When two share a type and
            display name, or a folder, the first one is kept.
    """

    def __init__(self, items: Iterable[CatalogItem]) -> None:
        self._by_key: dict[ItemKey, CatalogItem] = {}
        self._by_folder: dict[str, CatalogItem] = {}
        for item in items:
            self._by_key.setdefault(item.key, item)
            self._by_folder.setdefault(_folder_id(item.path), item)

    @classmethod
    def read(cls, path: str, item_types: Sequence[str]) -> LocalCatalog:
        """
        List the items of the given types under a folder.

        An item whose ``.platform`` cannot be read is left out; the planner
        reports it when it is selected.

        Args:
            path (str): The folder of the items.
            item_types (Sequence[str]): The item types to list.

        Returns:
            LocalCatalog: The items found.
        """
        items: list[CatalogItem] = []
        for item_type in item_types:
            for item_path in sorted(
                str(p) for p in list_paths_of_type(path, item_type)
            ):
                identity = _read_platform(item_path)
                if identity is not None:
                    display_name, logical_id = identity
                    items.append(
                        CatalogItem(
                            (item_type, display_name), item_path, logical_id
                        )
                    )
        return cls(items)

    def get(self, key: ItemKey) -> CatalogItem | None:
        """
        Return the item with a type and display name.

        Args:
            key (ItemKey): The item type and display name.

        Returns:
            CatalogItem | None: The item, or None when there is none.
        """
        return self._by_key.get(key)

    def at(self, folder: str) -> CatalogItem | None:
        """
        Return the item in a folder.

        Args:
            folder (str): The folder, in any form that points to it.

        Returns:
            CatalogItem | None: The item, or None when there is none.
        """
        return self._by_folder.get(_folder_id(folder))


@dataclass(frozen=True)
class ReferenceScan:
    """
    The references found from a selection of items.

    Attributes:
        dependencies (tuple[Dependency, ...]): The references to local items.
        broken (Mapping[ItemKey, tuple[str, ...]]): For each item whose
            definition points to a local item that is not there, why.
            Read-only.
    """

    dependencies: tuple[Dependency, ...] = ()
    broken: Mapping[ItemKey, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "broken", MappingProxyType(dict(self.broken)))


def scan_references(
    catalog: LocalCatalog, keys: Iterable[ItemKey]
) -> ReferenceScan:
    """
    Read the references of the given items and of every item they need.

    Args:
        catalog (LocalCatalog): The local items.
        keys (Iterable[ItemKey]): The items to start from. An item not in
            the catalog, or of a type whose references are not read, gives
            none.

    Returns:
        ReferenceScan: What the items refer to.
    """
    dependencies: list[Dependency] = []
    broken: dict[ItemKey, tuple[str, ...]] = {}
    pending = deque(dict.fromkeys(keys))
    scanned: set[ItemKey] = set()
    while pending:
        key = pending.popleft()
        if key in scanned:
            continue
        scanned.add(key)
        item = catalog.get(key)
        read = _READERS.get(key[0])
        if item is None or read is None:
            continue
        found, problems = read(item, catalog)
        dependencies.extend(found)
        pending.extend(dependency.target for dependency in found)
        if problems:
            broken[key] = tuple(problems)
    return ReferenceScan(tuple(dependencies), broken)


# What a reader finds in an item: references to local items, and problems.
_Found: TypeAlias = tuple[list[Dependency], list[str]]

_INITIAL_CATALOG = re.compile(
    r'initial catalog\s*=\s*"?([^";]+)"?', re.IGNORECASE
)


def _report_references(item: CatalogItem, catalog: LocalCatalog) -> _Found:
    """Report → SemanticModel, from ``datasetReference`` in the report."""
    definition = _read_json(Path(item.path) / "definition.pbir")
    reference = (
        definition.get("datasetReference")
        if isinstance(definition, dict)
        else None
    )
    if not isinstance(reference, dict):
        # An unreadable definition fails when it is deployed.
        return [], []

    by_path = reference.get("byPath")
    if isinstance(by_path, dict) and isinstance(by_path.get("path"), str):
        relative: str = by_path["path"]
        target = catalog.at(os.path.join(item.path, relative))
        if target is None or target.key[0] != "SemanticModel":
            return [], [
                f"definition.pbir points to {relative}, which is not a "
                "semantic model of the source."
            ]
        return [Dependency(item.key, target.key, "definition.pbir byPath")], []

    by_connection = reference.get("byConnection")
    if isinstance(by_connection, dict):
        match = _INITIAL_CATALOG.search(
            str(by_connection.get("connectionString", ""))
        )
        target = (
            catalog.get(("SemanticModel", match.group(1).strip()))
            if match
            else None
        )
        if target is not None:
            return [
                Dependency(
                    item.key, target.key, "definition.pbir byConnection"
                )
            ], []
    # A model outside the source is neither deployed nor blocking.
    return [], []


_READERS: dict[str, Callable[[CatalogItem, LocalCatalog], _Found]] = {
    "Report": _report_references,
}


def _read_platform(item_path: str) -> tuple[str, str | None] | None:
    """Read the display name and logical ID from an item's ``.platform``."""
    platform = _read_json(Path(item_path) / ".platform")
    if not isinstance(platform, dict):
        return None
    metadata = platform.get("metadata")
    config = platform.get("config")
    display_name = (
        metadata.get("displayName") if isinstance(metadata, dict) else None
    )
    logical_id = config.get("logicalId") if isinstance(config, dict) else None
    if not isinstance(display_name, str) or not display_name:
        return None
    return display_name, (
        logical_id if isinstance(logical_id, str) and logical_id else None
    )


def _read_json(path: Path) -> Any:
    """Read a JSON file, or return None when it cannot be read or parsed."""
    try:
        return json.loads(path.read_bytes())
    except (OSError, ValueError):
        return None


def _folder_id(path: str) -> str:
    """Name a folder so that two spellings of it compare equal."""
    return os.path.normcase(os.path.abspath(path))
