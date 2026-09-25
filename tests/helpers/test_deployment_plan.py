"""Tests for the deployment planner in pyfabricops.helpers.deployment_plan."""

from __future__ import annotations

import ast
import dataclasses
import inspect
import sys
from collections.abc import Collection

import pytest

from pyfabricops.helpers import deployment_plan
from pyfabricops.helpers.deployment_plan import (
    DeployedItem,
    DeploymentAction,
    DeploymentActionType,
    DeploymentPlan,
    DeploymentPlanner,
    DeploymentReason,
    SourceChange,
    SourceItem,
)

CREATE = DeploymentActionType.CREATE
UPDATE = DeploymentActionType.UPDATE
MOVE = DeploymentActionType.MOVE
DELETE = DeploymentActionType.DELETE
NOOP = DeploymentActionType.NOOP
BLOCKED = DeploymentActionType.BLOCKED


def _item(
    name: str, item_type: str = "Notebook", folder: str | None = None
) -> SourceItem:
    """A readable local item under workspace/, optionally in a folder."""
    parent = f"workspace/{folder}" if folder else "workspace"
    return SourceItem(
        item_type=item_type,
        source_path=f"{parent}/{name}.{item_type}",
        display_name=name,
        folder_path=folder,
    )


def _broken(name: str) -> SourceItem:
    """A local item whose .platform could not be read."""
    path = f"workspace/{name}.Notebook"
    return SourceItem(
        item_type="Notebook",
        source_path=path,
        error=f"{path}/.platform not found.",
    )


def _changed(
    name: str,
    change: SourceChange | None,
    item_type: str = "Notebook",
    folder: str | None = None,
) -> SourceItem:
    """A local item that changed since the baseline commit."""
    return dataclasses.replace(_item(name, item_type, folder), change=change)


def _plan(
    items: list[SourceItem],
    existing: Collection[tuple[str, str]] = (),
    root: str | None = None,
) -> DeploymentPlan:
    return DeploymentPlanner(existing_items=existing, root=root).plan(items)


# ---------------------------------------------------------------------------
# One action per item
# ---------------------------------------------------------------------------


def test_no_items_give_an_empty_plan() -> None:
    """Nothing selected, nothing planned."""
    assert _plan([]) == DeploymentPlan(actions=[])


def test_one_item_gives_one_action() -> None:
    """The action says what happens, to which item, where and why."""
    plan = _plan([_item("Orders", folder="Sales")])

    assert plan.actions == (
        DeploymentAction(
            action=CREATE,
            item_type="Notebook",
            display_name="Orders",
            source_path="workspace/Sales/Orders.Notebook",
            reason=DeploymentReason.FULL_DEPLOYMENT,
            folder_path="Sales",
        ),
    )


@pytest.mark.parametrize("count", [2, 25])
def test_n_items_give_n_actions_in_the_given_order(count: int) -> None:
    """The planner keeps the order of the selection, dependency order."""
    items = [_item(f"Item{n:02}") for n in range(count)]

    plan = _plan(items)

    assert len(plan.actions) == count
    assert [a.source_path for a in plan.actions] == [
        i.source_path for i in items
    ]


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------


def test_items_in_the_workspace_are_updated_and_others_created() -> None:
    """Only the same type and display name counts as the same item."""
    plan = _plan(
        [_item("Orders"), _item("Orders", "Report"), _item("Sales")],
        existing={("Notebook", "Orders"), ("Notebook", "Legacy")},
    )

    assert [a.action for a in plan.actions] == [UPDATE, CREATE, CREATE]


def test_an_unreadable_item_is_blocked_in_its_place() -> None:
    """The item stays in the plan, so it is reported where it was found."""
    broken = _broken("Broken")

    plan = _plan([_item("A"), broken, _item("B")])

    assert [a.action for a in plan.actions] == [CREATE, BLOCKED, CREATE]
    blocked = plan.actions[1]
    assert blocked.display_name is None
    assert blocked.detail == broken.error
    assert blocked.reason is DeploymentReason.FULL_DEPLOYMENT


def test_an_item_without_a_display_name_is_blocked() -> None:
    """Without a display name there is no workspace item to match."""
    (action,) = _plan([SourceItem("Notebook", "workspace/X.Notebook")]).actions

    assert action.action == BLOCKED
    assert action.detail == "workspace/X.Notebook has no display name."


def test_a_duplicate_identity_blocks_the_later_item() -> None:
    """Two local folders for one workspace item would overwrite each other."""
    plan = _plan(
        [_item("Orders", folder="A"), _item("Orders", folder="B")],
        existing={("Notebook", "Orders")},
    )

    assert [a.action for a in plan.actions] == [UPDATE, BLOCKED]
    assert plan.actions[1].detail == (
        "Orders.Notebook is also defined at workspace/A/Orders.Notebook; "
        "deploying both would overwrite the same item."
    )


# ---------------------------------------------------------------------------
# Changes since a baseline commit
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (None, DeploymentReason.FULL_DEPLOYMENT),
        (SourceChange.ADDED, DeploymentReason.ITEM_ADDED),
        (SourceChange.MODIFIED, DeploymentReason.SOURCE_CHANGED),
        (SourceChange.DELETED, DeploymentReason.ITEM_DELETED),
    ],
)
def test_the_reason_follows_how_the_item_changed(
    change: SourceChange | None, reason: DeploymentReason
) -> None:
    """Every action says why the item is in the plan."""
    (action,) = _plan([_changed("Orders", change)]).actions

    assert action.reason is reason


def test_a_changed_item_missing_from_the_workspace_is_created() -> None:
    """The source says modified, the workspace lacks it: create it."""
    (action,) = _plan([_changed("Orders", SourceChange.MODIFIED)]).actions

    assert action.action == CREATE


def test_a_deleted_item_in_the_workspace_is_planned_for_deletion() -> None:
    """The plan says DELETE; refusing it is the executor's business."""
    (action,) = _plan(
        [_changed("Old", SourceChange.DELETED)],
        existing={("Notebook", "Old")},
    ).actions

    assert action.action == DELETE
    assert action.detail == (
        "Refused until deletions are allowed: delete it from the workspace "
        "by hand."
    )


def test_a_deleted_item_gone_from_the_workspace_needs_nothing() -> None:
    """Nothing to delete, so nothing to refuse."""
    (action,) = _plan([_changed("Old", SourceChange.DELETED)]).actions

    assert action.action == NOOP
    assert action.detail == "Deleted from the source and not in the workspace."


def test_deletions_come_after_every_other_action() -> None:
    """Creates and updates go first, whatever order the items came in."""
    plan = _plan(
        [
            _changed("Old", SourceChange.DELETED),
            _changed("Orders", SourceChange.MODIFIED),
            _changed("Sales", SourceChange.ADDED, "Report"),
        ],
        existing={("Notebook", "Old"), ("Notebook", "Orders")},
    )

    assert [(a.action, a.display_name) for a in plan.actions] == [
        (UPDATE, "Orders"),
        (CREATE, "Sales"),
        (DELETE, "Old"),
    ]


def test_a_moved_item_is_updated_not_deleted() -> None:
    """Its old folder is gone, but the same item is defined elsewhere."""
    plan = _plan(
        [
            _changed("Orders", SourceChange.DELETED, folder="Sales"),
            _changed("Orders", SourceChange.ADDED, folder="Finance"),
        ],
        existing={("Notebook", "Orders")},
    )

    assert [(a.action, a.folder_path) for a in plan.actions] == [
        (UPDATE, "Finance"),
        (NOOP, "Sales"),
    ]
    assert plan.actions[1].detail == (
        "Still defined at workspace/Finance/Orders.Notebook."
    )


def test_a_workspace_item_is_deleted_once() -> None:
    """Two deleted folders for one workspace item give one DELETE."""
    plan = _plan(
        [
            _changed("Old", SourceChange.DELETED, folder="A"),
            _changed("Old", SourceChange.DELETED, folder="B"),
        ],
        existing={("Notebook", "Old")},
    )

    assert [a.action for a in plan.actions] == [DELETE, NOOP]
    assert plan.actions[1].detail == (
        "Its deletion is planned with workspace/A/Old.Notebook."
    )


def test_details_show_other_item_folders_relative_to_the_root() -> None:
    """The prefix of a staging folder would only add noise to each detail."""
    moved = _plan(
        [
            _changed("Orders", SourceChange.DELETED, folder="Sales"),
            _changed("Orders", SourceChange.ADDED, folder="Finance"),
        ],
        existing={("Notebook", "Orders")},
        root="workspace",
    )
    deleted_twice = _plan(
        [
            _changed("Old", SourceChange.DELETED, folder="A"),
            _changed("Old", SourceChange.DELETED, folder="B"),
        ],
        existing={("Notebook", "Old")},
        root="workspace",
    )
    duplicate = _plan(
        [_item("Orders", folder="A"), _item("Orders", folder="B")],
        root="workspace",
    )

    assert moved.actions[1].detail == (
        "Still defined at Finance/Orders.Notebook."
    )
    assert deleted_twice.actions[1].detail == (
        "Its deletion is planned with A/Old.Notebook."
    )
    assert duplicate.actions[1].detail == (
        "Orders.Notebook is also defined at A/Orders.Notebook; deploying "
        "both would overwrite the same item."
    )


def test_a_folder_outside_the_root_is_shown_as_given() -> None:
    """Nothing to show it relative to, so the full path stays."""
    plan = _plan(
        [
            _changed("Orders", SourceChange.DELETED, folder="Sales"),
            _changed("Orders", SourceChange.ADDED, folder="Finance"),
        ],
        existing={("Notebook", "Orders")},
        root="elsewhere",
    )

    assert plan.actions[1].detail == (
        "Still defined at workspace/Finance/Orders.Notebook."
    )


def test_a_deleted_item_with_an_unreadable_baseline_is_blocked() -> None:
    """Without its old name there is no workspace item to match."""
    broken = dataclasses.replace(_broken("Old"), change=SourceChange.DELETED)

    (action,) = _plan([broken]).actions

    assert (action.action, action.reason) == (
        BLOCKED,
        DeploymentReason.ITEM_DELETED,
    )


# ---------------------------------------------------------------------------
# What the last successful deployment sent
# ---------------------------------------------------------------------------


def _sent(content_hash: str | None, folder: str | None = None) -> SourceItem:
    """Orders.Notebook, changed in Git, with the hash of its definition."""
    return dataclasses.replace(
        _changed("Orders", SourceChange.MODIFIED, folder=folder),
        content_hash=content_hash,
    )


def _plan_after(
    item: SourceItem,
    deployed: DeployedItem,
    existing: Collection[tuple[str, str]] = (("Notebook", "Orders"),),
) -> DeploymentAction:
    """Plan one item against what its last deployment sent."""
    planner = DeploymentPlanner(
        existing_items=existing,
        deployed_items={("Notebook", "Orders"): deployed},
    )
    (action,) = planner.plan([item]).actions
    return action


def test_an_item_sent_unchanged_needs_nothing() -> None:
    """A candidate whose definition was already sent is a NOOP."""
    action = _plan_after(_sent("h1"), DeployedItem("h1"))

    assert action.action == NOOP
    assert action.reason is DeploymentReason.SOURCE_CHANGED
    assert action.detail == (
        "Definition and folder unchanged since the last successful deployment."
    )


def test_a_changed_definition_is_updated() -> None:
    """Another hash means another definition."""
    action = _plan_after(_sent("h2"), DeployedItem("h1"))

    assert action.action == UPDATE


def test_a_moved_item_with_the_same_definition_is_only_moved() -> None:
    """The definition was already sent; only the folder needs to change."""
    action = _plan_after(_sent("h1", folder="Sales"), DeployedItem("h1"))

    assert (action.action, action.folder_path) == (MOVE, "Sales")
    assert action.detail == (
        "Definition unchanged since the last successful deployment; folder "
        "changed from the workspace root to 'Sales'."
    )


def test_an_item_moved_to_the_root_is_moved_there() -> None:
    """The root is a folder like any other for a move."""
    action = _plan_after(_sent("h1"), DeployedItem("h1", folder_path="Sales"))

    assert (action.action, action.folder_path) == (MOVE, None)
    assert action.detail == (
        "Definition unchanged since the last successful deployment; folder "
        "changed from 'Sales' to the workspace root."
    )


def test_a_moved_item_with_a_new_definition_is_updated() -> None:
    """The update moves it too, so one action does both."""
    action = _plan_after(_sent("h2", folder="Sales"), DeployedItem("h1"))

    assert action.action == UPDATE


def test_an_item_missing_from_the_workspace_is_created_all_the_same() -> None:
    """What was sent once does not help when the item is gone."""
    action = _plan_after(_sent("h1"), DeployedItem("h1"), existing=())

    assert action.action == CREATE


def test_an_item_without_a_hash_is_deployed() -> None:
    """Without a hash there is nothing to compare."""
    action = _plan_after(_sent(None), DeployedItem("h1"))

    assert action.action == UPDATE


# ---------------------------------------------------------------------------
# A plan as text
# ---------------------------------------------------------------------------


def test_an_action_describes_itself_on_one_line() -> None:
    """What, to which item, and why; the detail after a colon."""
    update = _plan([_item("Orders")], existing={("Notebook", "Orders")})
    blocked = _plan([_broken("Broken")])

    assert update.actions[0].describe() == (
        "UPDATE   Orders.Notebook  FULL_DEPLOYMENT"
    )
    assert blocked.actions[0].describe() == (
        "BLOCKED  workspace/Broken.Notebook  FULL_DEPLOYMENT: "
        "workspace/Broken.Notebook/.platform not found."
    )


def test_a_plan_counts_and_describes_its_actions() -> None:
    """One line per action, then every action type counted."""
    plan = _plan(
        [_item("A"), _item("B"), _changed("Old", SourceChange.DELETED)],
        existing={("Notebook", "B")},
    )

    assert plan.summary() == {
        "CREATE": 1,
        "UPDATE": 1,
        "MOVE": 0,
        "DELETE": 0,
        "NOOP": 1,
        "BLOCKED": 0,
    }
    assert plan.describe().splitlines() == [
        "CREATE   A.Notebook  FULL_DEPLOYMENT",
        "UPDATE   B.Notebook  FULL_DEPLOYMENT",
        "NOOP     Old.Notebook  ITEM_DELETED: Deleted from the source and "
        "not in the workspace.",
        "1 create, 1 update, 0 move, 0 delete, 1 noop, 0 blocked",
    ]


def test_an_empty_plan_says_so() -> None:
    """Nothing to do is said, not left blank."""
    assert DeploymentPlan().describe() == (
        "No actions.\n0 create, 0 update, 0 move, 0 delete, 0 noop, 0 blocked"
    )


# ---------------------------------------------------------------------------
# Properties of a plan
# ---------------------------------------------------------------------------


def test_the_same_input_gives_the_same_plan() -> None:
    """Planning is deterministic, whatever collection types are passed."""
    items = [
        _item("Orders"),
        _item("Orders", folder="Copy"),
        _item("Sales", "Report"),
        _broken("Broken"),
    ]
    existing = [("Notebook", "Orders")]

    assert _plan(items, existing) == _plan(list(items), set(existing))


def test_a_plan_cannot_be_changed_once_built() -> None:
    """A plan can be inspected, then applied, exactly as it was decided."""
    plan = _plan([_item("Orders")])

    assert isinstance(plan.actions, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.actions[0].action = UPDATE  # type: ignore[misc]


def test_create_and_update_actions_need_a_display_name() -> None:
    """Only a blocked action may name no workspace item."""
    with pytest.raises(ValueError, match="needs a display name"):
        DeploymentAction(
            action=UPDATE,
            item_type="Notebook",
            display_name=None,
            source_path="workspace/X.Notebook",
            reason=DeploymentReason.FULL_DEPLOYMENT,
        )


def test_types_and_reasons_compare_equal_to_their_names() -> None:
    """Plain strings work, e.g. for logs or a serialized plan."""
    assert UPDATE == "UPDATE"
    assert DeploymentReason.FULL_DEPLOYMENT == "FULL_DEPLOYMENT"


def test_the_planner_cannot_reach_the_fabric_api() -> None:
    """
    The planning module imports only the standard library, and the
    dependency graph, which imports only the standard library itself.

    Nothing that talks to Fabric (the API client, requests, the other
    helpers) can be reached from it, so planning cannot create, update,
    move or delete anything.
    """
    tree = ast.parse(inspect.getsource(deployment_plan))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                assert (node.level, node.module) == (1, "dependency_graph"), (
                    "relative import in the planning module"
                )
                continue
            imported.add(node.module or "")

    assert {name.split(".")[0] for name in imported} <= sys.stdlib_module_names
