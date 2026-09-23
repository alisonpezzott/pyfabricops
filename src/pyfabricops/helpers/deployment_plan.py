"""
Deployment plan: what a deployment run does to each item, and why.

Deciding and doing are separate steps. ``DeploymentPlanner`` turns the items
selected for a run into a ``DeploymentPlan`` using only what it is given: it
calls no Fabric API and reads no file, so the same input always gives the
same plan. The engine in ``pyfabricops.helpers.deployment`` then applies the
plan.

``plan_all_items`` returns a plan, so ``DeploymentPlan``, ``DeploymentAction``,
``DeploymentActionType`` and ``DeploymentReason`` are exported from
``pyfabricops``; the planner itself stays internal.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePath

__all__ = [
    "DeploymentAction",
    "DeploymentActionType",
    "DeploymentPlan",
    "DeploymentPlanner",
    "DeploymentReason",
    "DeployedItem",
    "SourceChange",
    "SourceItem",
]


class DeploymentActionType(str, Enum):
    """
    What a deployment action does to an item.

    Members compare equal to their names, so ``action == "UPDATE"`` holds.

    Attributes:
        CREATE: Create the item, which is not in the workspace yet.
        UPDATE: Replace the definition of the item already in the workspace.
        MOVE: Move the item to its folder, or to the workspace root. Its
            definition is the one the last successful deployment sent, so it
            is not sent again.
        DELETE: Delete the item from the workspace, because it was deleted
            from the source. The executor refuses it until a policy allows
            deletions.
        NOOP: Nothing to do, such as for an item deleted from the source
            that the workspace no longer has.
        BLOCKED: Leave the item alone and report it as failed;
            ``DeploymentAction.detail`` says why.
    """

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    MOVE = "MOVE"
    DELETE = "DELETE"
    NOOP = "NOOP"
    BLOCKED = "BLOCKED"


class DeploymentReason(str, Enum):
    """
    Why an item is part of a deployment plan.

    Each way of selecting items adds the reasons it gives.

    Attributes:
        FULL_DEPLOYMENT: The run deploys every local item in its scope: every
            type in ``DEPLOY_ORDER``, or the ``item_types`` requested.
        SOURCE_CHANGED: Files of the item changed since the baseline commit.
        ITEM_ADDED: The item was added to the source since the baseline
            commit.
        ITEM_DELETED: The item was deleted from the source since the baseline
            commit.
    """

    FULL_DEPLOYMENT = "FULL_DEPLOYMENT"
    SOURCE_CHANGED = "SOURCE_CHANGED"
    ITEM_ADDED = "ITEM_ADDED"
    ITEM_DELETED = "ITEM_DELETED"


class SourceChange(str, Enum):
    """
    How an item changed in the source since the baseline commit.

    Attributes:
        ADDED: The item folder did not exist at the baseline commit.
        MODIFIED: The item folder exists at both commits and some of its
            files changed, even if they are all new files.
        DELETED: The item folder no longer exists at HEAD.
    """

    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"


@dataclass(frozen=True)
class SourceItem:
    """
    A local item selected for deployment, as the planner receives it.

    Attributes:
        item_type (str): The Fabric item type, from the folder suffix.
        source_path (str): The local item folder. A deleted item no longer
            has one.
        display_name (str | None): The display name from ``.platform`` (for
            a deleted item, as it was at the baseline commit), or None when
            it could not be read.
        folder_path (str | None): The workspace folder the item belongs in,
            such as ``"Sales/Staging"``, or None for the workspace root.
        error (str | None): Why the item cannot be deployed, such as an
            unreadable ``.platform``.
        change (SourceChange | None): How the item changed since the
            baseline commit, or None when the run deploys every item.
        content_hash (str | None): The hash of the definition to deploy, or
            None when no deployment state can use it.
    """

    item_type: str
    source_path: str
    display_name: str | None = None
    folder_path: str | None = None
    error: str | None = None
    change: SourceChange | None = None
    content_hash: str | None = None


@dataclass(frozen=True)
class DeployedItem:
    """
    What the last successful deployment sent for an item.

    Attributes:
        content_hash (str): The hash of the item definition.
        folder_path (str | None): The workspace folder the item was placed
            in, or None for the workspace root.
    """

    content_hash: str
    folder_path: str | None = None


@dataclass(frozen=True)
class DeploymentAction:
    """
    One step of a deployment plan: what happens to an item, and why.

    Attributes:
        action (DeploymentActionType): What happens to the item.
        item_type (str): The Fabric item type.
        display_name (str | None): The item display name. Only a BLOCKED
            action may lack one, when ``.platform`` could not be read.
        source_path (str): The local item folder.
        reason (DeploymentReason): Why the item is part of the plan.
        folder_path (str | None): The workspace folder the item belongs in,
            or None for the workspace root.
        detail (str | None): More about the action, such as why it is
            blocked.

    Raises:
        ValueError: If an action other than BLOCKED has no display name.
    """

    action: DeploymentActionType
    item_type: str
    display_name: str | None
    source_path: str
    reason: DeploymentReason
    folder_path: str | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if (
            self.display_name is None
            and self.action is not DeploymentActionType.BLOCKED
        ):
            raise ValueError(
                f"A {self.action.value} action needs a display name "
                f"({self.source_path})."
            )

    def describe(self) -> str:
        """
        Describe the action on one line: what, to which item, and why.

        Returns:
            str: Such as ``UPDATE   Orders.Notebook  SOURCE_CHANGED``, with
                the detail after a colon when there is one.
        """
        name = (
            f"{self.display_name}.{self.item_type}"
            if self.display_name
            else self.source_path
        )
        line = f"{self.action.value:<8} {name}  {self.reason.value}"
        return f"{line}: {self.detail}" if self.detail else line


@dataclass(frozen=True)
class DeploymentPlan:
    """
    The actions of a deployment run, decided before anything changes.

    Attributes:
        actions (Sequence[DeploymentAction]): The actions, in execution
            order. Stored as a tuple, so a plan cannot change once built.
    """

    actions: Sequence[DeploymentAction] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "actions", tuple(self.actions))

    def summary(self) -> dict[str, int]:
        """
        Count the actions by type.

        Returns:
            dict[str, int]: The number of each action type, every type
                included.
        """
        counts = {action_type.value: 0 for action_type in DeploymentActionType}
        for action in self.actions:
            counts[action.action.value] += 1
        return counts

    def describe(self) -> str:
        """
        Describe the plan: one line per action, then the counts.

        Returns:
            str: The plan as text, ready to print or log.

        Examples:
            ```python
            print(plan_all_items('Sales-DEV', 'workspace').describe())
            ```
        """
        lines = [action.describe() for action in self.actions]
        counts = ", ".join(
            f"{count} {action_type.lower()}"
            for action_type, count in self.summary().items()
        )
        return "\n".join([*(lines or ["No actions."]), counts])


class DeploymentPlanner:
    """
    Decide what a deployment run does to each selected item.

    The planner works only on what it is given: it calls no Fabric API and
    reads no file, so a plan can be built, inspected and tested without a
    workspace, and the same input always gives the same plan.

    Args:
        existing_items (Collection[tuple[str, str]]): The ``(item_type,
            display_name)`` of every item already in the target workspace.
        deployed_items (Mapping[tuple[str, str], DeployedItem], optional):
            What the last successful deployment sent for each item, from the
            deployment state. Defaults to nothing known.
        root (str, optional): The folder the items were read from. A detail
            that points to another item folder shows it relative to this
            one. Defaults to showing it as given.

    Examples:
        ```python
        planner = DeploymentPlanner(existing_items={("Notebook", "Orders")})
        plan = planner.plan([
            SourceItem("Notebook", "ws/Orders.Notebook", "Orders"),
            SourceItem("Report", "ws/Sales.Report", "Sales"),
        ])
        [a.action.value for a in plan.actions]  # ['UPDATE', 'CREATE']
        ```
    """

    def __init__(
        self,
        existing_items: Collection[tuple[str, str]],
        deployed_items: Mapping[tuple[str, str], DeployedItem] | None = None,
        *,
        root: str | None = None,
    ) -> None:
        self._existing_items = frozenset(existing_items)
        self._deployed_items = dict(deployed_items or {})
        self._root = root

    def plan(self, items: Iterable[SourceItem]) -> DeploymentPlan:
        """
        Plan one action per item.

        An item already in the workspace is updated and any other is
        created. An item whose definition is the one its last successful
        deployment sent needs nothing, or only a move when its folder
        changed. An item deleted from the source is deleted from the
        workspace, or needs nothing when the workspace no longer has it or
        another item of the plan still defines it, as when its folder moved.
        An item whose display name is unknown is blocked, and so is an item
        with the same type and display name as an earlier one: deploying
        both would overwrite the same workspace item.

        Args:
            items (Iterable[SourceItem]): The selected items, in deployment
                order.

        Returns:
            DeploymentPlan: One action per item. Deletions come after every
                other action; otherwise the order given is kept.
        """
        selected = list(items)
        defined: dict[tuple[str, str], str] = {}
        actions = [
            self._plan_item(item, defined)
            for item in selected
            if item.change is not SourceChange.DELETED
        ]
        deleted: dict[tuple[str, str], str] = {}
        actions += [
            self._plan_deletion(item, defined, deleted)
            for item in selected
            if item.change is SourceChange.DELETED
        ]
        return DeploymentPlan(actions=actions)

    def _plan_item(
        self, item: SourceItem, defined: dict[tuple[str, str], str]
    ) -> DeploymentAction:
        """Plan an item to create or update, catching duplicate identities."""
        display_name = item.display_name
        if item.error is not None or display_name is None:
            return _blocked(item)

        identity = (item.item_type, display_name)
        if identity in defined:
            return _action(
                item,
                DeploymentActionType.BLOCKED,
                f"{display_name}.{item.item_type} is also defined at "
                f"{self._where(defined[identity])}; deploying both would "
                "overwrite the same item.",
            )
        defined[identity] = item.source_path

        if identity not in self._existing_items:
            return _action(item, DeploymentActionType.CREATE)
        sent = self._sent_before(identity, item)
        if sent is None:
            return _action(item, DeploymentActionType.UPDATE)
        if sent.folder_path == item.folder_path:
            return _action(
                item,
                DeploymentActionType.NOOP,
                "Definition and folder unchanged since the last successful "
                "deployment.",
            )
        return _action(
            item,
            DeploymentActionType.MOVE,
            "Definition unchanged since the last successful deployment; "
            f"folder changed from {_folder(sent.folder_path)} to "
            f"{_folder(item.folder_path)}.",
        )

    def _sent_before(
        self, identity: tuple[str, str], item: SourceItem
    ) -> DeployedItem | None:
        """What the last deployment sent, when it sent this definition."""
        deployed = self._deployed_items.get(identity)
        if (
            deployed is None
            or item.content_hash is None
            or deployed.content_hash != item.content_hash
        ):
            return None
        return deployed

    def _plan_deletion(
        self,
        item: SourceItem,
        defined: dict[tuple[str, str], str],
        deleted: dict[tuple[str, str], str],
    ) -> DeploymentAction:
        """Plan an item deleted from the source, once per workspace item."""
        display_name = item.display_name
        if item.error is not None or display_name is None:
            return _blocked(item)

        identity = (item.item_type, display_name)
        if identity in defined:
            return _action(
                item,
                DeploymentActionType.NOOP,
                f"Still defined at {self._where(defined[identity])}.",
            )
        if identity in deleted:
            return _action(
                item,
                DeploymentActionType.NOOP,
                "Its deletion is planned with "
                f"{self._where(deleted[identity])}.",
            )
        deleted[identity] = item.source_path

        if identity in self._existing_items:
            return _action(
                item,
                DeploymentActionType.DELETE,
                "Refused until deletions are allowed: delete it from the "
                "workspace by hand.",
            )
        return _action(
            item,
            DeploymentActionType.NOOP,
            "Deleted from the source and not in the workspace.",
        )

    def _where(self, source_path: str) -> str:
        """Show an item folder relative to the root, when it is inside it."""
        if self._root is None:
            return source_path
        try:
            return PurePath(source_path).relative_to(self._root).as_posix()
        except ValueError:
            return source_path


# Why an item is in the plan, from how it changed; None means a full run.
_REASONS: dict[SourceChange | None, DeploymentReason] = {
    None: DeploymentReason.FULL_DEPLOYMENT,
    SourceChange.ADDED: DeploymentReason.ITEM_ADDED,
    SourceChange.MODIFIED: DeploymentReason.SOURCE_CHANGED,
    SourceChange.DELETED: DeploymentReason.ITEM_DELETED,
}


def _action(
    item: SourceItem,
    action: DeploymentActionType,
    detail: str | None = None,
) -> DeploymentAction:
    """Plan an action for an item, with the reason its change gives."""
    return DeploymentAction(
        action=action,
        item_type=item.item_type,
        display_name=item.display_name,
        source_path=item.source_path,
        reason=_REASONS[item.change],
        folder_path=item.folder_path,
        detail=detail,
    )


def _folder(folder_path: str | None) -> str:
    """Name a workspace folder for a detail."""
    return f"'{folder_path}'" if folder_path else "the workspace root"


def _blocked(item: SourceItem) -> DeploymentAction:
    """Block an item whose display name is unknown, keeping its place."""
    return _action(
        item,
        DeploymentActionType.BLOCKED,
        item.error or f"{item.source_path} has no display name.",
    )
