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

Given the references between local items (a ``DependencyGraph``, as pure as
the planner), the planner also orders each item after what it needs, and
meets or blocks what the selected items need.
"""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import PurePath

from .dependency_graph import DependencyGraph, ItemKey

__all__ = [
    "DeploymentAction",
    "DeploymentActionType",
    "DeploymentPlan",
    "DeploymentPlanner",
    "DeploymentReason",
    "DeployedItem",
    "SourceChange",
    "SourceItem",
    "name_problem",
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
            from the source. Planned only when the run allows deletions and
            no item that stays in the source refers to it; the item is
            blocked otherwise.
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
        DEPENDENCY_REQUIRED: An item of the plan needs it: it is validated
            when the workspace has it, and created otherwise.
        TARGET_MISSING: A reconciliation found the item in the source and
            not in the workspace.
        WORKSPACE_DRIFT: A reconciliation found the item in the workspace
            different from the source: changed there since the last
            deployment, or different, when no deployment state tells.
    """

    FULL_DEPLOYMENT = "FULL_DEPLOYMENT"
    SOURCE_CHANGED = "SOURCE_CHANGED"
    ITEM_ADDED = "ITEM_ADDED"
    ITEM_DELETED = "ITEM_DELETED"
    DEPENDENCY_REQUIRED = "DEPENDENCY_REQUIRED"
    TARGET_MISSING = "TARGET_MISSING"
    WORKSPACE_DRIFT = "WORKSPACE_DRIFT"


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
        logical_id (str | None): ``config.logicalId`` from ``.platform``,
            read for an item deleted from the source, as it was at the
            baseline commit, so that what refers to it by logical ID is
            found; None otherwise.
    """

    item_type: str
    source_path: str
    display_name: str | None = None
    folder_path: str | None = None
    error: str | None = None
    change: SourceChange | None = None
    content_hash: str | None = None
    logical_id: str | None = None


@dataclass(frozen=True)
class DeployedItem:
    """
    What the last successful deployment sent for an item.

    Attributes:
        content_hash (str): The hash of the item definition.
        folder_path (str | None): The workspace folder the item was placed
            in, or None for the workspace root.
        sent_by (str | None): Who sent it, when not the last successful
            deployment, such as ``"an interrupted run sent it at
            2026-09-26T10:00:00Z"``; a plan detail tells it.
    """

    content_hash: str
    folder_path: str | None = None
    sent_by: str | None = None


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
        needs (Sequence[ItemKey]): The ``(item_type, display_name)`` of
            the items of the plan that this one needs. When one of them
            fails or is skipped, this one is skipped. Stored as a tuple.

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
    needs: Sequence[ItemKey] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "needs", tuple(self.needs))
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
        dependencies (DependencyGraph, optional): The references between
            local items. Without it, dependencies are not resolved and the
            order given is kept.
        broken (Mapping[ItemKey, Sequence[str]], optional): For each item
            whose definition points to a local item that is not there, why;
            such an item is blocked.
        item_types (Collection[str], optional): The item types the run
            deploys; a missing dependency of another type is not created,
            and what needs it is blocked. Defaults to any type.
        warnings (Mapping[ItemKey, Sequence[str]], optional): For each item,
            what to warn about, such as a reference by ID the workspace
            lacks. Added to the detail of the item's action; nothing is
            blocked for it.
        source (Mapping[ItemKey, str], optional): Every item of the source,
            whatever the run selects, with its folder. An item deleted from
            one folder is not deleted from the workspace while the source
            still defines it in another. Defaults to the selected items.
        referenced_by (Mapping[ItemKey, Sequence[str]], optional): For each
            item deleted from the source, the items that stay and still
            refer to it, and how, such as ``"Sales.Report (definition.pbir
            byPath)"``. Its deletion is blocked, so that nothing is deleted
            from under an item that needs it.
        allow_deletions (bool, optional): Delete from the workspace the
            items deleted from the source. Defaults to False: each is
            blocked, so the run fails and the deletion is not missed.

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
        dependencies: DependencyGraph | None = None,
        broken: Mapping[ItemKey, Sequence[str]] | None = None,
        item_types: Collection[str] | None = None,
        warnings: Mapping[ItemKey, Sequence[str]] | None = None,
        source: Mapping[ItemKey, str] | None = None,
        referenced_by: Mapping[ItemKey, Sequence[str]] | None = None,
        allow_deletions: bool = False,
    ) -> None:
        self._existing_items = frozenset(existing_items)
        self._deployed_items = dict(deployed_items or {})
        self._root = root
        self._graph = dependencies
        self._broken = {
            key: tuple(problems) for key, problems in (broken or {}).items()
        }
        self._item_types = None if item_types is None else set(item_types)
        self._warnings = {
            key: tuple(texts) for key, texts in (warnings or {}).items()
        }
        self._source = dict(source or {})
        self._referenced_by = {
            key: tuple(texts) for key, texts in (referenced_by or {}).items()
        }
        self._allow_deletions = allow_deletions

    def plan(
        self,
        items: Iterable[SourceItem],
        available: Iterable[SourceItem] = (),
    ) -> DeploymentPlan:
        """
        Plan one action per item.

        An item already in the workspace is updated and any other is
        created. An item whose definition is the one its last successful
        deployment sent needs nothing, or only a move when its folder
        changed. An item deleted from the source is deleted from the
        workspace when the run allows deletions and no item that stays
        refers to it, and blocked otherwise; it needs nothing when the
        workspace no longer has it or the source still defines it, as when
        its folder moved. An item whose display name is unknown is blocked,
        and so is an item with the same type and display name as an earlier
        one: deploying both would overwrite the same workspace item.

        With ``dependencies``, each item comes after the items it needs.
        What an item to create, update or move needs, when not selected, is
        validated (NOOP) if the workspace has it, and created otherwise from
        ``available``. An item is blocked when a reference of its definition
        is broken, when it is part of a dependency cycle, or when something
        it needs is blocked or cannot be created. Each action lists in
        ``needs`` the items of the plan it needs, so that it is skipped when
        one of them is not deployed.

        Args:
            items (Iterable[SourceItem]): The selected items, in deployment
                order.
            available (Iterable[SourceItem], optional): Local items outside
                the selection that the plan may validate or create to meet
                dependencies, in deployment order. Defaults to none.

        Returns:
            DeploymentPlan: One action per item, plus one per dependency met.
                Deletions come after every other action; otherwise the order
                given is kept, except that each item follows what it needs.
        """
        selected = list(items)
        defined: dict[tuple[str, str], str] = {}
        actions = [
            self._plan_item(item, defined)
            for item in selected
            if item.change is not SourceChange.DELETED
        ]
        if self._graph is not None:
            actions = self._resolve(self._graph, actions, list(available))
        if self._warnings:
            actions = [self._with_warnings(action) for action in actions]
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
            problem = name_problem(item.item_type, display_name)
            if problem is not None:
                return _action(
                    item,
                    DeploymentActionType.BLOCKED,
                    f"Fabric refuses this name: {problem}.",
                )
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
        still_defined = defined.get(identity) or self._source.get(identity)
        if still_defined is not None:
            return _action(
                item,
                DeploymentActionType.NOOP,
                f"Still defined at {self._where(still_defined)}.",
            )
        if identity in deleted:
            return _action(
                item,
                DeploymentActionType.NOOP,
                "Its deletion is planned with "
                f"{self._where(deleted[identity])}.",
            )
        deleted[identity] = item.source_path

        if identity not in self._existing_items:
            return _action(
                item,
                DeploymentActionType.NOOP,
                "Deleted from the source and not in the workspace.",
            )
        problems: list[str] = []
        referrers = self._referenced_by.get(identity)
        if referrers:
            problems.append(f"Still referred to by {'; '.join(referrers)}.")
        if not self._allow_deletions:
            problems.append(
                "Deletions are not allowed in this run: pass "
                "allow_deletions=True, or delete it from the workspace by "
                "hand."
            )
        if problems:
            return _action(
                item, DeploymentActionType.BLOCKED, " ".join(problems)
            )
        return _action(item, DeploymentActionType.DELETE)

    def _resolve(
        self,
        graph: DependencyGraph,
        actions: list[DeploymentAction],
        available: list[SourceItem],
    ) -> list[DeploymentAction]:
        """Meet or block what the actions need, and order them by it."""
        # Each action keeps the nameless ones after it, which have no key.
        head: list[DeploymentAction] = []
        groups: dict[ItemKey, list[DeploymentAction]] = {}
        group = head
        for action in actions:
            if action.display_name is not None:
                group = groups.setdefault(_key(action), [])
            group.append(action)
        selected = {key: group[0] for key, group in groups.items()}

        needed, unmet = self._required(graph, selected, available)
        blocked = self._blocked(graph, selected, needed, unmet)

        needed_in_order = [
            key
            for key in dict.fromkeys(
                (item.item_type, item.display_name)
                for item in available
                if item.display_name is not None
            )
            if key in needed
        ]
        planned_keys = {*selected, *needed}
        resolved = list(head)
        for key in graph.order([*selected, *needed_in_order]):
            planned = groups.get(key, [needed[key]] if key in needed else [])
            needs = tuple(
                dict.fromkeys(
                    dependency.target
                    for dependency in graph.dependencies_of(key)
                    if dependency.target in planned_keys
                )
            )
            if planned and needs:
                planned = [replace(planned[0], needs=needs), *planned[1:]]
            if key in blocked:
                planned = [_block(planned[0], blocked[key]), *planned[1:]]
            resolved.extend(planned)
        return resolved

    def _required(
        self,
        graph: DependencyGraph,
        selected: Mapping[ItemKey, DeploymentAction],
        available: list[SourceItem],
    ) -> tuple[dict[ItemKey, DeploymentAction], dict[ItemKey, str]]:
        """
        Plan what the items to deploy need and the selection lacks.

        A needed item the workspace has is validated, and what it needs in
        turn is left alone. One it lacks is created, when it can be, and
        what it needs is followed. Returns those actions, and why each of
        the other needed items cannot be met.
        """
        candidates: dict[ItemKey, SourceItem] = {}
        for item in available:
            if item.display_name is not None:
                candidates.setdefault(
                    (item.item_type, item.display_name), item
                )

        needed: dict[ItemKey, DeploymentAction] = {}
        unmet: dict[ItemKey, str] = {}
        seen = set(selected)
        pending = deque(
            key
            for key, action in selected.items()
            if action.action in _DEPLOYING
        )
        while pending:
            key = pending.popleft()
            for dependency in graph.dependencies_of(key):
                target = dependency.target
                if target in seen:
                    continue
                seen.add(target)
                required_by = f"Required by {_name(key)} ({dependency.via})"
                candidate = candidates.get(target)
                if target in self._existing_items:
                    if candidate is not None:
                        needed[target] = _action(
                            candidate,
                            DeploymentActionType.NOOP,
                            f"{required_by}; already in the workspace.",
                            reason=DeploymentReason.DEPENDENCY_REQUIRED,
                        )
                elif candidate is None or candidate.error is not None:
                    unmet[target] = (
                        "is missing from the workspace and cannot be "
                        "deployed from the source"
                    )
                elif (
                    self._item_types is not None
                    and target[0] not in self._item_types
                ):
                    unmet[target] = (
                        "is missing from the workspace and not among the "
                        "item types of this run"
                    )
                elif (problem := name_problem(*target)) is not None:
                    unmet[target] = (
                        f"is missing from the workspace, with a name Fabric "
                        f"refuses: {problem}"
                    )
                else:
                    needed[target] = _action(
                        candidate,
                        DeploymentActionType.CREATE,
                        f"{required_by} and missing from the workspace.",
                        reason=DeploymentReason.DEPENDENCY_REQUIRED,
                    )
                    pending.append(target)
        return needed, unmet

    def _blocked(
        self,
        graph: DependencyGraph,
        selected: Mapping[ItemKey, DeploymentAction],
        needed: Mapping[ItemKey, DeploymentAction],
        unmet: Mapping[ItemKey, str],
    ) -> dict[ItemKey, str]:
        """Say why each item to deploy cannot be deployed with its needs."""
        deploying = [
            key
            for key, action in {**selected, **needed}.items()
            if action.action in _DEPLOYING
        ]
        blocked: dict[ItemKey, str] = {}
        for key in deploying:
            if key in self._broken:
                blocked[key] = " ".join(self._broken[key])
        for members in graph.cycles(deploying):
            names = ", ".join(_name(key) for key in members)
            for key in members:
                blocked.setdefault(
                    key, f"Part of a dependency cycle: {names}."
                )

        unusable = {
            key
            for key, action in selected.items()
            if action.action is DeploymentActionType.BLOCKED
        }
        changed = True
        while changed:
            changed = False
            for key in deploying:
                if key in blocked:
                    continue
                for dependency in graph.dependencies_of(key):
                    target = dependency.target
                    if target in unmet:
                        why = unmet[target]
                    elif target in blocked or target in unusable:
                        why = "is blocked"
                    else:
                        continue
                    blocked[key] = f"Needs {_name(target)}, which {why}."
                    changed = True
                    break
        return blocked

    def _with_warnings(self, action: DeploymentAction) -> DeploymentAction:
        """Add what to warn about an item to the detail of its action."""
        if action.display_name is None:
            return action
        warnings = self._warnings.get(_key(action), ())
        if not warnings:
            return action
        notes = [f"Warning: {warning}" for warning in warnings]
        return replace(
            action,
            detail=" ".join(
                [action.detail, *notes] if action.detail else notes
            ),
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


# The actions that change the workspace and so need what the item needs.
_DEPLOYING = frozenset(
    {
        DeploymentActionType.CREATE,
        DeploymentActionType.UPDATE,
        DeploymentActionType.MOVE,
    }
)


# Display names Fabric documents that it refuses, by item type, and what it
# expects instead.
_NAME_RULES: dict[str, tuple[re.Pattern[str], str]] = {
    "Lakehouse": (
        re.compile(r"[A-Za-z][A-Za-z0-9_]{0,122}"),
        "a lakehouse name starts with a letter and holds only letters, "
        "digits and underscores, up to 123 characters",
    ),
}


def name_problem(item_type: str, display_name: str) -> str | None:
    """
    Say why Fabric would refuse a display name for an item type.

    Only the rules Fabric documents are checked, so that an item is not
    held back by a guess: a lakehouse name starts with a letter and holds
    only letters, digits and underscores, up to 123 characters.

    Args:
        item_type (str): The Fabric item type.
        display_name (str): The display name to create the item under.

    Returns:
        str | None: What Fabric expects, when the name breaks one of its
            rules; None otherwise.
    """
    rule = _NAME_RULES.get(item_type)
    if rule is None or rule[0].fullmatch(display_name):
        return None
    return rule[1]


def _action(
    item: SourceItem,
    action: DeploymentActionType,
    detail: str | None = None,
    *,
    reason: DeploymentReason | None = None,
) -> DeploymentAction:
    """Plan an action for an item, with the reason its change gives."""
    return DeploymentAction(
        action=action,
        item_type=item.item_type,
        display_name=item.display_name,
        source_path=item.source_path,
        reason=reason or _REASONS[item.change],
        folder_path=item.folder_path,
        detail=detail,
    )


def _key(action: DeploymentAction) -> ItemKey:
    """Return the ``(item_type, display_name)`` of a named action."""
    return action.item_type, action.display_name or ""


def _name(key: ItemKey) -> str:
    """Name an item as ``DisplayName.Type`` for a detail."""
    item_type, display_name = key
    return f"{display_name}.{item_type}"


def _block(action: DeploymentAction, detail: str) -> DeploymentAction:
    """Turn a planned action into a blocked one, keeping its reason."""
    return replace(action, action=DeploymentActionType.BLOCKED, detail=detail)


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
