"""Tests for the dependency graph in pyfabricops.helpers.dependency_graph."""

from __future__ import annotations

import ast
import inspect
import sys
from itertools import pairwise

from pyfabricops.helpers import dependency_graph
from pyfabricops.helpers.dependency_graph import (
    Dependency,
    DependencyGraph,
    ItemKey,
)

REPORT = ("Report", "Sales")
MODEL = ("SemanticModel", "Sales")
LAKEHOUSE = ("Lakehouse", "Gold")
LOAD = ("Notebook", "Load")
CLEAN = ("Notebook", "Clean")
AUDIT = ("Notebook", "Audit")


def _graph(*edges: tuple[ItemKey, ItemKey]) -> DependencyGraph:
    """A graph of source -> target references."""
    return DependencyGraph(
        Dependency(source, target, "test") for source, target in edges
    )


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------


def test_without_references_the_order_given_stays() -> None:
    """Nothing to reorder: the type and path order is kept as it is."""
    items = [LOAD, REPORT, LAKEHOUSE]
    graph = DependencyGraph()

    assert graph.order(items) == tuple(items)
    assert graph.required_by(items) == ()
    assert graph.cycles(items) == ()


def test_each_item_comes_after_what_it_needs() -> None:
    """A chain is deployed from its end."""
    graph = _graph((REPORT, MODEL), (MODEL, LAKEHOUSE))

    assert graph.order([REPORT, MODEL, LAKEHOUSE]) == (
        LAKEHOUSE,
        MODEL,
        REPORT,
    )


def test_only_what_is_needed_moves() -> None:
    """An item keeps its place, preceded by what it needs."""
    graph = _graph((LOAD, CLEAN))

    assert graph.order([AUDIT, LOAD, REPORT, CLEAN]) == (
        AUDIT,
        CLEAN,
        LOAD,
        REPORT,
    )


def test_references_to_items_not_given_are_ignored() -> None:
    """Ordering a selection does not add the items it needs."""
    graph = _graph((REPORT, MODEL))

    assert graph.order([REPORT, LOAD]) == (REPORT, LOAD)


def test_a_repeated_reference_counts_once() -> None:
    """The same reference found twice is one dependency."""
    graph = _graph((REPORT, MODEL), (REPORT, MODEL))

    assert graph.dependencies_of(REPORT) == (
        Dependency(REPORT, MODEL, "test"),
    )


# ---------------------------------------------------------------------------
# What a selection needs
# ---------------------------------------------------------------------------


def test_a_selection_needs_what_its_items_need_through_others() -> None:
    """Nearest first, each once, without the items given."""
    graph = _graph((REPORT, MODEL), (REPORT, LAKEHOUSE), (MODEL, LAKEHOUSE))

    assert graph.required_by([REPORT]) == (MODEL, LAKEHOUSE)
    assert graph.required_by([REPORT, MODEL]) == (LAKEHOUSE,)


# ---------------------------------------------------------------------------
# Cycles
# ---------------------------------------------------------------------------


def test_items_that_need_one_another_are_a_cycle() -> None:
    """Reported in the order given, and still ordered with the rest."""
    graph = _graph((CLEAN, LOAD), (LOAD, CLEAN), (AUDIT, CLEAN))

    assert graph.cycles([AUDIT, LOAD, CLEAN]) == ((LOAD, CLEAN),)
    assert graph.order([AUDIT, LOAD, CLEAN]) == (LOAD, CLEAN, AUDIT)


def test_an_item_that_refers_to_itself_is_a_cycle() -> None:
    """A notebook that runs itself cannot be deployed after itself."""
    graph = _graph((LOAD, LOAD))

    assert graph.cycles([LOAD, AUDIT]) == ((LOAD,),)
    assert graph.order([LOAD, AUDIT]) == (LOAD, AUDIT)


def test_a_long_chain_needs_no_recursion() -> None:
    """Thousands of items in one chain are ordered without a deep stack."""
    items = [("Notebook", f"N{n:05}") for n in range(5000)]
    graph = _graph(*pairwise(items))

    assert graph.order(items) == tuple(reversed(items))
    assert graph.cycles(items) == ()


# ---------------------------------------------------------------------------
# Purity
# ---------------------------------------------------------------------------


def test_the_graph_module_imports_only_the_standard_library() -> None:
    """Like the planner, it stays free of Fabric calls and file reads."""
    tree = ast.parse(inspect.getsource(dependency_graph))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import in the graph module"
            imported.add(node.module or "")

    assert {name.split(".")[0] for name in imported} <= sys.stdlib_module_names
