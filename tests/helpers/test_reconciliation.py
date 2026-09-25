"""Tests for the reconciliation of a workspace with the source."""

from __future__ import annotations

import ast
import dataclasses
import inspect
import sys
from collections.abc import Collection, Iterable, Mapping, Sequence

import pytest

from pyfabricops.helpers import reconciliation
from pyfabricops.helpers.dependency_graph import ItemKey
from pyfabricops.helpers.deployment_plan import DeployedItem, SourceItem
from pyfabricops.helpers.reconciliation import (
    Reconciliation,
    UnmanagedItem,
    WorkspaceItem,
    reconcile,
)

ORDERS = ("Notebook", "Orders")
BRONZE = ("Lakehouse", "Bronze")


def _item(
    key: ItemKey, folder: str | None = None, content_hash: str | None = "h1"
) -> SourceItem:
    item_type, name = key
    return SourceItem(
        item_type=item_type,
        source_path=f"ws/{name}.{item_type}",
        display_name=name,
        folder_path=folder,
        content_hash=content_hash,
    )


def _reconcile(
    items: Iterable[SourceItem],
    workspace: Iterable[WorkspaceItem],
    *,
    differences: Mapping[ItemKey, Sequence[str]] | None = None,
    unchecked: Mapping[ItemKey, str] | None = None,
    deployed: Mapping[ItemKey, DeployedItem] | None = None,
    source_keys: Collection[ItemKey] | None = None,
    deployable_types: Collection[str] | None = None,
    root: str | None = None,
) -> Reconciliation:
    """Reconcile, with no differences unless given."""
    return reconcile(
        items,
        workspace,
        differences=differences or {},
        unchecked=unchecked,
        deployed=deployed,
        source_keys=source_keys,
        deployable_types=deployable_types,
        root=root,
    )


def _lines(result: Reconciliation) -> list[tuple[str, str, str, str | None]]:
    return [
        (a.action.value, a.display_name or "", a.reason.value, a.detail)
        for a in result.plan.actions
    ]


# ---------------------------------------------------------------------------
# Items of the source
# ---------------------------------------------------------------------------


def test_an_item_that_matches_is_in_sync() -> None:
    """Same definition, same folder: nothing to bring back."""
    result = _reconcile(
        [_item(ORDERS)],
        [WorkspaceItem(*ORDERS)],
        differences={ORDERS: ()},
    )

    assert result.plan.actions == ()
    assert result.in_sync == (ORDERS,)
    assert result.ok


@pytest.mark.parametrize(
    ("deployed", "detail"),
    [
        (None, "In the source, not in the workspace."),
        (
            {ORDERS: DeployedItem("h1")},
            "Deleted from the workspace since the last deployment.",
        ),
    ],
)
def test_an_item_missing_from_the_workspace_would_be_created(
    deployed: Mapping[ItemKey, DeployedItem] | None, detail: str
) -> None:
    """With a deployment state, the item was there once."""
    result = _reconcile([_item(ORDERS)], [], deployed=deployed)

    assert _lines(result) == [("CREATE", "Orders", "TARGET_MISSING", detail)]
    assert not result.ok


def test_a_change_made_in_the_workspace_is_drift() -> None:
    """The source is as deployed, so the workspace changed."""
    result = _reconcile(
        [_item(ORDERS, content_hash="h1")],
        [WorkspaceItem(*ORDERS)],
        differences={ORDERS: ("notebook-content.py",)},
        deployed={ORDERS: DeployedItem("h1")},
    )

    assert _lines(result) == [
        (
            "UPDATE",
            "Orders",
            "WORKSPACE_DRIFT",
            "Changed in the workspace since the last deployment: "
            "notebook-content.py.",
        )
    ]


def test_a_change_made_in_the_source_is_a_deployment_to_run() -> None:
    """The source moved on since the last deployment."""
    result = _reconcile(
        [_item(ORDERS, content_hash="h2")],
        [WorkspaceItem(*ORDERS)],
        differences={ORDERS: ("notebook-content.py", ".platform")},
        deployed={ORDERS: DeployedItem("h1")},
    )

    assert _lines(result) == [
        (
            "UPDATE",
            "Orders",
            "SOURCE_CHANGED",
            "Changed in the source since the last deployment: "
            "notebook-content.py, .platform.",
        )
    ]


@pytest.mark.parametrize("content_hash", ["h1", None])
def test_without_a_deployment_state_a_difference_is_drift(
    content_hash: str | None,
) -> None:
    """Nothing tells which side changed: the source is what is desired."""
    result = _reconcile(
        [_item(ORDERS, content_hash=content_hash)],
        [WorkspaceItem(*ORDERS)],
        differences={ORDERS: ("notebook-content.py",)},
        deployed={} if content_hash else {ORDERS: DeployedItem("h1")},
    )

    assert _lines(result) == [
        (
            "UPDATE",
            "Orders",
            "WORKSPACE_DRIFT",
            "Differs from the source: notebook-content.py.",
        )
    ]


@pytest.mark.parametrize(
    ("deployed", "reason", "detail"),
    [
        (
            {ORDERS: DeployedItem("h1", "Sales")},
            "WORKSPACE_DRIFT",
            "Moved to 'Archive' in the workspace since the last deployment; "
            "the source has it in 'Sales'.",
        ),
        (
            {ORDERS: DeployedItem("h1", "Archive")},
            "SOURCE_CHANGED",
            "Moved to 'Sales' in the source since the last deployment; the "
            "workspace has it in 'Archive'.",
        ),
        (
            None,
            "WORKSPACE_DRIFT",
            "In 'Archive' in the workspace, 'Sales' in the source.",
        ),
    ],
)
def test_an_item_in_another_folder_would_be_moved(
    deployed: Mapping[ItemKey, DeployedItem] | None, reason: str, detail: str
) -> None:
    """The deployment state tells who moved it, when there is one."""
    result = _reconcile(
        [_item(ORDERS, folder="Sales")],
        [WorkspaceItem(*ORDERS, folder_path="Archive")],
        differences={ORDERS: ()},
        deployed=deployed,
    )

    assert _lines(result) == [("MOVE", "Orders", reason, detail)]


def test_a_changed_item_in_another_folder_is_updated_with_a_note() -> None:
    """An update also moves the item, so one action says both."""
    result = _reconcile(
        [_item(ORDERS)],
        [WorkspaceItem(*ORDERS, folder_path="Archive")],
        differences={ORDERS: ("notebook-content.py",)},
    )

    assert _lines(result) == [
        (
            "UPDATE",
            "Orders",
            "WORKSPACE_DRIFT",
            "Differs from the source: notebook-content.py. It is in "
            "'Archive' in the workspace, the workspace root in the source.",
        )
    ]


def test_an_item_whose_definition_was_not_compared_is_unchecked() -> None:
    """In the workspace and in its folder, but not known to match."""
    result = _reconcile(
        [_item(BRONZE)],
        [WorkspaceItem(*BRONZE)],
        unchecked={BRONZE: "Fabric returned no definition."},
    )

    assert result.plan.actions == ()
    assert dict(result.unchecked) == {BRONZE: "Fabric returned no definition."}
    assert result.in_sync == ()
    assert result.ok


def test_an_unchecked_item_in_another_folder_would_still_be_moved() -> None:
    """Its folder is known, whatever its definition."""
    result = _reconcile(
        [_item(BRONZE, folder="Data")],
        [WorkspaceItem(*BRONZE)],
        unchecked={BRONZE: "Fabric returned no definition."},
    )

    assert [a.action.value for a in result.plan.actions] == ["MOVE"]
    assert list(result.unchecked) == [BRONZE]


def test_an_unreadable_or_repeated_local_item_is_blocked() -> None:
    """As in a deployment plan, in its place."""
    unreadable = SourceItem(
        "Notebook", "ws/Broken.Notebook", error="ws/Broken.Notebook: no name"
    )
    twin = dataclasses.replace(
        _item(ORDERS), source_path="ws/B/Orders.Notebook"
    )

    result = _reconcile(
        [unreadable, _item(ORDERS), twin],
        [WorkspaceItem(*ORDERS)],
        differences={ORDERS: ()},
        root="ws",
    )

    assert [(a.action.value, a.detail) for a in result.plan.actions] == [
        ("BLOCKED", "ws/Broken.Notebook: no name"),
        (
            "BLOCKED",
            "Orders.Notebook is also defined at Orders.Notebook; the source "
            "cannot hold it twice.",
        ),
    ]


# ---------------------------------------------------------------------------
# Items of the workspace only
# ---------------------------------------------------------------------------


def test_an_item_the_source_lacks_is_unmanaged() -> None:
    """Every type counts, but the endpoint that comes with a lakehouse."""
    result = _reconcile(
        [_item(BRONZE)],
        [
            WorkspaceItem(*BRONZE),
            WorkspaceItem("SQLEndpoint", "Bronze"),
            WorkspaceItem("Notebook", "Draft", folder_path="Sandbox"),
            WorkspaceItem("KQLDatabase", "Logs"),
        ],
        differences={BRONZE: ()},
        deployable_types={"Lakehouse", "Notebook"},
    )

    assert result.unmanaged == (
        UnmanagedItem("Notebook", "Draft", "Sandbox", deployable=True),
        UnmanagedItem("KQLDatabase", "Logs", None, deployable=False),
    )
    assert not result.ok


def test_an_item_of_the_source_outside_the_scope_is_not_unmanaged() -> None:
    """A run limited to some types still knows the rest of the source."""
    result = _reconcile(
        [_item(ORDERS)],
        [WorkspaceItem(*ORDERS), WorkspaceItem(*BRONZE)],
        differences={ORDERS: ()},
        source_keys={ORDERS, BRONZE},
    )

    assert result.unmanaged == ()


# ---------------------------------------------------------------------------
# The result
# ---------------------------------------------------------------------------


def test_a_reconciliation_describes_what_differs_then_the_counts() -> None:
    """One line per finding, then how many of each."""
    result = _reconcile(
        [_item(ORDERS), _item(BRONZE), _item(("Report", "Sales"))],
        [
            WorkspaceItem(*ORDERS),
            WorkspaceItem(*BRONZE),
            WorkspaceItem("Notebook", "Draft"),
        ],
        differences={ORDERS: ("notebook-content.py",)},
        unchecked={BRONZE: "Fabric returned no definition."},
    )

    assert result.describe() == "\n".join(
        [
            "UPDATE   Orders.Notebook  WORKSPACE_DRIFT: Differs from the "
            "source: notebook-content.py.",
            "CREATE   Sales.Report  TARGET_MISSING: In the source, not in the "
            "workspace.",
            "UNMANAGED Draft.Notebook: in the workspace, not in the source.",
            "UNCHECKED Bronze.Lakehouse: Fabric returned no definition.",
            "0 in sync, 1 create, 1 update, 0 move, 0 blocked, 1 unmanaged, "
            "1 unchecked",
        ]
    )


def test_a_reconciliation_cannot_be_changed_once_made() -> None:
    """What it found stays as it was reported."""
    result = _reconcile(
        [_item(ORDERS)],
        [WorkspaceItem(*ORDERS)],
        differences={ORDERS: ()},
    )

    assert isinstance(result.in_sync, tuple)
    assert isinstance(result.unmanaged, tuple)
    with pytest.raises(TypeError):
        result.unchecked[ORDERS] = "changed"  # type: ignore[index]


def test_the_reconciliation_cannot_reach_the_fabric_api() -> None:
    """
    The module imports only the standard library and the pure planning
    modules, so a reconciliation cannot change the workspace.
    """
    imported: set[str] = set()
    for node in ast.walk(ast.parse(inspect.getsource(reconciliation))):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                assert node.level == 1
                assert node.module in {"dependency_graph", "deployment_plan"}
                continue
            imported.add(node.module or "")

    assert {name.split(".")[0] for name in imported} <= sys.stdlib_module_names
