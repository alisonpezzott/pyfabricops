"""Tests for dependency resolution in the deployment planner."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence

from pyfabricops.helpers.dependency_graph import (
    Dependency,
    DependencyGraph,
    ItemKey,
)
from pyfabricops.helpers.deployment_plan import (
    DeployedItem,
    DeploymentPlan,
    DeploymentPlanner,
    SourceChange,
    SourceItem,
)

REPORT = ("Report", "Sales")
MODEL = ("SemanticModel", "Sales")
LAKEHOUSE = ("Lakehouse", "Gold")
LOAD = ("Notebook", "Load")
CLEAN = ("Notebook", "Clean")
AUDIT = ("Notebook", "Audit")


def _item(
    key: ItemKey,
    change: SourceChange | None = SourceChange.MODIFIED,
    content_hash: str | None = None,
) -> SourceItem:
    """A local item, selected when it changed; available when change=None."""
    item_type, name = key
    return SourceItem(
        item_type=item_type,
        source_path=f"ws/{name}.{item_type}",
        display_name=name,
        change=change,
        content_hash=content_hash,
    )


def _plan(
    items: Iterable[SourceItem],
    *,
    edges: Iterable[tuple[ItemKey, ItemKey]] = (),
    existing: Collection[ItemKey] = (),
    available: Iterable[ItemKey] = (),
    broken: Mapping[ItemKey, Sequence[str]] | None = None,
    item_types: Collection[str] | None = None,
    deployed: Mapping[ItemKey, DeployedItem] | None = None,
) -> DeploymentPlan:
    graph = DependencyGraph(
        Dependency(source, target, "definition.pbir byPath")
        for source, target in edges
    )
    planner = DeploymentPlanner(
        existing,
        deployed,
        dependencies=graph,
        broken=broken,
        item_types=item_types,
    )
    return planner.plan(
        items, available=[_item(key, change=None) for key in available]
    )


def _lines(plan: DeploymentPlan) -> list[tuple[str, str, str]]:
    """Each action as (action, Name.Type, reason)."""
    return [
        (a.action.value, f"{a.display_name}.{a.item_type}", a.reason.value)
        for a in plan.actions
    ]


# ---------------------------------------------------------------------------
# The roadmap cases
# ---------------------------------------------------------------------------


def test_a_needed_item_in_the_workspace_is_validated_not_deployed() -> None:
    """The report changed, its model did not: only the report goes."""
    plan = _plan(
        [_item(REPORT)],
        edges=[(REPORT, MODEL)],
        existing={REPORT, MODEL},
        available=[MODEL],
    )

    assert _lines(plan) == [
        ("NOOP", "Sales.SemanticModel", "DEPENDENCY_REQUIRED"),
        ("UPDATE", "Sales.Report", "SOURCE_CHANGED"),
    ]
    assert plan.actions[0].detail == (
        "Required by Sales.Report (definition.pbir byPath); already in the "
        "workspace."
    )


def test_a_changed_dependency_is_deployed_first() -> None:
    """Both changed: the model before the report, whatever the order given."""
    plan = _plan(
        [_item(REPORT), _item(MODEL)],
        edges=[(REPORT, MODEL)],
        existing={REPORT, MODEL},
    )

    assert _lines(plan) == [
        ("UPDATE", "Sales.SemanticModel", "SOURCE_CHANGED"),
        ("UPDATE", "Sales.Report", "SOURCE_CHANGED"),
    ]


def test_a_missing_dependency_of_the_source_is_created_first() -> None:
    """The workspace lacks the model: it is created before the report."""
    plan = _plan(
        [_item(REPORT)],
        edges=[(REPORT, MODEL)],
        existing={REPORT},
        available=[MODEL],
    )

    assert _lines(plan) == [
        ("CREATE", "Sales.SemanticModel", "DEPENDENCY_REQUIRED"),
        ("UPDATE", "Sales.Report", "SOURCE_CHANGED"),
    ]
    assert plan.actions[0].detail == (
        "Required by Sales.Report (definition.pbir byPath) and missing from "
        "the workspace."
    )


# ---------------------------------------------------------------------------
# What cannot be met
# ---------------------------------------------------------------------------


def test_a_missing_dependency_outside_the_item_types_blocks_its_user() -> None:
    """A run limited to reports creates no model; the report waits."""
    plan = _plan(
        [_item(REPORT)],
        edges=[(REPORT, MODEL)],
        existing={REPORT},
        available=[MODEL],
        item_types={"Report"},
    )

    assert _lines(plan) == [("BLOCKED", "Sales.Report", "SOURCE_CHANGED")]
    assert plan.actions[0].detail == (
        "Needs Sales.SemanticModel, which is missing from the workspace and "
        "not among the item types of this run."
    )


def test_a_broken_reference_blocks_the_item() -> None:
    """The scan's reason is the detail."""
    problem = (
        "definition.pbir points to ../Gone.SemanticModel, which is not a "
        "semantic model of the source."
    )

    plan = _plan([_item(REPORT)], broken={REPORT: [problem]})

    assert _lines(plan) == [("BLOCKED", "Sales.Report", "SOURCE_CHANGED")]
    assert plan.actions[0].detail == problem


def test_items_in_a_cycle_are_blocked_and_so_is_what_needs_them() -> None:
    """Neither can go first, so neither goes, nor what needs them."""
    plan = _plan(
        [_item(AUDIT), _item(LOAD), _item(CLEAN)],
        edges=[(LOAD, CLEAN), (CLEAN, LOAD), (AUDIT, LOAD)],
    )

    details = {
        f"{a.display_name}.{a.item_type}": (a.action.value, a.detail)
        for a in plan.actions
    }
    cycle = "Part of a dependency cycle: Load.Notebook, Clean.Notebook."
    assert details == {
        "Load.Notebook": ("BLOCKED", cycle),
        "Clean.Notebook": ("BLOCKED", cycle),
        "Audit.Notebook": (
            "BLOCKED",
            "Needs Load.Notebook, which is blocked.",
        ),
    }


def test_what_needs_a_blocked_item_is_blocked_in_turn() -> None:
    """The model cannot be created without its lakehouse, so neither goes."""
    plan = _plan(
        [_item(REPORT)],
        edges=[(REPORT, MODEL), (MODEL, LAKEHOUSE)],
        existing={REPORT},
        available=[LAKEHOUSE, MODEL],
        item_types={"Report", "SemanticModel"},
    )

    assert [(a.action.value, a.detail) for a in plan.actions] == [
        (
            "BLOCKED",
            "Needs Gold.Lakehouse, which is missing from the workspace and "
            "not among the item types of this run.",
        ),
        ("BLOCKED", "Needs Sales.SemanticModel, which is blocked."),
    ]


# ---------------------------------------------------------------------------
# Where resolution stops
# ---------------------------------------------------------------------------


def test_what_a_validated_item_needs_is_left_alone() -> None:
    """The model in the workspace already works with what it has."""
    plan = _plan(
        [_item(REPORT)],
        edges=[(REPORT, MODEL), (MODEL, LAKEHOUSE)],
        existing={REPORT, MODEL},
        available=[LAKEHOUSE, MODEL],
    )

    assert _lines(plan) == [
        ("NOOP", "Sales.SemanticModel", "DEPENDENCY_REQUIRED"),
        ("UPDATE", "Sales.Report", "SOURCE_CHANGED"),
    ]


def test_an_item_that_needs_nothing_done_pulls_nothing() -> None:
    """An unchanged report does not bring its missing model along."""
    plan = _plan(
        [_item(REPORT, content_hash="h1")],
        edges=[(REPORT, MODEL)],
        existing={REPORT},
        available=[MODEL],
        deployed={REPORT: DeployedItem("h1")},
    )

    assert _lines(plan) == [("NOOP", "Sales.Report", "SOURCE_CHANGED")]


def test_without_a_graph_nothing_is_added_or_reordered() -> None:
    """dependencies=None keeps the planner as it was."""
    planner = DeploymentPlanner({REPORT, MODEL})

    plan = planner.plan(
        [_item(REPORT), _item(MODEL)],
        available=[_item(LAKEHOUSE, change=None)],
    )

    assert _lines(plan) == [
        ("UPDATE", "Sales.Report", "SOURCE_CHANGED"),
        ("UPDATE", "Sales.SemanticModel", "SOURCE_CHANGED"),
    ]


def test_deletions_and_unreadable_items_keep_their_places() -> None:
    """Resolution reorders what it can name; deletions still come last."""
    unreadable = SourceItem(
        "Notebook",
        "ws/Broken.Notebook",
        error="ws/Broken.Notebook: no .platform",
    )

    plan = _plan(
        [
            _item(LOAD, change=SourceChange.DELETED),
            _item(REPORT),
            unreadable,
            _item(MODEL),
        ],
        edges=[(REPORT, MODEL)],
        existing={REPORT, MODEL, LOAD},
    )

    assert [(a.action.value, a.source_path) for a in plan.actions] == [
        ("UPDATE", "ws/Sales.SemanticModel"),
        ("UPDATE", "ws/Sales.Report"),
        ("BLOCKED", "ws/Broken.Notebook"),
        ("DELETE", "ws/Load.Notebook"),
    ]
