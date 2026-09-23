"""
Deployment plan: what a deployment run does to each item, and why.

Deciding and doing are separate steps. ``DeploymentPlanner`` turns the items
selected for a run into a ``DeploymentPlan`` using only what it is given: it
calls no Fabric API and reads no file, so the same input always gives the
same plan. The engine in ``pyfabricops.helpers.deployment`` then applies the
plan.

Internal for now: nothing here is exported from ``pyfabricops``, and the
model may change while the deployment engine evolves.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from enum import Enum

__all__ = [
    "DeploymentAction",
    "DeploymentActionType",
    "DeploymentPlan",
    "DeploymentPlanner",
    "DeploymentReason",
    "SourceItem",
]


class DeploymentActionType(str, Enum):
    """
    What a deployment action does to an item.

    Members compare equal to their names, so ``action == "UPDATE"`` holds.

    Attributes:
        CREATE: Create the item, which is not in the workspace yet.
        UPDATE: Replace the definition of the item already in the workspace.
        BLOCKED: Leave the item alone and report it as failed;
            ``DeploymentAction.detail`` says why.
    """

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    BLOCKED = "BLOCKED"


class DeploymentReason(str, Enum):
    """
    Why an item is part of a deployment plan.

    Each way of selecting items adds the reasons it gives; for now there is
    one.

    Attributes:
        FULL_DEPLOYMENT: The run deploys every local item in its scope: every
            type in ``DEPLOY_ORDER``, or the ``item_types`` requested.
    """

    FULL_DEPLOYMENT = "FULL_DEPLOYMENT"


@dataclass(frozen=True)
class SourceItem:
    """
    A local item selected for deployment, as the planner receives it.

    Attributes:
        item_type (str): The Fabric item type, from the folder suffix.
        source_path (str): The local item folder.
        display_name (str | None): The display name from ``.platform``, or
            None when it could not be read.
        folder_path (str | None): The workspace folder the item belongs in,
            such as ``"Sales/Staging"``, or None for the workspace root.
        error (str | None): Why the item cannot be deployed, such as an
            unreadable ``.platform``.
    """

    item_type: str
    source_path: str
    display_name: str | None = None
    folder_path: str | None = None
    error: str | None = None


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
        ValueError: If a CREATE or UPDATE action has no display name.
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


class DeploymentPlanner:
    """
    Decide what a deployment run does to each selected item.

    The planner works only on what it is given: it calls no Fabric API and
    reads no file, so a plan can be built, inspected and tested without a
    workspace, and the same input always gives the same plan.

    Args:
        existing_items (Collection[tuple[str, str]]): The ``(item_type,
            display_name)`` of every item already in the target workspace.

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

    def __init__(self, existing_items: Collection[tuple[str, str]]) -> None:
        self._existing_items = frozenset(existing_items)

    def plan(self, items: Iterable[SourceItem]) -> DeploymentPlan:
        """
        Plan one action per item, in the order given.

        An item already in the workspace is updated and any other is
        created. An item whose display name is unknown is blocked, and so is
        an item with the same type and display name as an earlier one:
        deploying both would overwrite the same workspace item.

        Args:
            items (Iterable[SourceItem]): The selected items, in deployment
                order.

        Returns:
            DeploymentPlan: One action per item, in the same order.
        """
        first_seen: dict[tuple[str, str], str] = {}
        return DeploymentPlan(
            actions=[self._plan_item(item, first_seen) for item in items]
        )

    def _plan_item(
        self, item: SourceItem, first_seen: dict[tuple[str, str], str]
    ) -> DeploymentAction:
        """Plan one item, remembering its identity to catch duplicates."""
        display_name = item.display_name
        if item.error is not None or display_name is None:
            return _blocked(
                item, item.error or f"{item.source_path} has no display name."
            )

        identity = (item.item_type, display_name)
        if identity in first_seen:
            return _blocked(
                item,
                f"{display_name}.{item.item_type} is also defined at "
                f"{first_seen[identity]}; deploying both would overwrite the "
                "same item.",
            )
        first_seen[identity] = item.source_path

        action = (
            DeploymentActionType.UPDATE
            if identity in self._existing_items
            else DeploymentActionType.CREATE
        )
        return DeploymentAction(
            action=action,
            item_type=item.item_type,
            display_name=display_name,
            source_path=item.source_path,
            reason=DeploymentReason.FULL_DEPLOYMENT,
            folder_path=item.folder_path,
        )


def _blocked(item: SourceItem, detail: str) -> DeploymentAction:
    """Plan an item that cannot be deployed, keeping its place in the run."""
    return DeploymentAction(
        action=DeploymentActionType.BLOCKED,
        item_type=item.item_type,
        display_name=item.display_name,
        source_path=item.source_path,
        reason=DeploymentReason.FULL_DEPLOYMENT,
        folder_path=item.folder_path,
        detail=detail,
    )
