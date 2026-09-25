"""
Reconciliation: how a workspace stands against the whole source.

``reconcile`` takes the local items in scope, every item of the workspace,
which parts of each item's definition differ between the two (as
``drift.differing_parts`` names them), and, when there is one, what the
last successful deployment sent. It returns a ``Reconciliation``:

- a plan of what would bring the workspace back to the source: CREATE for
  an item the workspace lacks (TARGET_MISSING), UPDATE for one whose
  definition differs, MOVE for one in another folder, BLOCKED for a local
  item that cannot be read. A difference is WORKSPACE_DRIFT, unless the
  deployment state shows the source changed since the last deployment
  (SOURCE_CHANGED): then it is a deployment still to run;
- the items the workspace holds and the source does not (unmanaged);
- the items whose definition could not be compared (unchecked);
- the items that match (in sync).

Like the planner, it calls no API and reads no file, and nothing here
changes the workspace: a reconciliation only reports.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import PurePath
from types import MappingProxyType

from .dependency_graph import ItemKey
from .deployment_plan import (
    DeployedItem,
    DeploymentAction,
    DeploymentActionType,
    DeploymentPlan,
    DeploymentReason,
    SourceItem,
)

__all__ = [
    "CHILD_TYPES",
    "Reconciliation",
    "UnmanagedItem",
    "WorkspaceItem",
    "reconcile",
]

# Items Fabric creates along with another item, and deletes with it.
CHILD_TYPES = frozenset({"SQLEndpoint"})


@dataclass(frozen=True)
class WorkspaceItem:
    """
    An item of the workspace, as its listing gives it.

    Attributes:
        item_type (str): The Fabric item type.
        display_name (str): The item display name.
        folder_path (str | None): The workspace folder it is in, such as
            ``"Sales/Staging"``, or None at the workspace root.
    """

    item_type: str
    display_name: str
    folder_path: str | None = None


@dataclass(frozen=True)
class UnmanagedItem:
    """
    An item the workspace holds and the source does not.

    Attributes:
        item_type (str): The Fabric item type.
        display_name (str): The item display name.
        folder_path (str | None): The workspace folder it is in, or None at
            the workspace root.
        deployable (bool): Whether pyfabricops deploys items of its type.
    """

    item_type: str
    display_name: str
    folder_path: str | None = None
    deployable: bool = True

    def describe(self) -> str:
        """
        Describe the item on one line.

        Returns:
            str: Such as ``UNMANAGED Draft.Notebook: in the workspace, not
                in the source.``
        """
        where = f" in {_folder(self.folder_path)}" if self.folder_path else ""
        note = "" if self.deployable else "; pyfabricops does not deploy it"
        return (
            f"UNMANAGED {self.display_name}.{self.item_type}: in the "
            f"workspace{where}, not in the source{note}."
        )


@dataclass(frozen=True)
class Reconciliation:
    """
    How a workspace stands against the source.

    Attributes:
        plan (DeploymentPlan): What would bring the workspace back to the
            source, one action per item that differs, with its reason and
            what differs. Items that match are not in it.
        unmanaged (Sequence[UnmanagedItem]): The items the workspace holds
            and the source does not, in the order the workspace lists them.
            Stored as a tuple.
        unchecked (Mapping[ItemKey, str]): For each item whose definition
            could not be compared, why. It is in the workspace, and in the
            folder the source says, or it would be in the plan. Read-only.
        in_sync (Sequence[ItemKey]): The items that match the workspace.
            Stored as a tuple.
    """

    plan: DeploymentPlan = field(default_factory=DeploymentPlan)
    unmanaged: Sequence[UnmanagedItem] = ()
    unchecked: Mapping[ItemKey, str] = field(default_factory=dict)
    in_sync: Sequence[ItemKey] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "unmanaged", tuple(self.unmanaged))
        object.__setattr__(
            self, "unchecked", MappingProxyType(dict(self.unchecked))
        )
        object.__setattr__(self, "in_sync", tuple(self.in_sync))

    @property
    def ok(self) -> bool:
        """
        True when nothing differs: the plan is empty and nothing is
        unmanaged. An unchecked item does not count, as some item types
        never return a definition to compare.
        """
        return not self.plan.actions and not self.unmanaged

    def describe(self) -> str:
        """
        Describe the reconciliation: what differs, then the counts.

        Returns:
            str: One line per action, unmanaged item and unchecked item,
                then a line of counts.
        """
        lines = [action.describe() for action in self.plan.actions]
        lines += [item.describe() for item in self.unmanaged]
        lines += [
            f"UNCHECKED {display_name}.{item_type}: {why}"
            for (item_type, display_name), why in self.unchecked.items()
        ]
        counts = self.plan.summary()
        lines.append(
            f"{len(self.in_sync)} in sync, "
            + ", ".join(
                f"{counts[action.value]} {action.value.lower()}"
                for action in _PLANNED
            )
            + f", {len(self.unmanaged)} unmanaged, "
            f"{len(self.unchecked)} unchecked"
        )
        return "\n".join(lines)


# The actions a reconciliation plans, in the order they are counted.
_PLANNED = (
    DeploymentActionType.CREATE,
    DeploymentActionType.UPDATE,
    DeploymentActionType.MOVE,
    DeploymentActionType.BLOCKED,
)


def reconcile(
    items: Iterable[SourceItem],
    workspace: Iterable[WorkspaceItem],
    *,
    differences: Mapping[ItemKey, Sequence[str]],
    unchecked: Mapping[ItemKey, str] | None = None,
    deployed: Mapping[ItemKey, DeployedItem] | None = None,
    source_keys: Collection[ItemKey] | None = None,
    deployable_types: Collection[str] | None = None,
    root: str | None = None,
) -> Reconciliation:
    """
    Tell how a workspace stands against the source.

    Args:
        items (Iterable[SourceItem]): The local items in scope, in
            deployment order.
        workspace (Iterable[WorkspaceItem]): Every item of the workspace.
        differences (Mapping[ItemKey, Sequence[str]]): For each item in
            both, the parts of its definition that differ, empty when they
            match.
        unchecked (Mapping[ItemKey, str], optional): For each item in both
            whose definition could not be compared, why.
        deployed (Mapping[ItemKey, DeployedItem], optional): What the last
            successful deployment sent for each item, from the deployment
            state. It tells a change made in the workspace from a change
            made in the source.
        source_keys (Collection[ItemKey], optional): Every item of the
            source, of any type, when ``items`` holds only some types: an
            item of the source is never unmanaged. Defaults to the items.
        deployable_types (Collection[str], optional): The item types
            pyfabricops deploys, to tell unmanaged items of other types.
            Defaults to any type.
        root (str, optional): The folder the items were read from. A detail
            that points to another item folder shows it relative to this
            one. Defaults to showing it as given.

    Returns:
        Reconciliation: What differs, what is unmanaged, what could not be
            compared, and what matches.

    Examples:
        ```python
        reconciliation = reconcile(
            [SourceItem("Notebook", "ws/Orders.Notebook", "Orders")],
            [WorkspaceItem("Notebook", "Orders")],
            differences={("Notebook", "Orders"): ["notebook-content.py"]},
        )
        print(reconciliation.describe())
        ```
    """
    unchecked = dict(unchecked or {})
    deployed = dict(deployed or {})
    listed = list(workspace)
    found = {(i.item_type, i.display_name): i for i in listed}

    actions: list[DeploymentAction] = []
    not_compared: dict[ItemKey, str] = {}
    in_sync: list[ItemKey] = []
    defined: dict[ItemKey, str] = {}
    for item in items:
        if item.error is not None or item.display_name is None:
            actions.append(
                _action(
                    item,
                    DeploymentActionType.BLOCKED,
                    item.error or f"{item.source_path} has no display name.",
                )
            )
            continue
        key = (item.item_type, item.display_name)
        if key in defined:
            actions.append(
                _action(
                    item,
                    DeploymentActionType.BLOCKED,
                    f"{item.display_name}.{item.item_type} is also defined "
                    f"at {_where(defined[key], root)}; the source cannot "
                    "hold it twice.",
                )
            )
            continue
        defined[key] = item.source_path

        target = found.get(key)
        record = deployed.get(key)
        if target is None:
            actions.append(
                _action(
                    item,
                    DeploymentActionType.CREATE,
                    "Deleted from the workspace since the last deployment."
                    if record is not None
                    else "In the source, not in the workspace.",
                    reason=DeploymentReason.TARGET_MISSING,
                )
            )
            continue

        parts = differences.get(key)
        if parts is None:
            not_compared[key] = unchecked.get(key, "Definition not compared.")
        moved = (target.folder_path or None) != (item.folder_path or None)
        if parts:
            reason, detail = _content_changed(item, record, tuple(parts))
            if moved:
                detail += (
                    f" It is in {_folder(target.folder_path)} in the "
                    f"workspace, {_folder(item.folder_path)} in the source."
                )
            actions.append(
                _action(item, DeploymentActionType.UPDATE, detail, reason)
            )
        elif moved:
            reason, detail = _folder_changed(item, target, record)
            actions.append(
                _action(item, DeploymentActionType.MOVE, detail, reason)
            )
        elif key not in not_compared:
            in_sync.append(key)

    known = set(defined) | set(source_keys or ())
    unmanaged = [
        UnmanagedItem(
            item.item_type,
            item.display_name,
            item.folder_path,
            deployable_types is None or item.item_type in deployable_types,
        )
        for item in listed
        if (item.item_type, item.display_name) not in known
        and item.item_type not in CHILD_TYPES
    ]
    return Reconciliation(
        plan=DeploymentPlan(actions=actions),
        unmanaged=unmanaged,
        unchecked=not_compared,
        in_sync=in_sync,
    )


def _content_changed(
    item: SourceItem, record: DeployedItem | None, parts: tuple[str, ...]
) -> tuple[DeploymentReason, str]:
    """Say where a difference of definition comes from, when one can tell."""
    listed = ", ".join(parts)
    if record is None or item.content_hash is None:
        return (
            DeploymentReason.WORKSPACE_DRIFT,
            f"Differs from the source: {listed}.",
        )
    if record.content_hash == item.content_hash:
        return (
            DeploymentReason.WORKSPACE_DRIFT,
            f"Changed in the workspace since the last deployment: {listed}.",
        )
    return (
        DeploymentReason.SOURCE_CHANGED,
        f"Changed in the source since the last deployment: {listed}.",
    )


def _folder_changed(
    item: SourceItem, target: WorkspaceItem, record: DeployedItem | None
) -> tuple[DeploymentReason, str]:
    """Say where a difference of folder comes from, when one can tell."""
    here = _folder(target.folder_path)
    there = _folder(item.folder_path)
    if record is None:
        return (
            DeploymentReason.WORKSPACE_DRIFT,
            f"In {here} in the workspace, {there} in the source.",
        )
    if (record.folder_path or None) == (item.folder_path or None):
        return (
            DeploymentReason.WORKSPACE_DRIFT,
            f"Moved to {here} in the workspace since the last deployment; "
            f"the source has it in {there}.",
        )
    return (
        DeploymentReason.SOURCE_CHANGED,
        f"Moved to {there} in the source since the last deployment; the "
        f"workspace has it in {here}.",
    )


def _action(
    item: SourceItem,
    action: DeploymentActionType,
    detail: str,
    reason: DeploymentReason = DeploymentReason.FULL_DEPLOYMENT,
) -> DeploymentAction:
    """Plan an action for a local item, as the planner would."""
    return DeploymentAction(
        action=action,
        item_type=item.item_type,
        display_name=item.display_name,
        source_path=item.source_path,
        reason=reason,
        folder_path=item.folder_path,
        detail=detail,
    )


def _folder(folder_path: str | None) -> str:
    """Name a workspace folder for a detail."""
    return f"'{folder_path}'" if folder_path else "the workspace root"


def _where(source_path: str, root: str | None) -> str:
    """Show an item folder relative to the root, when it is inside it."""
    if root is None:
        return source_path
    try:
        return PurePath(source_path).relative_to(root).as_posix()
    except ValueError:
        return source_path
