"""
Deploy the Fabric items of a Git repository to a workspace.

The sample is Adventure Works LT as Fabric Git integration writes it from a
DEV workspace connected to ``fabric-workspace``; this script deploys it to
PRD. Copy this folder as the root of a repository, connect your DEV
workspace to it, and run the deployment from Azure DevOps
(``azure-pipelines.yml``) or GitHub Actions (``.github/workflows``).

The workspace connected to the repository, the source workspace, writes its
own IDs in the definitions: the default lakehouse of a notebook, the OneLake
path of a semantic model, the logical IDs of the items of the same
workspace in a pipeline or a shortcut. Sent as they are, the items of the
target workspace would read and write the source one.

So the items are copied to a staging folder, where each ID of the source
workspace becomes the ID of the same item, by type and name, in the target
workspace, as Fabric lists both at every run. The repository is never
changed, and the script holds no name or ID. A shortcut to an item of the
same workspace gets the logical ID of that item in the target, since Fabric
looks it up among the items of the workspace.

The variable libraries are sent as they are: their value sets hold what
differs between environments, such as the database of each ingestion. Once
they are deployed, the value set of the target is made active in them.

The item types are deployed one at a time, in the dependency order of
pyfabricops and pipelines last, so that an item refers by ID only to items
already in the target workspace. Within a type, the items the others refer
to are created first, such as a lakehouse a shortcut points to. A run stops
before it sends an item that would still refer to the source workspace.

With a deployment state, in a lakehouse (--state-workspace and
--state-lakehouse) or in a folder (--state-dir), a run deploys only what
changed in Git since the last successful one, and holds a lock, so that two
runs never deploy at a time.

Instead of deploying, --plan prints the plan; --reconcile reports how the
target stands against the repository, its active value sets included, and
changes nothing; --restore brings back what drifted there, and deletes
nothing.

Usage::

    python deploy.py --source-workspace <source> --workspace <target> \\
        --value-set <value set> [--plan | --reconcile | --restore]
    python deploy.py --source-workspace <source> --workspace <target> \\
        --value-set <value set> \\
        --state-workspace <workspace> --state-lakehouse <lakehouse>
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# pyfabricops 0.7 ships no py.typed marker, so mypy cannot read its types.
import pyfabricops as pf  # type: ignore[import-untyped]

ItemKey = tuple[str, str]
# deploy_all_items or restore_items: what a run does to the items of a type.
Operation = Callable[..., Any]

# The Git folder of the source workspace, as its Git integration names it.
SOURCE = Path(__file__).resolve().parent / "fabric-workspace"
# A pipeline refers to what it runs by ID, so pipelines go last.
ITEM_TYPES = [t for t in pf.DEPLOY_ORDER if t != "DataPipeline"] + [
    "DataPipeline"
]
# The empty GUID, which Fabric writes for "this workspace".
THIS_WORKSPACE = "00000000-0000-0000-0000-000000000000"
# The shortcuts of a lakehouse, which get the IDs of the target one by one.
SHORTCUTS = "shortcuts.metadata.json"
# The files that get the IDs of the target as text: all but the shortcuts, a
# .platform, which holds the identity of its item, and the files of the
# variable libraries.
MAPPED = (
    r"^(?!.*\.VariableLibrary[\\/])(?!.*shortcuts\.metadata\.json$)"
    r".*(?<!\.platform)$"
)
# In pipelines and notebooks, the empty GUID of a workspace gets the target.
REFERRERS = r"(pipeline-content\.json|notebook-content\.\w+)$"
EMPTY_WORKSPACE = (
    r'("(?:workspaceId|default_lakehouse_workspace_id)"\s*:\s*")'
    + THIS_WORKSPACE
    + r'(")'
)


def label(key: ItemKey) -> str:
    """An item as Fabric Git integration names its folder."""
    return f"{key[1]}.{key[0]}"


@dataclass(frozen=True)
class SourceItem:
    """An item of the repository, as its .platform describes it."""

    item_type: str
    name: str
    logical_id: str | None
    folder: Path

    @property
    def key(self) -> ItemKey:
        """The identity of the item: its type and display name."""
        return (self.item_type, self.name)


def read_items(staging: Path) -> list[SourceItem]:
    """The items of the staging folder, from their .platform."""
    items: list[SourceItem] = []
    for platform in sorted(staging.rglob(".platform")):
        content = json.loads(platform.read_text(encoding="utf-8-sig"))
        metadata = content["metadata"]
        items.append(
            SourceItem(
                item_type=metadata["type"],
                name=metadata["displayName"],
                logical_id=content.get("config", {}).get("logicalId"),
                folder=platform.parent,
            )
        )
    return items


def require_workspace(name: str) -> str:
    """The ID of a workspace; exits when the principal cannot see it."""
    workspace_id = pf.resolve_workspace(name)
    if workspace_id is None:
        raise SystemExit(
            f"Workspace {name} not found, or the service principal has no "
            "access to it."
        )
    return str(workspace_id)


def list_workspace(workspace_id: str) -> dict[ItemKey, dict[str, Any]]:
    """The items of a workspace, by type and display name."""
    items = pf.list_items(workspace_id, df=False)
    if items is None:
        raise SystemExit(
            f"Could not list the items of workspace {workspace_id}."
        )
    return {(item["type"], item["displayName"]): item for item in items}


class IdMap:
    """
    The ID in the target workspace of each ID of the source workspace.

    An item of the source workspace maps to the item of the same type and
    name in the target, by its ID and by its logical ID, and so does the
    logical ID of an item of the repository. The source workspace maps to
    the target.

    Args:
        source (str): The ID of the workspace connected to the repository.
        target (str): The ID of the workspace to deploy to.
        items (Sequence[SourceItem]): The items of the repository.
    """

    def __init__(
        self, source: str, target: str, items: Sequence[SourceItem]
    ) -> None:
        self.source = source.lower()
        self.target = target
        self.items = items
        # Every ID in lowercase, as Fabric returns them, with its item.
        self.known: dict[str, ItemKey] = {}
        for key, item in list_workspace(source).items():
            for value in (item.get("id"), item.get("logicalId")):
                if value:
                    self.known[str(value).lower()] = key
        for source_item in items:
            if source_item.logical_id:
                self.known[source_item.logical_id.lower()] = source_item.key
        self.target_items: dict[ItemKey, dict[str, Any]] = {}
        # The IDs of the items the target lacks yet.
        self.pending: dict[str, ItemKey] = {}
        self.refresh()

    def refresh(self) -> None:
        """List the target again, for the items deployed since."""
        self.target_items = list_workspace(self.target)
        self.pending = {
            old: key
            for old, key in self.known.items()
            if key not in self.target_items
        }

    def apply(self, staging: Path, shortcuts: Mapping[Path, str]) -> None:
        """
        Put the IDs of the target in the staged items.

        Args:
            staging (Path): The staging folder.
            shortcuts (Mapping[Path, str]): The staged shortcuts files, with
                their content in the repository.
        """
        replacements = {(MAPPED, "(?i)" + re.escape(self.source)): self.target}
        for old, key in self.known.items():
            if key in self.target_items:
                new = str(self.target_items[key]["id"])
                replacements[(MAPPED, "(?i)" + re.escape(old))] = new
        replacements[(REFERRERS, EMPTY_WORKSPACE)] = (
            rf"\g<1>{self.target}\g<2>"
        )
        pf.find_and_replace(str(staging), replacements)
        for file, text in shortcuts.items():
            pointed = [self.point(shortcut) for shortcut in json.loads(text)]
            file.write_text(json.dumps(pointed, indent=2), encoding="utf-8")

    def point(self, shortcut: dict[str, Any]) -> dict[str, Any]:
        """
        A OneLake shortcut to an item of the source workspace, pointed at the
        same item in the target.

        Fabric looks the logical ID of a shortcut to its own workspace up
        among the items of the workspace, so the shortcut gets the logical ID
        of the item in the target; the ID of the item, with the ID of the
        target workspace, when the item has none. Any other shortcut stays as
        it is, as does one to an item the target lacks yet: the lakehouse
        waits for it.
        """
        one_lake = shortcut.get("target", {}).get("oneLake")
        if not isinstance(one_lake, dict):
            return shortcut
        workspace = str(one_lake.get("workspaceId", "")).lower()
        key = self.known.get(str(one_lake.get("itemId", "")).lower())
        target = self.target_items.get(key) if key else None
        if workspace not in (THIS_WORKSPACE, self.source) or target is None:
            return shortcut
        pointed: dict[str, Any] = json.loads(json.dumps(shortcut))
        if target.get("logicalId"):
            pointed["target"]["oneLake"].update(
                workspaceId=THIS_WORKSPACE, itemId=str(target["logicalId"])
            )
        else:
            pointed["target"]["oneLake"].update(
                workspaceId=self.target, itemId=str(target["id"])
            )
        return pointed

    def references(self, item: SourceItem) -> tuple[set[ItemKey], bool]:
        """
        What a staged item still refers to in the source workspace.

        Returns:
            tuple[set[ItemKey], bool]: The items the target lacks that it
                refers to by ID, and whether it refers to the source
                workspace itself.
        """
        found: set[ItemKey] = set()
        workspace = False
        # A variable library holds the values of each environment itself.
        if item.item_type == "VariableLibrary":
            return found, workspace
        for file in sorted(p for p in item.folder.rglob("*") if p.is_file()):
            if file.name == ".platform":
                continue
            text = file.read_text(encoding="utf-8", errors="replace").lower()
            found |= {key for old, key in self.pending.items() if old in text}
            workspace = workspace or self.source in text
        found.discard(item.key)
        return found, workspace


def subset(staging: Path, items: Sequence[SourceItem], folder: Path) -> Path:
    """A copy of some staged items, in their folders, for a run of their own."""
    root = folder / staging.name
    for item in items:
        shutil.copytree(item.folder, root / item.folder.relative_to(staging))
    return root


def report(result: Any, title: str) -> bool:
    """Print what a run did; True when every item succeeded."""
    if result.results:
        print(f"== {title}")
        print(result.describe())
    return bool(result.ok)


def run_type(
    item_type: str,
    operation: Operation,
    workspace_id: str,
    staging: Path,
    arguments: Mapping[str, Any],
    ids: IdMap,
    shortcuts: Mapping[Path, str],
) -> bool:
    """
    Deploy or restore the items of a type; True when every item succeeded.

    The items the others refer to by ID are created first, in runs of their
    own and without the state, which the run of the whole type reads and,
    for a deployment, records.
    """
    items = [item for item in ids.items if item.item_type == item_type]
    sources = {item.key for item in ids.items}
    created: set[ItemKey] = set()
    while True:
        ids.refresh()
        ids.apply(staging, shortcuts)
        waiting: dict[SourceItem, set[ItemKey]] = {}
        problems: list[str] = []
        for item in items:
            found, workspace = ids.references(item)
            if workspace:
                problems.append(
                    f"{label(item.key)} refers to the source workspace."
                )
            problems.extend(
                f"{label(item.key)} refers by ID to {label(key)}, which the "
                "target lacks and this run cannot create before it."
                for key in sorted(found)
                if key[0] != item_type or key not in sources
            )
            if found:
                waiting[item] = found
        if problems:
            print("\n".join(problems))
            return False
        if not waiting:
            run = {**arguments, "item_types": [item_type]}
            result = operation(workspace_id, str(staging), **run)
            return report(result, item_type)
        # Each wave creates at least one item, so the waves come to an end.
        first = [
            item
            for item in items
            if item not in waiting
            and item.key not in ids.target_items
            and item.key not in created
        ]
        if not first:
            print(
                "\n".join(
                    f"{label(item.key)} waits for "
                    + ", ".join(map(label, sorted(keys)))
                    for item, keys in waiting.items()
                )
            )
            return False
        created |= {item.key for item in first}
        folder = staging.parent / f"{item_type}-{len(created)}"
        root = subset(staging, first, folder)
        names = ", ".join(label(item.key) for item in first)
        run = {"start_path": str(root), "item_types": [item_type]}
        result = operation(workspace_id, str(root), **run)
        if not report(result, f"{item_type}, first {names}"):
            return False


def active_value_set(endpoint: str) -> str | None:
    """The active value set of a variable library, or None."""
    result = pf.api_request(endpoint, return_result=True)
    if not result.success:
        return None
    properties = (result.data or {}).get("properties") or {}
    value = properties.get("activeValueSetName")
    return str(value) if value else None


def value_set_in_place(
    workspace_id: str,
    items: Sequence[SourceItem],
    value_set: str,
    *,
    change: bool,
) -> bool:
    """
    Whether each variable library has the value set active.

    The active value set is no part of the definition, so a deployment does
    not set it. With ``change``, it is made active where it is not.
    """
    libraries = list_workspace(workspace_id)
    ok = True
    for item in items:
        if item.item_type != "VariableLibrary":
            continue
        names = {
            json.loads(file.read_text(encoding="utf-8-sig")).get("name")
            for file in (item.folder / "valueSets").glob("*.json")
        }
        library = libraries.get(item.key)
        if value_set not in names or library is None:
            print(f"{label(item.key)}: no value set {value_set}, or missing.")
            ok = False
            continue
        endpoint = (
            f"/workspaces/{workspace_id}/variableLibraries/{library['id']}"
        )
        active = active_value_set(endpoint)
        if active != value_set and change:
            pf.api_request(
                endpoint,
                method="patch",
                payload={"properties": {"activeValueSetName": value_set}},
                return_result=True,
            )
            active = active_value_set(endpoint)
        print(f"{label(item.key)}: the active value set is {active}.")
        ok = ok and active == value_set
    return ok


def state_backend(args: argparse.Namespace) -> Any:
    """The state in a lakehouse or a folder, when either is given."""
    if args.state_lakehouse:
        return pf.OneLakeStateBackend(
            args.state_workspace, args.state_lakehouse
        )
    if args.state_dir:
        return pf.LocalJsonStateBackend(str(args.state_dir))
    return None


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Read the command line."""
    parser = argparse.ArgumentParser(
        description="Deploy the Fabric items of a Git repository to a "
        "workspace."
    )
    parser.add_argument(
        "--source-workspace",
        required=True,
        help="The workspace connected to the repository, by name or ID, "
        "whose IDs the items hold.",
    )
    parser.add_argument(
        "--workspace",
        required=True,
        help="The workspace to deploy to, by name or ID.",
    )
    parser.add_argument(
        "--value-set",
        help="The value set of the target workspace, made active in the "
        "variable libraries. Needed when the repository has any.",
    )
    parser.add_argument(
        "--environment",
        help="The name the deployment state is kept under. Default: the "
        "workspace to deploy to, as given.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=SOURCE,
        help="The folder of the items, in the repository. Default: the "
        "fabric-workspace folder next to this script",
    )
    parser.add_argument(
        "--state-workspace",
        help="The workspace, by name or ID, of the lakehouse of the state.",
    )
    parser.add_argument(
        "--state-lakehouse",
        help="The lakehouse, by name or ID, that keeps the state.",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        help="The folder of the state, without a lakehouse.",
    )
    parser.add_argument(
        "--allow-deletions",
        action="store_true",
        help="Delete from the workspace the items deleted in Git.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--plan",
        action="store_true",
        help="Print the plan, and change nothing.",
    )
    mode.add_argument(
        "--reconcile",
        action="store_true",
        help="Report how the target stands against the repository, and "
        "change nothing.",
    )
    mode.add_argument(
        "--restore",
        action="store_true",
        help="Bring back what drifted in the target, and delete nothing.",
    )
    args = parser.parse_args(argv)
    if bool(args.state_workspace) != bool(args.state_lakehouse):
        parser.error("--state-workspace and --state-lakehouse go together")
    if args.state_lakehouse and args.state_dir:
        parser.error("--state-dir goes without --state-lakehouse")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    """Deploy, plan, reconcile or restore; 0 when all went well."""
    args = parse_args(argv)
    load_dotenv()
    pf.set_auth_provider("env")

    source = require_workspace(args.source_workspace)
    target = require_workspace(args.workspace)
    if source == target:
        raise SystemExit(
            "The workspace to deploy to is the one of the repository."
        )

    with tempfile.TemporaryDirectory(prefix="pyfabricops-") as staging_dir:
        staging = Path(
            pf.copy_to_staging(str(args.source), staging_dir=staging_dir)
        )
        items = read_items(staging)
        libraries = any(i.item_type == "VariableLibrary" for i in items)
        if libraries and not args.value_set:
            raise SystemExit(
                "The repository has variable libraries: give --value-set, "
                "the value set of the workspace to deploy to."
            )
        shortcuts = {
            file: file.read_text(encoding="utf-8-sig")
            for file in sorted(staging.glob(f"**/*.Lakehouse/{SHORTCUTS}"))
        }
        state: dict[str, Any] = {
            "start_path": str(staging),
            "state_backend": state_backend(args),
            "environment": args.environment or args.workspace,
        }
        ids = IdMap(source, target, items)
        ids.apply(staging, shortcuts)

        if args.reconcile:
            reconciliation = pf.reconcile_items(target, str(staging), **state)
            print(reconciliation.describe())
            in_place = not libraries or value_set_in_place(
                target, items, args.value_set, change=False
            )
            return 0 if reconciliation.ok and in_place else 1

        arguments = state
        operation: Operation = pf.restore_items
        if not args.restore:
            arguments = {
                **state,
                # The items in Git, which the staging copy came from.
                "repository_path": str(args.source),
                "allow_deletions": args.allow_deletions,
            }
            operation = pf.deploy_all_items
            print("== Plan")
            plan = pf.plan_all_items(target, str(staging), **arguments)
            print(plan.describe())
            for item in items:
                found, _ = ids.references(item)
                if found:
                    names = ", ".join(map(label, sorted(found)))
                    print(
                        f"{label(item.key)} refers to {names}, not there yet."
                    )
            if args.plan:
                return 0

        for item_type in ITEM_TYPES:
            if not run_type(
                item_type,
                operation,
                target,
                staging,
                arguments,
                ids,
                shortcuts,
            ):
                return 1
            if (
                item_type == "VariableLibrary"
                and libraries
                and not value_set_in_place(
                    target, items, args.value_set, change=True
                )
            ):
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
