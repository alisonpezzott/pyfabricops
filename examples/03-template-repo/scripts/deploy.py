"""
Deploy the items of a Git repository to a workspace, on a Fabric capacity or
not.

The items are in ``fabric-workspace``, and each environment is a workspace:
a push to develop deploys to DEV, and one to main to PRD, from Azure DevOps
(``azure-pipelines.yml``) or GitHub Actions (``.github/workflows``). Who
writes the repository tells what a run does:

- Power BI Desktop saves a Power BI Project, which holds no ID of a
  workspace. The repository is then the source of every environment, DEV
  included, each on a capacity or a Pro workspace, without one, and the
  environments may mix them, such as DEV on Pro and PRD on a capacity.
  Variable libraries, semantic models and reports go.
- Fabric Git integration writes the items of DEV, connected to
  ``fabric-workspace``. They hold the IDs of DEV, such as the default
  lakehouse of a notebook, the OneLake path of a Direct Lake model or the
  items of the same workspace in a pipeline: sent as they are, the items of
  PRD would read and write DEV. So no run deploys to DEV, and in a staging
  copy each ID of DEV becomes the ID of the same item, by type and name, in
  the workspace to deploy to, as Fabric lists both at every run. Every item
  type of pyfabricops goes. A shortcut to an item of the same workspace gets
  the logical ID of that item in the target, since Fabric looks it up among
  the items of the workspace.

The item types go one at a time, in the dependency order of pyfabricops and
pipelines last, so that an item refers by ID only to items already in the
target, and a report bound to a model by path is sent bound to its ID there.
Within a type, the items the others refer to are created first, such as a
lakehouse a shortcut points to. A run stops before it sends an item that
would still refer to DEV. A type that neither the repository nor the target
has is skipped: its run would do nothing, but still take the lock and record
the state.

Some items stop the run before anything is deployed: an item of a type
pyfabricops does not deploy; without DEV connected to Git, any item but a
variable library, a semantic model or a report, and a Direct Lake model,
whose source is a Fabric item by ID; for a Pro workspace, which holds
semantic models and reports only, any other item; and a model saved as
model.bim, whose parameters the script does not read.

Each environment is a JSON file of ``environments``, named after it
(--environment PRD reads ``environments/PRD.json``), which gives its
workspace, the value set of its variable libraries and the parameters of
each semantic model there::

    {
      "workspace": "<workspace>",
      "valueSet": "<value set>",
      "parameters": {
        "Main": {"Server": "<server>.database.windows.net", "Database": "<db>"}
      }
    }

The file of the environment connected to Git gives ``"gitConnected": true``
and its workspace only; one environment at most is. So what tells the
environments apart is in Git, reviewed like the items, and the pipelines
only pick the environment of their branch. --workspace overrides the
workspace of the file, for a local run.

A variable library is sent as it is: its value sets hold what differs
between environments, for the items that read it. The value set of the
environment, which every library must have, is made active in each once it
is deployed, and read back: the active value set is no part of the
definition, so no deployment sets it. --reconcile checks it, and --restore
makes it active again. An environment without one keeps the default values:
a library starts on them, and the script leaves its active value set alone,
as the Fabric API documents no way back to them.

The repository keeps the parameter values DEV opens with. In the staging
copy, which leaves out what Git ignores, such as the data cache of Power BI
Desktop, and the diagram layout of each model, which the service does not
keep, the text parameters of each semantic model get the values the file of
the environment gives. A parameter it does not give keeps the value of the
repository, such as the database of DEV, and the run says which; a model or
a parameter the repository does not have stops the run, as a misspelled
name would leave that value unnoticed. The repository is never changed. A
model whose parameters in the workspace differ from those it is deployed
with is deployed again, even when Git did not change it.

A semantic model carries no credentials, and an import model arrives empty.
So each import model deployed, or never refreshed, or whose last refresh
failed, is taken over by the service principal, each of its SQL data
sources is bound to the shareable cloud connection of the same server and
database, and it is refreshed, without the options of an enhanced refresh: a
workspace without a capacity refuses them, and the plain refresh serves
both. A workspace without a capacity refreshes a model at most eight times a
day; --no-refresh only binds. A Direct Lake model is left alone: it reads
the tables of its source as they are loaded.

With a deployment state, on a branch of this repository (--state-branch),
in a lakehouse (--state-workspace and --state-lakehouse) or in a folder
(--state-dir), a run deploys only what changed in Git since the last
successful one, and holds a lock, so that two runs never deploy at a time.

Instead of deploying, --plan prints the plan; --reconcile reports how the
target stands against the repository, its parameters and active value sets
included, and changes nothing; --restore brings back what drifted there,
makes the value set active again, binds and refreshes the models it
restored, and deletes nothing.

Usage::

    python deploy.py --environment <env> [--plan | --reconcile | --restore]
    python deploy.py --environment <env> --state-branch pyfabricops/state
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# pyfabricops ships no py.typed marker, so mypy cannot read its types.
import pyfabricops as pf  # type: ignore[import-untyped]

ItemKey = tuple[str, str]
# The parameters of each semantic model, by model and parameter name.
Parameters = dict[str, dict[str, str]]
# deploy_all_items or restore_items: what a run does to the items of a type.
Operation = Callable[..., Any]

# The root of the repository, one folder above this script.
ROOT = Path(__file__).resolve().parents[1]
# The items of the repository: a Power BI Project, or the Git folder of DEV.
SOURCE = ROOT / "fabric-workspace"
# The JSON file of each environment: its workspace, value set and parameters.
ENVIRONMENTS = ROOT / "environments"
# What the script deploys, in the dependency order of pyfabricops. A pipeline
# refers to what it runs by ID, so pipelines go last.
ITEM_TYPES = [t for t in pf.DEPLOY_ORDER if t != "DataPipeline"] + [
    "DataPipeline"
]
# What goes without DEV connected to Git: as Power BI Desktop saves them, or
# as the values of a variable library, they hold no ID of a workspace.
WITHOUT_GIT = ("VariableLibrary", "SemanticModel", "Report")
# What a workspace holds without a capacity, as a Pro workspace.
ANY_WORKSPACE = ("SemanticModel", "Report")
# What a deployment did to an item that sent its definition.
SENT = ("created", "updated")
# The refresh statuses that need no new refresh: done, or still running.
REFRESHED = ("Completed", "Unknown")
# How long a refresh may take, and how often it is checked, in seconds.
REFRESH_TIMEOUT = 3600
REFRESH_POLL = 15
# What Power BI Desktop saves of a semantic model but the service does not
# keep, so that no reconciliation would ever find it in sync.
UNKEPT = ("diagramLayout.json",)
# An expression of expressions.tmdl starts a line.
EXPRESSION = re.compile(
    r"^expression\s+('(?:[^']|'')+'|[^\s=]+)", re.MULTILINE
)
PARAMETER = re.compile(
    r"meta\s*\[\s*IsParameterQuery\s*=\s*true", re.IGNORECASE
)
# The quoted value of a text parameter, right before its meta record.
TEXT_VALUE = re.compile(
    r'"((?:[^"]|"")*)"(?=\s*meta\s*\[\s*IsParameterQuery\s*=\s*true)',
    re.IGNORECASE,
)
# A partition in Direct Lake, in the file of its table.
DIRECT_LAKE = re.compile(
    r"^\s*mode:\s*directLake\b", re.MULTILINE | re.IGNORECASE
)
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
    """An item as Desktop and Git integration name its folder."""
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


def models(items: Sequence[SourceItem]) -> list[SourceItem]:
    """The semantic models among the items."""
    return [item for item in items if item.item_type == "SemanticModel"]


def libraries(items: Sequence[SourceItem]) -> list[SourceItem]:
    """The variable libraries among the items."""
    return [item for item in items if item.item_type == "VariableLibrary"]


def value_sets(library: SourceItem) -> set[str]:
    """The value sets of a variable library, by name, but the default."""
    return {
        str(json.loads(file.read_text(encoding="utf-8-sig")).get("name"))
        for file in sorted((library.folder / "valueSets").glob("*.json"))
    }


def direct_lake(model: SourceItem) -> bool:
    """Whether a semantic model has a table in Direct Lake."""
    return any(
        DIRECT_LAKE.search(table.read_text(encoding="utf-8-sig"))
        for table in sorted(model.folder.glob("definition/tables/*.tmdl"))
    )


def unsupported(items: Sequence[SourceItem], *, translated: bool) -> list[str]:
    """
    What among the staged items the script cannot deploy as it should.

    An item of a type it does not deploy, and a model saved as model.bim,
    whose parameters would keep the values of DEV. Unless the IDs of DEV are
    translated, also any item but a variable library, a semantic model or a
    report, and a Direct Lake model, which would still refer to DEV.
    """
    problems: list[str] = []
    for item in items:
        if item.item_type not in ITEM_TYPES:
            problems.append(
                f"{label(item.key)}: deploy.py deploys no {item.item_type}."
            )
        elif not translated and item.item_type not in WITHOUT_GIT:
            problems.append(
                f"{label(item.key)}: deploy.py deploys a {item.item_type} "
                "only with an environment connected to Git, whose IDs it "
                "translates."
            )
    for model in models(items):
        if (model.folder / "model.bim").is_file():
            problems.append(
                f"{label(model.key)}: saved as model.bim; deploy.py reads "
                "the parameters of TMDL only."
            )
        if not translated and direct_lake(model):
            problems.append(
                f"{label(model.key)}: Direct Lake, whose source is a Fabric "
                "item by ID, which deploy.py translates only with an "
                "environment connected to Git."
            )
    return problems


def require_workspace(name: str) -> str:
    """The ID of a workspace; exits when the principal cannot see it."""
    workspace_id = pf.resolve_workspace(name)
    if workspace_id is None:
        raise SystemExit(
            f"Workspace {name} not found, or the service principal has no "
            "access to it."
        )
    return str(workspace_id)


def without_capacity(
    workspace_id: str, items: Sequence[SourceItem]
) -> list[str]:
    """
    The items a workspace cannot hold, when it has no capacity.

    A Pro workspace holds semantic models and reports only. The workspace
    is read only when an item needs a capacity.
    """
    needing = [
        item
        for item in items
        if item.item_type in ITEM_TYPES and item.item_type not in ANY_WORKSPACE
    ]
    if not needing:
        return []
    workspace = pf.get_workspace(workspace_id, df=False)
    if not isinstance(workspace, dict):
        raise SystemExit(f"Could not read workspace {workspace_id}.")
    if workspace.get("capacityId"):
        return []
    return [
        f"{label(item.key)}: a workspace without a capacity holds no "
        f"{item.item_type}."
        for item in needing
    ]


def list_workspace(workspace_id: str) -> dict[ItemKey, dict[str, Any]]:
    """The items of a workspace, by type and display name."""
    items = pf.list_items(workspace_id, df=False)
    if items is None:
        raise SystemExit(
            f"Could not list the items of workspace {workspace_id}."
        )
    return {(item["type"], item["displayName"]): item for item in items}


def power_bi(endpoint: str, **kwargs: Any) -> Any:
    """A call to the Power BI REST API, as an ApiResult."""
    return pf.api_request(
        endpoint, audience="powerbi", return_result=True, **kwargs
    )


class Expressions:
    """
    The text parameters of a semantic model, in its expressions.tmdl.

    A parameter is an expression whose value has the meta record
    ``IsParameterQuery = true``, inline or inside a ``let``, as Power BI
    Desktop writes either. A parameter whose value is not text, such as a
    date or a number, cannot be told by a JSON string, so it stops the run.

    Args:
        model (SourceItem): The staged semantic model.
    """

    def __init__(self, model: SourceItem) -> None:
        self.model = model
        self.path = model.folder / "definition" / "expressions.tmdl"
        # Read and written as bytes, so that the line endings stay.
        self.text = (
            self.path.read_bytes().decode("utf-8-sig")
            if self.path.exists()
            else ""
        )

    def blocks(self) -> list[tuple[str, int, int]]:
        """Each expression: its name, start and end in the text."""
        starts = list(EXPRESSION.finditer(self.text))
        ends = [match.start() for match in starts[1:]] + [len(self.text)]
        return [
            (match.group(1).strip("'").replace("''", "'"), match.start(), end)
            for match, end in zip(starts, ends, strict=True)
        ]

    def values(self) -> dict[str, str]:
        """The value of each parameter, by name."""
        found: dict[str, str] = {}
        for name, start, end in self.blocks():
            block = self.text[start:end]
            if not PARAMETER.search(block):
                continue
            value = TEXT_VALUE.search(block)
            if value is None:
                raise SystemExit(
                    f"{label(self.model.key)}: parameter {name} is not text, "
                    "which --parameters cannot set."
                )
            found[name] = value.group(1).replace('""', '"')
        return found

    def set(self, values: Mapping[str, str]) -> None:
        """Give the parameters these values, and write the file."""
        parts: list[str] = []
        last = 0
        for name, start, end in self.blocks():
            value = TEXT_VALUE.search(self.text, start, end)
            if name not in values or value is None:
                continue
            parts += [
                self.text[last : value.start(1)],
                values[name].replace('"', '""'),
            ]
            last = value.end(1)
        self.text = "".join(parts) + self.text[last:]
        self.path.write_bytes(self.text.encode("utf-8"))


@dataclass(frozen=True)
class Environment:
    """An environment, as its file in ``environments`` describes it."""

    name: str
    file: Path
    workspace: str
    # Whether its workspace is connected to Git, whose IDs the items hold.
    git_connected: bool
    # The value set made active in each variable library, if any.
    value_set: str | None
    # The parameter values of each semantic model, as the file gives them.
    parameters: Mapping[str, Any]


def read_environment(name: str) -> Environment:
    """The environment of a name; exits when its file is missing or wrong."""
    file = ENVIRONMENTS / f"{name}.json"
    if not file.is_file():
        known = ", ".join(sorted(p.stem for p in ENVIRONMENTS.glob("*.json")))
        raise SystemExit(
            f"No environment {name}: {file} is missing. Known: {known}."
        )
    content = json.loads(file.read_text(encoding="utf-8-sig"))
    workspace = content.get("workspace")
    git_connected = content.get("gitConnected", False)
    value_set = content.get("valueSet")
    parameters = content.get("parameters", {})
    keys = {"workspace", "gitConnected", "valueSet", "parameters"}
    problems = [
        f"{file.name}: unknown key {key}."
        for key in sorted(set(content) - keys)
    ]
    if not isinstance(workspace, str) or not workspace:
        problems.append(f"{file.name}: no workspace.")
    if not isinstance(git_connected, bool):
        problems.append(f"{file.name}: gitConnected is not true or false.")
    elif git_connected:
        problems += [
            f"{file.name}: {key}, but it is connected to Git, and no run "
            "deploys to it."
            for key in ("valueSet", "parameters")
            if key in content
        ]
    if value_set is not None and (
        not isinstance(value_set, str) or not value_set
    ):
        problems.append(f"{file.name}: valueSet is not a name.")
    if not isinstance(parameters, dict):
        problems.append(f"{file.name}: parameters is not an object.")
    if problems:
        raise SystemExit("\n".join(problems))
    return Environment(
        name, file, str(workspace), git_connected, value_set, parameters
    )


def git_environment() -> Environment | None:
    """The environment connected to Git, whose IDs the items hold, if any."""
    connected = [
        environment
        for environment in (
            read_environment(path.stem)
            for path in sorted(ENVIRONMENTS.glob("*.json"))
        )
        if environment.git_connected
    ]
    if len(connected) > 1:
        names = ", ".join(environment.name for environment in connected)
        raise SystemExit(
            f"One environment at most is connected to Git, not {names}."
        )
    return connected[0] if connected else None


def read_parameters(
    environment: Environment, items: Sequence[SourceItem]
) -> Parameters:
    """
    The parameters the file of the environment gives each semantic model.

    A parameter it does not give keeps the value of the repository, the one
    DEV opens with. A model or a parameter the repository does not have
    stops the run, as a misspelled name would leave that value unnoticed.
    """
    file = environment.file
    given = environment.parameters
    names = {model.name for model in models(items)}
    problems = [
        f"{file.name}: no semantic model {name} in the repository."
        for name in sorted(set(given) - names)
    ]
    parameters: Parameters = {}
    for model in models(items):
        defined = set(Expressions(model).values())
        values = {str(k): str(v) for k, v in given.get(model.name, {}).items()}
        problems += [
            f"{file.name}: {label(model.key)} has no parameter {name}."
            for name in sorted(set(values) - defined)
        ]
        parameters[model.name] = values
    if problems:
        raise SystemExit("\n".join(problems))
    return parameters


def read_value_set(
    environment: Environment, items: Sequence[SourceItem]
) -> str | None:
    """
    The value set to make active in each variable library, or None.

    It must be one of every library of the repository, which is checked
    before anything is deployed. An environment without one keeps the
    default values; a repository without a library takes none.
    """
    file = environment.file
    value_set = environment.value_set
    if value_set is None:
        return None
    found = libraries(items)
    if not found:
        raise SystemExit(
            f"{file.name}: valueSet {value_set}, but the repository has no "
            "variable library."
        )
    problems = [
        f"{file.name}: {label(library.key)} has no value set {value_set}."
        for library in found
        if value_set not in value_sets(library)
    ]
    if problems:
        raise SystemExit("\n".join(problems))
    return value_set


def apply_parameters(
    items: Sequence[SourceItem], parameters: Parameters
) -> Parameters:
    """
    Put the values the file gives in the staged models.

    Returns:
        Parameters: The value each parameter of each model is deployed with:
            the one of the file, or else the one of the repository.
    """
    deployed: Parameters = {}
    for model in models(items):
        given = parameters[model.name]
        expressions = Expressions(model)
        expressions.set(given)
        values = expressions.values()
        if any(values[name] != value for name, value in given.items()):
            raise SystemExit(
                f"{label(model.key)}: its parameters did not take the values "
                "given."
            )
        kept = sorted(set(values) - set(given))
        if kept:
            print(
                f"{label(model.key)} keeps the values of the repository for "
                f"{', '.join(kept)}."
            )
        deployed[model.name] = values
    return deployed


def stale_models(
    workspace_id: str, items: Sequence[SourceItem], parameters: Parameters
) -> list[SourceItem]:
    """The models of the workspace whose parameters differ from those given."""
    target = list_workspace(workspace_id)
    stale: list[SourceItem] = []
    for model in models(items):
        existing = target.get(model.key)
        if existing is None:
            continue
        result = power_bi(
            f"/groups/{workspace_id}/datasets/{existing['id']}/parameters"
        )
        if not result.success:
            raise SystemExit(
                f"{label(model.key)}: could not read its parameters: "
                f"{result.error}"
            )
        current = {
            str(p["name"]): str(p.get("currentValue"))
            for p in (result.data or {}).get("value", [])
        }
        if any(current.get(k) != v for k, v in parameters[model.name].items()):
            stale.append(model)
    return stale


def drop_local_files(
    source: Path, staging: Path, items: Sequence[SourceItem]
) -> None:
    """
    Remove from the staging folder what is no part of the definitions.

    That is what Git ignores, such as the data cache and the local settings
    Power BI Desktop leaves in .pbi, which a run from a working copy would
    send otherwise, and what the service does not keep of a model.
    """
    ignored = subprocess.run(
        ["git", "ls-files", "--others", "--ignored", "--exclude-standard"]
        + ["-z", "--", "."],
        cwd=source,
        capture_output=True,
        text=True,
        check=True,
    )
    for path in filter(None, ignored.stdout.split("\0")):
        (staging / path).unlink(missing_ok=True)
    for model in models(items):
        for name in UNKEPT:
            (model.folder / name).unlink(missing_ok=True)


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
    ids: IdMap | None,
    shortcuts: Mapping[Path, str],
) -> list[Any] | None:
    """
    Deploy or restore the items of a type: what was done to each, or None
    when an item failed.

    With the IDs of DEV to translate, the items the others refer to by ID
    are created first, in runs of their own and without the state, which
    the run of the whole type reads and, for a deployment, records.
    """
    run = {**arguments, "item_types": [item_type]}
    if ids is None:
        result = operation(workspace_id, str(staging), **run)
        return list(result.results) if report(result, item_type) else None
    items = [item for item in ids.items if item.item_type == item_type]
    sources = {item.key for item in ids.items}
    created: set[ItemKey] = set()
    done: list[Any] = []
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
            return None
        if not waiting:
            result = operation(workspace_id, str(staging), **run)
            if not report(result, item_type):
                return None
            return done + list(result.results)
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
            return None
        created |= {item.key for item in first}
        folder = staging.parent / f"{item_type}-{len(created)}"
        root = subset(staging, first, folder)
        names = ", ".join(label(item.key) for item in first)
        wave = {"start_path": str(root), "item_types": [item_type]}
        result = operation(workspace_id, str(root), **wave)
        if not report(result, f"{item_type}, first {names}"):
            return None
        done += result.results


def cloud_connections() -> dict[str, dict[str, Any]]:
    """
    The shareable cloud SQL connections the service principal may use, by
    their ``server;database`` path in lowercase.
    """
    connections = pf.list_connections(df=False)
    if connections is None:
        raise SystemExit("Could not list the connections.")
    found: dict[str, dict[str, Any]] = {}
    for connection in connections:
        details = connection.get("connectionDetails") or {}
        if (
            connection.get("connectivityType") == "ShareableCloud"
            and details.get("type") == "SQL"
        ):
            found[str(details.get("path", "")).lower()] = connection
    return found


def latest_refresh(endpoint: str) -> dict[str, Any] | None:
    """The last refresh of a semantic model, or None."""
    result = power_bi(f"{endpoint}/refreshes", params={"$top": 1})
    history = (result.data or {}).get("value", []) if result.success else []
    return dict(history[0]) if history else None


def wait_refresh(endpoint: str, before: str | None) -> dict[str, Any] | None:
    """The first refresh other than ``before`` to end, or None on timeout."""
    deadline = time.monotonic() + REFRESH_TIMEOUT
    while time.monotonic() < deadline:
        time.sleep(REFRESH_POLL)
        latest = latest_refresh(endpoint)
        if (
            latest is not None
            and latest.get("requestId") != before
            and latest.get("status") != "Unknown"
        ):
            return latest
    return None


def refresh(endpoint: str, name: str) -> bool:
    """Refresh a semantic model and wait for it; True when it completed."""
    latest = latest_refresh(endpoint)
    if latest is not None and latest.get("status") == "Unknown":
        print(f"{name}: a refresh is running; waiting for it first.")
        latest = wait_refresh(endpoint, None)
    before = latest.get("requestId") if latest else None
    # A workspace without a capacity takes no option of an enhanced refresh,
    # and the plain refresh serves any workspace.
    started = power_bi(
        f"{endpoint}/refreshes",
        method="post",
        payload={"notifyOption": "NoNotification"},
    )
    if not started.success:
        print(f"{name}: the refresh did not start: {started.error}")
        return False
    ended = wait_refresh(endpoint, before)
    if ended is None:
        print(f"{name}: the refresh did not end in {REFRESH_TIMEOUT} s.")
        return False
    status = ended.get("status")
    print(f"{name}: refresh {status}.")
    if status != "Completed":
        print(ended.get("serviceExceptionJson", ""))
    return status == "Completed"


def prepare_model(
    workspace_id: str,
    model_id: str,
    name: str,
    connections: Mapping[str, dict[str, Any]],
    *,
    refreshed: bool,
) -> bool:
    """
    Take a semantic model over, bind its data sources and refresh it.

    The service principal takes the model over, so that it can bind and
    refresh it, as a model published from Power BI Desktop is another's.
    Each SQL data source is bound to the shareable cloud connection of the
    same server and database; any other kind stops the model.
    """
    endpoint = f"/groups/{workspace_id}/datasets/{model_id}"
    taken = power_bi(f"{endpoint}/Default.TakeOver", method="post")
    if not taken.success:
        print(f"{name}: could not take it over: {taken.error}")
        return False
    sources = power_bi(f"{endpoint}/datasources")
    if not sources.success:
        print(f"{name}: could not read its data sources: {sources.error}")
        return False
    for source in (sources.data or {}).get("value", []):
        details = source.get("connectionDetails") or {}
        if source.get("datasourceType") != "Sql":
            print(
                f"{name}: a {source.get('datasourceType')} data source, which "
                "this script does not bind."
            )
            return False
        path = f"{details.get('server')};{details.get('database')}"
        connection = connections.get(path.lower())
        if connection is None:
            print(
                f"{name}: no shareable cloud connection to {path} that the "
                "service principal may use."
            )
            return False
        bound = pf.api_request(
            f"/workspaces/{workspace_id}/semanticModels/{model_id}"
            "/bindConnection",
            method="post",
            payload={
                "connectionBinding": {
                    "id": connection["id"],
                    "connectivityType": "ShareableCloud",
                    "connectionDetails": connection["connectionDetails"],
                }
            },
            return_result=True,
        )
        if not bound.success:
            print(f"{name}: could not bind {path}: {bound.error}")
            return False
        print(f"{name}: {path} bound to {connection['displayName']}.")
    return not refreshed or refresh(endpoint, name)


def prepare_models(
    workspace_id: str,
    items: Sequence[SourceItem],
    results: Sequence[Any],
    *,
    refreshed: bool,
) -> bool:
    """
    Bind and refresh the import models just deployed, and those never
    refreshed or whose last refresh failed, so that a run that stopped after
    deploying is finished by the next one.
    """
    target = list_workspace(workspace_id)
    sent = {(r.item_type, r.display_name) for r in results if r.action in SENT}
    connections: dict[str, dict[str, Any]] | None = None
    ok = True
    for model in models(items):
        existing = target.get(model.key)
        # A Direct Lake model is left alone: it reads the tables of its
        # source as they are loaded.
        if existing is None or direct_lake(model):
            continue
        if model.key not in sent:
            latest = latest_refresh(
                f"/groups/{workspace_id}/datasets/{existing['id']}"
            )
            if latest is not None and latest.get("status") in REFRESHED:
                continue
            print(
                f"{label(model.key)}: never refreshed, or its last refresh "
                "failed."
            )
        if connections is None:
            connections = cloud_connections()
        ok = (
            prepare_model(
                workspace_id,
                str(existing["id"]),
                label(model.key),
                connections,
                refreshed=refreshed,
            )
            and ok
        )
    return ok


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
    value_set: str | None,
    *,
    change: bool,
) -> bool:
    """
    Whether each variable library has the value set active.

    The active value set is no part of the definition, so a deployment does
    not set it. With ``change``, it is made active where it is not, and read
    back. Without a value set, the environment keeps the default values, and
    there is nothing to check.
    """
    if value_set is None:
        return True
    target = list_workspace(workspace_id)
    ok = True
    for library in libraries(items):
        existing = target.get(library.key)
        if existing is None:
            print(f"{label(library.key)}: not in the workspace.")
            ok = False
            continue
        endpoint = (
            f"/workspaces/{workspace_id}/variableLibraries/{existing['id']}"
        )
        active = active_value_set(endpoint)
        if active != value_set and change:
            changed = pf.api_request(
                endpoint,
                method="patch",
                payload={"properties": {"activeValueSetName": value_set}},
                return_result=True,
            )
            if not changed.success:
                print(
                    f"{label(library.key)}: could not make {value_set} "
                    f"active: {changed.error}"
                )
            active = active_value_set(endpoint)
        print(f"{label(library.key)}: the active value set is {active}.")
        ok = ok and active == value_set
    return ok


def state_backend(args: argparse.Namespace) -> Any:
    """The state on a branch, in a lakehouse or in a folder, if one is given."""
    if args.state_branch:
        # The repository of the items, whose remote keeps the branch.
        return pf.GitStateBackend(str(args.source), args.state_branch)
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
        description="Deploy the items of a Git repository to a workspace, on "
        "a Fabric capacity or not."
    )
    parser.add_argument(
        "--environment",
        required=True,
        help="The environment to deploy to, such as PRD: the file of the "
        "environments folder of that name gives its workspace, value set and "
        "parameters, and the deployment state is kept under it.",
    )
    parser.add_argument(
        "--workspace",
        help="The workspace to deploy to, by name or ID, instead of the one "
        "of the environment.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=SOURCE,
        help="The folder of the items, in the repository. Default: the "
        "fabric-workspace folder next to this script",
    )
    parser.add_argument(
        "--state-branch",
        help="The branch of this repository that keeps the state, such as "
        "pyfabricops/state. The first deployment creates it; each run "
        "pushes to it.",
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
        help="The folder of the state, for a local run.",
    )
    parser.add_argument(
        "--allow-deletions",
        action="store_true",
        help="Delete from the workspace the items deleted in Git.",
    )
    parser.add_argument(
        "--no-refresh",
        dest="refresh",
        action="store_false",
        help="Bind the semantic models, but do not refresh them.",
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
    stores = (args.state_branch, args.state_lakehouse, args.state_dir)
    if sum(bool(store) for store in stores) > 1:
        parser.error(
            "give one of --state-branch, --state-lakehouse or --state-dir"
        )
    return args


def main(argv: Sequence[str] | None = None) -> int:
    """Deploy, plan, reconcile or restore; 0 when all went well."""
    args = parse_args(argv)
    load_dotenv()
    pf.set_auth_provider("env")
    environment = read_environment(args.environment)
    if environment.git_connected:
        print(
            f"{environment.name} is connected to Git: it writes the "
            "repository, and no run deploys to it."
        )
        return 0
    connected = git_environment()
    target = require_workspace(args.workspace or environment.workspace)
    source: str | None = None
    if connected is not None:
        source = require_workspace(connected.workspace)
        if source == target:
            raise SystemExit(
                f"The workspace to deploy to is that of {connected.name}, "
                "which is connected to Git."
            )

    with tempfile.TemporaryDirectory(prefix="pyfabricops-") as staging_dir:
        staging = Path(
            pf.copy_to_staging(str(args.source), staging_dir=staging_dir)
        )
        items = read_items(staging)
        drop_local_files(args.source, staging, items)
        problems = unsupported(items, translated=source is not None)
        problems += without_capacity(target, items)
        if problems:
            raise SystemExit("\n".join(problems))
        given = read_parameters(environment, items)
        value_set = read_value_set(environment, items)
        # Those of the file, and of the repository for the others.
        parameters = apply_parameters(items, given)
        shortcuts = {
            file: file.read_text(encoding="utf-8-sig")
            for file in sorted(staging.glob(f"**/*.Lakehouse/{SHORTCUTS}"))
        }
        ids = None if source is None else IdMap(source, target, items)
        if ids is not None:
            ids.apply(staging, shortcuts)
        # The types a run manages: those that hold no ID of a workspace,
        # unless the IDs of DEV are translated.
        managed = [
            t for t in ITEM_TYPES if ids is not None or t in WITHOUT_GIT
        ]
        state: dict[str, Any] = {
            "start_path": str(staging),
            "state_backend": state_backend(args),
            "environment": environment.name,
        }

        if args.reconcile:
            reconciliation = pf.reconcile_items(
                target, str(staging), item_types=managed, **state
            )
            print(reconciliation.describe())
            stale = stale_models(target, items, parameters)
            for model in stale:
                print(
                    f"{label(model.key)}: its parameters differ from "
                    f"{environment.file.name} and the repository."
                )
            in_place = value_set_in_place(
                target, items, value_set, change=False
            )
            return 0 if reconciliation.ok and not stale and in_place else 1

        arguments = state
        operation: Operation = pf.restore_items
        stale = []
        if not args.restore:
            arguments = {
                **state,
                # The items in Git, which the staging copy came from.
                "repository_path": str(args.source),
                "allow_deletions": args.allow_deletions,
            }
            operation = pf.deploy_all_items
            print("== Plan")
            plan = pf.plan_all_items(
                target, str(staging), item_types=managed, **arguments
            )
            print(plan.describe())
            for item in items:
                found = ids.references(item)[0] if ids is not None else set()
                if found:
                    names = ", ".join(map(label, sorted(found)))
                    print(
                        f"{label(item.key)} refers to {names}, not there yet."
                    )
            # Git did not change these, so the plan leaves them out.
            stale = stale_models(target, items, parameters)
            for model in stale:
                print(
                    f"{label(model.key)}: its parameters in the workspace "
                    f"differ from {environment.file.name} and the repository, "
                    "so it is deployed again."
                )
            if args.plan:
                return 0

        # A type the target has, but no longer the repository, still runs:
        # its run tells about the items deleted in Git.
        present = {item.item_type for item in items}
        present |= {item_type for item_type, _ in list_workspace(target)}
        results: list[Any] = []
        for item_type in [t for t in managed if t in present]:
            done = run_type(
                item_type,
                operation,
                target,
                staging,
                arguments,
                ids,
                shortcuts,
            )
            if done is None:
                return 1
            results += done
            if item_type == "VariableLibrary" and not value_set_in_place(
                target, items, value_set, change=True
            ):
                return 1
        sent = {
            (r.item_type, r.display_name) for r in results if r.action in SENT
        }
        again = [model for model in stale if model.key not in sent]
        if again:
            # A run of their own, without the state: Git did not change them.
            root = subset(staging, again, staging.parent / "parameters")
            redeployed = pf.deploy_all_items(
                target,
                str(root),
                start_path=str(root),
                item_types=["SemanticModel"],
            )
            if not report(redeployed, "SemanticModel, parameters"):
                return 1
            results += redeployed.results
        ready = prepare_models(target, items, results, refreshed=args.refresh)
        return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
