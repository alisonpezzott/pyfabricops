"""
Deploy the Power BI items of a Git repository to a workspace without a
Fabric capacity.

A Pro workspace has no Git integration, so no workspace writes the
repository: the items are the Power BI Project of ``fabric-workspace``, as
Power BI Desktop saves it, and the repository is the source of every
environment. A push to develop deploys to DEV, and one to main to PRD, from
Azure DevOps (``azure-pipelines.yml``) or GitHub Actions
(``.github/workflows``).

A Pro workspace holds only the items of Power BI, so a repository with any
other, such as a lakehouse or a notebook, stops the run. The semantic models
go first, so that a report bound to one by path is sent bound to its ID in
the workspace.

Each environment is a JSON file of ``environments``, named after it
(--environment DEV reads ``environments/DEV.json``), which gives its
workspace and the parameters of each semantic model there::

    {
      "workspace": "<workspace>",
      "parameters": {
        "Main": {"Server": "<server>.database.windows.net", "Database": "<db>"}
      }
    }

So what tells the environments apart is in Git, reviewed like the items,
and the pipelines only pick the environment of their branch. --workspace
overrides the workspace of the file, for a local run.

The repository keeps the parameter values Power BI Desktop opens with, those
of DEV. The items are copied to a staging folder, where the text parameters
of each semantic model get the values of the environment. The staging copy
leaves out what Git ignores, such as the data cache of Power BI Desktop, and
the diagram layout of each model, which the service does not keep. The
repository is never changed. The file must give every parameter of every
model, and no other. A model whose parameters in the workspace differ from
the file is deployed again, even when Git did not change it.

A semantic model carries no credentials, and an import model arrives empty.
So each model deployed, or never refreshed, or whose last refresh failed, is
taken over by the service principal, each of its SQL data sources is bound to
the shareable cloud connection of the same server and database, and it is
refreshed, without the options of an enhanced refresh, which a workspace
without a capacity refuses. Such a workspace refreshes a model at most eight
times a day; --no-refresh only binds.

With a deployment state, on a branch of this repository (--state-branch) or
in a folder (--state-dir), a run deploys only what changed in Git since the
last successful one, and holds a lock, so that two runs never deploy at a
time. A lakehouse cannot keep the state: a Pro workspace has none.

Instead of deploying, --plan prints the plan; --reconcile reports how the
target stands against the repository, its parameters included, and changes
nothing; --restore brings back what drifted there, binds and refreshes the
models it restored, and deletes nothing.

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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# pyfabricops ships no py.typed marker, so mypy cannot read its types.
import pyfabricops as pf  # type: ignore[import-untyped]

ItemKey = tuple[str, str]
# The parameters of each semantic model, by model and parameter name.
Parameters = dict[str, dict[str, str]]

# The Power BI Project of the repository, as Power BI Desktop saves it.
SOURCE = Path(__file__).resolve().parent / "fabric-workspace"
# The JSON file of each environment: its workspace and parameters.
ENVIRONMENTS = Path(__file__).resolve().parent / "environments"
# What a workspace without a capacity holds, in dependency order.
ITEM_TYPES = ["SemanticModel", "Report"]
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


def label(key: ItemKey) -> str:
    """An item as Power BI Desktop names its folder."""
    return f"{key[1]}.{key[0]}"


@dataclass(frozen=True)
class SourceItem:
    """An item of the repository, as its .platform describes it."""

    item_type: str
    name: str
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
                folder=platform.parent,
            )
        )
    return items


def models(items: Sequence[SourceItem]) -> list[SourceItem]:
    """The semantic models among the items."""
    return [item for item in items if item.item_type == "SemanticModel"]


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
    parameters = content.get("parameters", {})
    problems = [
        f"{file.name}: unknown key {key}."
        for key in sorted(set(content) - {"workspace", "parameters"})
    ]
    if not isinstance(workspace, str) or not workspace:
        problems.append(f"{file.name}: no workspace.")
    if not isinstance(parameters, dict):
        problems.append(f"{file.name}: parameters is not an object.")
    if problems:
        raise SystemExit("\n".join(problems))
    return Environment(name, file, str(workspace), parameters)


def read_parameters(
    environment: Environment, items: Sequence[SourceItem]
) -> Parameters:
    """
    The parameters of each semantic model for the workspace to deploy to.

    The file must give each parameter of each model of the repository, and
    nothing else, so that no model keeps a value of DEV by omission.
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
            f"{file.name}: no value for {name} of {label(model.key)}."
            for name in sorted(defined - set(values))
        ]
        problems += [
            f"{file.name}: {label(model.key)} has no parameter {name}."
            for name in sorted(set(values) - defined)
        ]
        parameters[model.name] = values
    if problems:
        raise SystemExit("\n".join(problems))
    return parameters


def apply_parameters(
    items: Sequence[SourceItem], parameters: Parameters
) -> None:
    """Put the values of the workspace to deploy to in the staged models."""
    for model in models(items):
        expressions = Expressions(model)
        expressions.set(parameters[model.name])
        if expressions.values() != parameters[model.name]:
            raise SystemExit(
                f"{label(model.key)}: its parameters did not take the values "
                "given."
            )


def stale_models(
    workspace_id: str, items: Sequence[SourceItem], parameters: Parameters
) -> list[SourceItem]:
    """The models of the workspace whose parameters differ from the file."""
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
    # A workspace without a capacity takes no option of an enhanced refresh.
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
    Bind and refresh the models just deployed, and those never refreshed or
    whose last refresh failed, so that a run that stopped after deploying is
    finished by the next one.
    """
    target = list_workspace(workspace_id)
    sent = {(r.item_type, r.display_name) for r in results if r.action in SENT}
    connections: dict[str, dict[str, Any]] | None = None
    ok = True
    for model in models(items):
        existing = target.get(model.key)
        if existing is None:
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


def state_backend(args: argparse.Namespace) -> Any:
    """The state on a branch or in a folder, if one is given."""
    if args.state_branch:
        # The repository of the items, whose remote keeps the branch.
        return pf.GitStateBackend(str(args.source), args.state_branch)
    if args.state_dir:
        return pf.LocalJsonStateBackend(str(args.state_dir))
    return None


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Read the command line."""
    parser = argparse.ArgumentParser(
        description="Deploy the Power BI items of a Git repository to a "
        "workspace without a Fabric capacity."
    )
    parser.add_argument(
        "--environment",
        required=True,
        help="The environment to deploy to, such as DEV: the file of the "
        "environments folder of that name gives its workspace and "
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
    store = parser.add_mutually_exclusive_group()
    store.add_argument(
        "--state-branch",
        help="The branch of this repository that keeps the state, such as "
        "pyfabricops/state. The first deployment creates it; each run "
        "pushes to it.",
    )
    store.add_argument(
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
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Deploy, plan, reconcile or restore; 0 when all went well."""
    args = parse_args(argv)
    load_dotenv()
    pf.set_auth_provider("env")
    environment = read_environment(args.environment)
    target = require_workspace(args.workspace or environment.workspace)

    with tempfile.TemporaryDirectory(prefix="pyfabricops-") as staging_dir:
        staging = Path(
            pf.copy_to_staging(str(args.source), staging_dir=staging_dir)
        )
        items = read_items(staging)
        drop_local_files(args.source, staging, items)
        others = sorted({item.item_type for item in items} - set(ITEM_TYPES))
        if others:
            raise SystemExit(
                "A workspace without a capacity holds no "
                + ", ".join(others)
                + "."
            )
        parameters = read_parameters(environment, items)
        apply_parameters(items, parameters)
        state: dict[str, Any] = {
            "start_path": str(staging),
            "state_backend": state_backend(args),
            "environment": environment.name,
            "item_types": ITEM_TYPES,
        }

        if args.reconcile:
            reconciliation = pf.reconcile_items(target, str(staging), **state)
            print(reconciliation.describe())
            stale = stale_models(target, items, parameters)
            for model in stale:
                print(
                    f"{label(model.key)}: its parameters differ from "
                    f"{environment.file.name}."
                )
            return 0 if reconciliation.ok and not stale else 1

        if args.restore:
            restored = pf.restore_items(target, str(staging), **state)
            if not report(restored, "Restore"):
                return 1
            ready = prepare_models(
                target, items, restored.results, refreshed=args.refresh
            )
            return 0 if ready else 1

        arguments = {
            **state,
            # The items in Git, which the staging copy came from.
            "repository_path": str(args.source),
            "allow_deletions": args.allow_deletions,
        }
        print("== Plan")
        plan = pf.plan_all_items(target, str(staging), **arguments)
        print(plan.describe())
        # Git did not change these, so the plan leaves them out.
        stale = stale_models(target, items, parameters)
        for model in stale:
            print(
                f"{label(model.key)}: its parameters in the workspace differ "
                f"from {environment.file.name}, so it is deployed again."
            )
        if args.plan:
            return 0

        deployed = pf.deploy_all_items(target, str(staging), **arguments)
        if not report(deployed, "Deploy"):
            return 1
        results = list(deployed.results)
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
