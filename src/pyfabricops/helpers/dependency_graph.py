"""
Dependency graph: which local items need which, and in what order.

An item depends on another when its definition refers to it, such as a
report on its semantic model. ``DependencyGraph`` holds those references
between items of the source and answers three questions for the planner:
what the selected items need (``required_by``), in which order to deploy
items so that each comes after what it needs (``order``), and which items
need one another (``cycles``). Like the planner, it calls no Fabric API and
reads no file: finding the references is the engine's job.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import TypeAlias

__all__ = ["Dependency", "DependencyGraph", "ItemKey"]

ItemKey: TypeAlias = tuple[str, str]
"""An item, as ``(item_type, display_name)``."""


@dataclass(frozen=True)
class Dependency:
    """
    A reference from one local item to another.

    Attributes:
        source (ItemKey): The item whose definition holds the reference.
        target (ItemKey): The item it refers to, needed first.
        via (str): Where the reference is, such as ``"definition.pbir"``,
            to explain it in a plan.
    """

    source: ItemKey
    target: ItemKey
    via: str


class DependencyGraph:
    """
    The references between local items.

    Args:
        dependencies (Iterable[Dependency], optional): The references found
            in the source; a repeated one counts once. Defaults to none.

    Examples:
        ```python
        report, model = ("Report", "Sales"), ("SemanticModel", "Sales")
        graph = DependencyGraph([Dependency(report, model, "definition.pbir")])
        graph.order([report, model])  # (model, report)
        ```
    """

    def __init__(self, dependencies: Iterable[Dependency] = ()) -> None:
        self._dependencies: dict[ItemKey, list[Dependency]] = {}
        for dependency in dict.fromkeys(dependencies):
            self._dependencies.setdefault(dependency.source, []).append(
                dependency
            )

    def dependencies_of(self, key: ItemKey) -> tuple[Dependency, ...]:
        """
        Return the references an item holds, in the order they were found.

        Args:
            key (ItemKey): The item.

        Returns:
            tuple[Dependency, ...]: Its references, possibly none.
        """
        return tuple(self._dependencies.get(key, ()))

    def required_by(self, keys: Iterable[ItemKey]) -> tuple[ItemKey, ...]:
        """
        Return every item the given ones need, directly or through others.

        Args:
            keys (Iterable[ItemKey]): The items to start from.

        Returns:
            tuple[ItemKey, ...]: The items they need, without the given ones,
                nearest first.
        """
        start = list(dict.fromkeys(keys))
        seen = set(start)
        pending = deque(start)
        required: list[ItemKey] = []
        while pending:
            for dependency in self.dependencies_of(pending.popleft()):
                if dependency.target not in seen:
                    seen.add(dependency.target)
                    required.append(dependency.target)
                    pending.append(dependency.target)
        return tuple(required)

    def order(self, keys: Sequence[ItemKey]) -> tuple[ItemKey, ...]:
        """
        Order items so that each comes after the items it needs.

        Only references between the given items count. Each item keeps its
        place in the order given, preceded by the items it needs that have
        not come yet, so a caller that sorts items by type and path first
        keeps that order wherever nothing else is needed. Items that need one
        another stay together, in the order given, after what they need.

        Args:
            keys (Sequence[ItemKey]): The items, in their default order.

        Returns:
            tuple[ItemKey, ...]: The same items, each after the ones it needs.
        """
        components = self._components(keys)
        component_of = {
            key: n for n, members in enumerate(components) for key in members
        }
        needs = [
            sorted(
                {
                    component_of[dependency.target]
                    for key in members
                    for dependency in self.dependencies_of(key)
                    if dependency.target in component_of
                }
                - {n}
            )
            for n, members in enumerate(components)
        ]

        ordered: list[ItemKey] = []
        placed = [False] * len(components)
        for root in range(len(components)):
            if placed[root]:
                continue
            placed[root] = True
            # Place what a component needs before the component itself.
            stack: list[tuple[int, Iterator[int]]] = [
                (root, iter(needs[root]))
            ]
            while stack:
                component, pending = stack[-1]
                for needed in pending:
                    if not placed[needed]:
                        placed[needed] = True
                        stack.append((needed, iter(needs[needed])))
                        break
                else:
                    stack.pop()
                    ordered.extend(components[component])
        return tuple(ordered)

    def cycles(
        self, keys: Sequence[ItemKey]
    ) -> tuple[tuple[ItemKey, ...], ...]:
        """
        Return the groups of items that need one another.

        Only references between the given items count; an item that refers
        to itself is a group on its own.

        Args:
            keys (Sequence[ItemKey]): The items to check.

        Returns:
            tuple[tuple[ItemKey, ...], ...]: Each group in the order given,
                the groups in the order of their first item.
        """
        return tuple(
            members
            for members in self._components(keys)
            if len(members) > 1
            or any(
                dependency.target == members[0]
                for dependency in self.dependencies_of(members[0])
            )
        )

    def _components(
        self, keys: Sequence[ItemKey]
    ) -> list[tuple[ItemKey, ...]]:
        """
        Group the items that reach one another through their references.

        Returns the strongly connected components of the references between
        the given items, each in the order given, ordered by their first item.
        """
        items = list(dict.fromkeys(keys))
        index = {key: n for n, key in enumerate(items)}
        forward = {
            key: [
                dependency.target
                for dependency in self.dependencies_of(key)
                if dependency.target in index
            ]
            for key in items
        }
        backward: dict[ItemKey, list[ItemKey]] = {key: [] for key in items}
        for key, targets in forward.items():
            for target in targets:
                backward[target].append(key)

        # First pass: the order in which items finish on the references.
        finished: list[ItemKey] = []
        visited: set[ItemKey] = set()
        for root in items:
            if root in visited:
                continue
            visited.add(root)
            stack: list[tuple[ItemKey, Iterator[ItemKey]]] = [
                (root, iter(forward[root]))
            ]
            while stack:
                key, pending = stack[-1]
                for target in pending:
                    if target not in visited:
                        visited.add(target)
                        stack.append((target, iter(forward[target])))
                        break
                else:
                    stack.pop()
                    finished.append(key)

        # Second pass: against the references, last finished first.
        assigned: set[ItemKey] = set()
        components: list[tuple[ItemKey, ...]] = []
        for root in reversed(finished):
            if root in assigned:
                continue
            assigned.add(root)
            members = [root]
            to_visit = [root]
            while to_visit:
                for source in backward[to_visit.pop()]:
                    if source not in assigned:
                        assigned.add(source)
                        members.append(source)
                        to_visit.append(source)
            components.append(tuple(sorted(members, key=index.__getitem__)))
        components.sort(key=lambda members: index[members[0]])
        return components
