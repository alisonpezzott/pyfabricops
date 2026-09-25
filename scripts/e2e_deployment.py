"""
End-to-end check of the deployment engine against a real Fabric workspace.

Runs against a sandbox workspace the flow a deployment pipeline runs: a Git
repository of items, a staging copy with placeholders replaced, a local
deployment state, and ``plan_all_items`` before each ``deploy_all_items``.
Every step checks the plan and the report; at the end the script deletes
what it created.

Steps: bootstrap without a state; nothing changed; one notebook changed;
only the layout of a file changed (content hash); a notebook moved to a
folder, then back to the root, without sending its definition; a run
limited to notebooks, then a full one; a broken pipeline that fails and
leaves the state alone; a notebook deleted from Git (refused, then deleted
by hand); a notebook and its default lakehouse: the lakehouse created
first, then only checked when the notebook changes, and once deleted by
hand, the notebook blocked in a run limited to notebooks and the lakehouse
created again, before it, by the full run; a report and its semantic
model: the report, which points to the model by path in Git, reaches the
workspace bound to the model's ID, when both are created and when only the
report changes.

Prerequisites:

- A service principal in an ``.env`` file (``FAB_CLIENT_ID``,
  ``FAB_CLIENT_SECRET``, ``FAB_TENANT_ID``), in a tenant that lets service
  principals use Fabric APIs.
- A sandbox workspace on a Fabric capacity, with the service principal as
  Contributor or above, holding nothing but what this script creates.
  ``--create --capacity <name or ID>`` creates it, if the tenant lets
  service principals create workspaces.
- git on PATH.

Usage::

    uv run --frozen python scripts/e2e_deployment.py \\
        --workspace pyfabricops-e2e --env-file project/.env

It runs only with an explicit workspace (``--workspace`` or
``PYFABRICOPS_E2E_WORKSPACE``), so a CI job that has Fabric credentials
never starts it by accident. It clears the pyfabricops token cache first,
so a token cached for another service principal is never reused.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

import pyfabricops as pf

_ENVIRONMENT = "e2e"
_GREETING = "Hello from the pyfabricops e2e run"
_CREDENTIALS = ("FAB_CLIENT_ID", "FAB_CLIENT_SECRET", "FAB_TENANT_ID")
_PLATFORM_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/"
    "platformProperties/2.0.0/schema.json"
)
# The workspace ID Fabric writes for an item of the same workspace.
_SAME_WORKSPACE = "00000000-0000-0000-0000-000000000000"
# Items Fabric creates along with a lakehouse, and deletes with it.
_CHILD_TYPES = frozenset({"SQLEndpoint"})
# Fabric frees the name of a deleted item only minutes later.
_NAME_ATTEMPTS = 10
_NAME_WAIT_SECONDS = 30
_SCHEMAS = "https://developer.microsoft.com/json-schemas/fabric/item"
# A semantic model with its data inline, so it needs no data source.
_MODEL: dict[str, str] = {
    "definition.pbism": json.dumps(
        {
            "$schema": f"{_SCHEMAS}/semanticModel/definitionProperties/"
            "1.0.0/schema.json",
            "version": "4.2",
            "settings": {},
        },
        indent=2,
    ),
    "definition/database.tmdl": "database\n\tcompatibilityLevel: 1604\n",
    "definition/model.tmdl": (
        "model Model\n"
        "\tculture: en-US\n"
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
        "\tsourceQueryCulture: en-US\n"
        "\tdataAccessOptions\n"
        "\t\tlegacyRedirects\n"
        "\t\treturnErrorValuesAsNull\n"
    ),
    "definition/tables/Numbers.tmdl": (
        "table Numbers\n"
        "\n"
        "\tcolumn Value\n"
        "\t\tdataType: int64\n"
        "\t\tsummarizeBy: sum\n"
        "\t\tsourceColumn: Value\n"
        "\n"
        "\tpartition Numbers = m\n"
        "\t\tmode: import\n"
        "\t\tsource =\n"
        "\t\t\t\tlet\n"
        "\t\t\t\t    Source = #table(\n"
        "\t\t\t\t        type table [Value = Int64.Type], {{1}, {2}}\n"
        "\t\t\t\t    )\n"
        "\t\t\t\tin\n"
        "\t\t\t\t    Source\n"
    ),
}
_NOTEBOOK = """# Fabric notebook source

# METADATA ********************

__METADATA__

# CELL ********************

print("#{GREETING}# - notebook __LETTER__, version __VERSION__")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
"""


class E2EFailure(Exception):
    """The sandbox is not usable, or a step did not do what it should."""


@dataclass
class Run:
    """The sandbox workspace and the local repository the steps work on."""

    workspace: str
    workspace_id: str
    prefix: str
    root: Path

    @property
    def repository(self) -> Path:
        """The local Git repository."""
        return self.root / "repo"

    @property
    def items(self) -> Path:
        """The repository folder that holds the items."""
        return self.repository / "workspace"

    @property
    def state(self) -> pf.LocalJsonStateBackend:
        """The local deployment state, outside the repository."""
        return pf.LocalJsonStateBackend(self.root / "state")

    @property
    def folder(self) -> str:
        """The workspace folder the move step uses."""
        return f"{self.prefix}_folder"

    def name(self, letter: str) -> str:
        """The display name of an item of the run."""
        return f"{self.prefix}_{letter}"


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def _step_bootstrap(run: Run) -> None:
    for letter in "ABC":
        _write_notebook(run, letter, version=1)
    _write_pipeline(run, "P", wait_seconds=1)
    head = _commit(run, "Add the items")

    _deploy_step(
        run,
        "Bootstrap: no state yet, so every item is created",
        plan=[
            ("CREATE", "A"),
            ("CREATE", "B"),
            ("CREATE", "C"),
            ("CREATE", "P"),
        ],
        results=[
            ("A", "created"),
            ("B", "created"),
            ("C", "created"),
            ("P", "created"),
        ],
    )
    state = _state(run)
    _check(state.source_commit == head, "the state records HEAD")
    _check(len(state.items) == 4, "the state records the four items")


def _step_nothing_changed(run: Run) -> None:
    (run.repository / "README.md").write_text(
        "Not an item.\n", encoding="utf-8"
    )
    head = _commit(run, "Change a file outside the items")

    _deploy_step(run, "Nothing changed: nothing to do", plan=[], results=[])
    _check(_state(run).source_commit == head, "the state still moves to HEAD")


def _step_one_change(run: Run) -> None:
    _write_notebook(run, "A", version=2)
    _commit(run, "Change notebook A")

    _deploy_step(
        run,
        "One notebook changed: only it is updated",
        plan=[("UPDATE", "A")],
        results=[("A", "updated")],
    )


def _step_layout_only(run: Run) -> None:
    platform = run.items / f"{run.name('A')}.Notebook" / ".platform"
    content = json.loads(platform.read_text(encoding="utf-8"))
    platform.write_text(
        json.dumps(content, indent=4, sort_keys=True), encoding="utf-8"
    )
    _commit(run, "Reformat the .platform of notebook A")

    _deploy_step(
        run,
        "Only the layout of a file changed: nothing to do (content hash)",
        plan=[("NOOP", "A")],
        results=[],
    )


def _step_move(run: Run) -> None:
    name = f"{run.name('B')}.Notebook"
    (run.items / run.folder).mkdir()
    shutil.move(str(run.items / name), str(run.items / run.folder / name))
    _commit(run, "Move notebook B to a folder")

    report = _deploy_step(
        run,
        "A notebook moved to a folder: moved, not deleted or sent again",
        plan=[("MOVE", "B"), ("NOOP", "B")],
        results=[("B", "moved")],
    )
    _check(report.results[0].moved, "notebook B was moved")
    _check(
        _folder_of(run, "Notebook", run.name("B")) is not None,
        "notebook B is in a folder of the workspace",
    )


def _step_move_back(run: Run) -> None:
    name = f"{run.name('B')}.Notebook"
    shutil.move(str(run.items / run.folder / name), str(run.items / name))
    _commit(run, "Move notebook B back to the root")

    report = _deploy_step(
        run,
        "The notebook moved back to the root: moved there",
        plan=[("MOVE", "B"), ("NOOP", "B")],
        results=[("B", "moved")],
    )
    _check(report.results[0].moved, "notebook B was moved")
    _check(
        _folder_of(run, "Notebook", run.name("B")) is None,
        "notebook B is at the root of the workspace",
    )


def _step_partial_run(run: Run) -> None:
    pipeline_commit = _state(run).commits["DataPipeline"]
    _write_notebook(run, "A", version=3)
    _write_pipeline(run, "P", wait_seconds=2)
    head = _commit(run, "Change notebook A and pipeline P")

    _deploy_step(
        run,
        "Only notebooks: the pipeline waits for the next full run",
        plan=[("UPDATE", "A")],
        results=[("A", "updated")],
        item_types=["Notebook"],
    )
    commits = _state(run).commits
    _check(commits["Notebook"] == head, "notebooks are recorded at HEAD")
    _check(
        commits["DataPipeline"] == pipeline_commit,
        "pipelines stay at their last deployment",
    )

    _deploy_step(
        run,
        "The full run deploys the pipeline left behind",
        plan=[("UPDATE", "P")],
        results=[("P", "updated")],
    )
    _check(
        _state(run).commits["DataPipeline"] == head,
        "pipelines are recorded at HEAD",
    )


def _step_failure(run: Run) -> None:
    pipeline_commit = _state(run).commits["DataPipeline"]
    _write_pipeline(run, "P", wait_seconds=None)
    _commit(run, "Break pipeline P")

    _deploy_step(
        run,
        "A broken pipeline fails, and the state stays",
        plan=[("UPDATE", "P")],
        results=[("P", "failed")],
    )
    _check(
        _state(run).commits["DataPipeline"] == pipeline_commit,
        "the state did not move",
    )

    _write_pipeline(run, "P", wait_seconds=3)
    head = _commit(run, "Fix pipeline P")

    _deploy_step(
        run,
        "Fixed: compared from the last success, the pipeline goes",
        plan=[("UPDATE", "P")],
        results=[("P", "updated")],
    )
    _check(_state(run).source_commit == head, "the state moves to HEAD")


def _step_deletion(run: Run) -> None:
    before = _state(run).source_commit
    name = run.name("C")
    shutil.rmtree(run.items / f"{name}.Notebook")
    head = _commit(run, "Delete notebook C")

    _deploy_step(
        run,
        "A notebook deleted from Git: the deletion is refused",
        plan=[("DELETE", "C")],
        results=[("C", "failed")],
    )
    _check(_state(run).source_commit == before, "the state did not move")

    _delete_by_hand(run, "Notebook", name)
    _deploy_step(
        run,
        "Deleted by hand: nothing left to do",
        plan=[("NOOP", "C")],
        results=[],
    )
    state = _state(run)
    _check(state.source_commit == head, "the state moves to HEAD")
    _check(
        ("Notebook", name) not in state.items,
        "the state forgets notebook C",
    )


def _step_dependency(run: Run) -> None:
    _write_lakehouse(run, "L")
    _write_notebook(run, "N", version=1, lakehouse="L")
    _commit(run, "Add lakehouse L and notebook N, which uses it")

    _deploy_step(
        run,
        "A notebook and its default lakehouse: the lakehouse goes first",
        plan=[("CREATE", "L"), ("CREATE", "N")],
        results=[("L", "created"), ("N", "created")],
    )


def _step_dependency_in_place(run: Run) -> None:
    _write_notebook(run, "N", version=2, lakehouse="L")
    _commit(run, "Change notebook N")

    _deploy_step(
        run,
        "The notebook changed: its lakehouse is checked, not deployed",
        plan=[("NOOP", "L"), ("UPDATE", "N")],
        results=[("N", "updated")],
        required=["L"],
    )


def _step_dependency_missing(run: Run) -> None:
    before = _state(run).source_commit
    _write_notebook(run, "N", version=3, lakehouse="L")
    head = _commit(run, "Change notebook N again")
    _delete_by_hand(run, "Lakehouse", run.name("L"))

    report = _deploy_step(
        run,
        "Its lakehouse deleted by hand, and only notebooks: blocked",
        plan=[("BLOCKED", "N")],
        results=[("N", "failed")],
        item_types=["Notebook"],
    )
    _check(
        run.name("L") in (report.results[0].error or ""),
        "the notebook is blocked by its missing lakehouse",
    )
    _check(_state(run).source_commit == before, "the state did not move")

    _deploy_step(
        run,
        "The full run creates the lakehouse again, before the notebook",
        plan=[("CREATE", "L"), ("UPDATE", "N")],
        results=[("L", "created"), ("N", "updated")],
        required=["L"],
    )
    _check(_state(run).source_commit == head, "the state moves to HEAD")


def _step_report(run: Run) -> None:
    _write_model(run, "M")
    _write_report(run, "R", model="M", version=1)
    _commit(run, "Add semantic model M and report R, which reads it")

    _deploy_step(
        run,
        "A report and its semantic model: the report reads the model by ID",
        plan=[("CREATE", "M"), ("CREATE", "R")],
        results=[("M", "created"), ("R", "created")],
    )
    _check_bound(run, "R", model="M")


def _step_report_in_place(run: Run) -> None:
    _write_report(run, "R", model="M", version=2)
    _commit(run, "Change report R")

    _deploy_step(
        run,
        "The report changed: bound again to the model already there",
        plan=[("NOOP", "M"), ("UPDATE", "R")],
        results=[("R", "updated")],
        required=["M"],
    )
    _check_bound(run, "R", model="M")


_STEPS: tuple[Callable[[Run], None], ...] = (
    _step_bootstrap,
    _step_nothing_changed,
    _step_one_change,
    _step_layout_only,
    _step_move,
    _step_move_back,
    _step_partial_run,
    _step_failure,
    _step_deletion,
    _step_dependency,
    _step_dependency_in_place,
    _step_dependency_missing,
    _step_report,
    _step_report_in_place,
)


# ---------------------------------------------------------------------------
# Plan, deploy and check
# ---------------------------------------------------------------------------


def _deploy_step(
    run: Run,
    title: str,
    *,
    plan: list[tuple[str, str]],
    results: list[tuple[str, str]],
    item_types: list[str] | None = None,
    required: Sequence[str] = (),
) -> pf.DeploymentReport:
    """
    Plan, check the plan, deploy, check the report.

    ``required`` names the items the plan has only because another item
    needs them.
    """
    print(f"\n== {title}")
    staging = _stage(run)
    arguments: dict[str, Any] = {
        "start_path": staging,
        "item_types": item_types,
        "repository_path": str(run.items),
        "state_backend": run.state,
        "environment": _ENVIRONMENT,
    }

    planned = pf.plan_all_items(run.workspace, staging, **arguments)
    print(_indent(planned.describe()))
    _check(
        [(a.action.value, a.display_name) for a in planned.actions]
        == [(action, run.name(letter)) for action, letter in plan],
        "the plan is as expected",
    )
    if required:
        _check(
            [
                a.display_name
                for a in planned.actions
                if a.reason is pf.DeploymentReason.DEPENDENCY_REQUIRED
            ]
            == [run.name(letter) for letter in required],
            "the plan has what the items need",
        )

    report = _deploy(run, staging, arguments)
    for result in report.results:
        error = f": {result.error}" if result.error else ""
        print(f"    {result.display_name} {result.action}{error}")
    _check(
        [(r.display_name, r.action) for r in report.results]
        == [(run.name(letter), outcome) for letter, outcome in results],
        "the deployment did what the plan said",
    )
    return report


def _deploy(
    run: Run, staging: str, arguments: dict[str, Any]
) -> pf.DeploymentReport:
    """
    Deploy, and again while an item waits for Fabric to free its name.

    A run with a failed item records no state, so every attempt plans the
    same actions.
    """
    for _ in range(_NAME_ATTEMPTS - 1):
        report: pf.DeploymentReport = pf.deploy_all_items(
            run.workspace, staging, **arguments
        )
        waiting = [
            f"{r.display_name}.{r.item_type}"
            for r in report.failed
            if "ItemDisplayNameNotAvailableYet" in (r.error or "")
        ]
        if not waiting:
            return report
        print(
            f"    {', '.join(waiting)}: Fabric has not freed the name yet; "
            f"trying again in {_NAME_WAIT_SECONDS}s"
        )
        time.sleep(_NAME_WAIT_SECONDS)
    last: pf.DeploymentReport = pf.deploy_all_items(
        run.workspace, staging, **arguments
    )
    return last


def _check(condition: bool, what: str) -> None:
    """Print a passed check, or stop the run on a failed one."""
    if not condition:
        raise E2EFailure(what)
    print(f"  [ok] {what}")


def _state(run: Run) -> pf.DeploymentState:
    """The recorded deployment state, which must exist."""
    state = run.state.load(_ENVIRONMENT)
    if state is None:
        raise E2EFailure("no deployment state was recorded")
    return state


def _indent(text: str) -> str:
    return "\n".join(f"    {line}" for line in text.splitlines())


# ---------------------------------------------------------------------------
# The local repository
# ---------------------------------------------------------------------------


def _init_repository(run: Run) -> None:
    run.items.mkdir(parents=True)
    _git(run, "init", "--quiet")
    for key, value in (
        ("user.name", "pyfabricops e2e"),
        ("user.email", "e2e@example.com"),
        ("commit.gpgsign", "false"),
        ("core.autocrlf", "false"),
    ):
        _git(run, "config", key, value)


def _commit(run: Run, message: str) -> str:
    """Commit every change and return the commit ID."""
    _git(run, "add", "--all")
    _git(run, "commit", "--quiet", "--allow-empty", "--message", message)
    return _git(run, "rev-parse", "HEAD")


def _git(run: Run, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(run.repository), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _stage(run: Run) -> str:
    """Copy the items to staging and replace the placeholders there."""
    staging: str = pf.copy_to_staging(
        str(run.items), staging_dir=str(run.root / "stg")
    )
    pf.find_and_replace(staging, {(r".*\.py$", r"#\{GREETING\}#"): _GREETING})
    return staging


def _write_notebook(
    run: Run, letter: str, *, version: int, lakehouse: str | None = None
) -> None:
    """Write a notebook, with a default lakehouse of the run if given."""
    item = _item_folder(run, letter, "Notebook")
    dependencies: dict[str, Any] = {}
    if lakehouse is not None:
        # As Fabric writes a lakehouse of the same workspace: by logical ID.
        dependencies["lakehouse"] = {
            "default_lakehouse": _logical_id(run, lakehouse, "Lakehouse"),
            "default_lakehouse_name": run.name(lakehouse),
            "default_lakehouse_workspace_id": _SAME_WORKSPACE,
        }
    metadata = {
        "kernel_info": {"name": "synapse_pyspark"},
        "dependencies": dependencies,
    }
    meta = "\n".join(
        f"# META {line}"
        for line in json.dumps(metadata, indent=2).splitlines()
    )
    content = (
        _NOTEBOOK.replace("__METADATA__", meta)
        .replace("__LETTER__", letter)
        .replace("__VERSION__", str(version))
    )
    (item / "notebook-content.py").write_text(content, encoding="utf-8")


def _write_lakehouse(run: Run, letter: str) -> None:
    """Write a lakehouse without schemas, shortcuts or tables."""
    item = _item_folder(run, letter, "Lakehouse")
    (item / "lakehouse.metadata.json").write_text("{}\n", encoding="utf-8")


def _write_model(run: Run, letter: str) -> None:
    """Write a semantic model of one table, with its data inline."""
    item = _item_folder(run, letter, "SemanticModel")
    for relative, content in _MODEL.items():
        path = item / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _write_report(run: Run, letter: str, *, model: str, version: int) -> None:
    """Write a report of one empty page, on a model of the run, by path."""
    item = _item_folder(run, letter, "Report")
    files: dict[str, dict[str, Any]] = {
        "definition.pbir": {
            "$schema": f"{_SCHEMAS}/report/definitionProperties/2.0.0/"
            "schema.json",
            "version": "4.0",
            "datasetReference": {
                "byPath": {"path": f"../{run.name(model)}.SemanticModel"}
            },
        },
        "definition/version.json": {
            "$schema": f"{_SCHEMAS}/report/definition/versionMetadata/1.0.0/"
            "schema.json",
            "version": "2.0.0",
        },
        "definition/report.json": {
            "$schema": f"{_SCHEMAS}/report/definition/report/3.1.0/"
            "schema.json",
            "themeCollection": {},
        },
        "definition/pages/pages.json": {
            "$schema": f"{_SCHEMAS}/report/definition/pagesMetadata/1.0.0/"
            "schema.json",
            "pageOrder": ["main"],
            "activePageName": "main",
        },
        "definition/pages/main/page.json": {
            "$schema": f"{_SCHEMAS}/report/definition/page/2.0.0/schema.json",
            "name": "main",
            "displayName": f"Version {version}",
            "displayOption": "FitToPage",
            "height": 720,
            "width": 1280,
        },
    }
    for relative, content in files.items():
        path = item / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content, indent=2), encoding="utf-8")


def _check_bound(run: Run, letter: str, *, model: str) -> None:
    """Check the report reads its model by ID, while Git keeps the path."""
    report_id = _item_id(run, "Report", run.name(letter))
    # The response of getDefinition, as the API returns it.
    response = pf.get_item_definition(run.workspace_id, report_id) or {}
    pbirs = [
        json.loads(base64.b64decode(part["payload"]))
        for part in response.get("definition", {}).get("parts", [])
        if part["path"] == "definition.pbir"
    ]
    if not pbirs:
        raise E2EFailure(f"no definition.pbir read back for report {letter}")
    connection = str(
        pbirs[0]
        .get("datasetReference", {})
        .get("byConnection", {})
        .get("connectionString", "")
    )
    model_id = _item_id(run, "SemanticModel", run.name(model))
    _check(
        model_id.lower() in connection.lower(),
        "the report in the workspace reads the model by its ID",
    )
    local = _item_folder(run, letter, "Report") / "definition.pbir"
    _check(
        "byPath"
        in json.loads(local.read_text(encoding="utf-8"))["datasetReference"],
        "Git keeps the path to the model",
    )


def _write_pipeline(
    run: Run, letter: str, *, wait_seconds: int | None
) -> None:
    """Write a pipeline with one Wait activity, or broken JSON for None."""
    item = _item_folder(run, letter, "DataPipeline")
    if wait_seconds is None:
        content = "{not json"
    else:
        activity = {
            "name": "Wait",
            "type": "Wait",
            "dependsOn": [],
            "typeProperties": {"waitTimeInSeconds": wait_seconds},
        }
        content = json.dumps(
            {"properties": {"activities": [activity]}}, indent=2
        )
    (item / "pipeline-content.json").write_text(content, encoding="utf-8")


def _item_folder(run: Run, letter: str, item_type: str) -> Path:
    """The item folder, created with its .platform on first use."""
    name = run.name(letter)
    found = list(run.items.glob(f"**/{name}.{item_type}"))
    if found:
        return found[0]

    item = run.items / f"{name}.{item_type}"
    item.mkdir(parents=True)
    platform = {
        "$schema": _PLATFORM_SCHEMA,
        "metadata": {"type": item_type, "displayName": name},
        "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
    }
    (item / ".platform").write_text(
        json.dumps(platform, indent=2), encoding="utf-8"
    )
    return item


def _logical_id(run: Run, letter: str, item_type: str) -> str:
    """The logical ID in the .platform of an item of the run."""
    platform = _item_folder(run, letter, item_type) / ".platform"
    content = json.loads(platform.read_text(encoding="utf-8"))
    logical_id: str = content["config"]["logicalId"]
    return logical_id


# ---------------------------------------------------------------------------
# The sandbox workspace
# ---------------------------------------------------------------------------


def _authenticate(env_file: str) -> None:
    """Load the service principal and authenticate with it."""
    if Path(env_file).is_file():
        load_dotenv(env_file, override=True)
    missing = [name for name in _CREDENTIALS if not os.getenv(name)]
    if missing:
        raise E2EFailure(
            f"{', '.join(missing)} not set: put the service principal in "
            f"{env_file} or in the environment."
        )
    # The token cache is shared and keyed by audience only: a token cached
    # for another service principal, maybe of another tenant, would be used.
    pf.clear_token_cache()
    pf.set_auth_provider("env")


def _open_sandbox(args: argparse.Namespace) -> tuple[str, bool]:
    """
    Find (or create) the sandbox and make sure it holds nothing else.

    Returns:
        tuple[str, bool]: The workspace ID, and whether this run created it.
    """
    workspace_id = pf.resolve_workspace(args.workspace)
    created = False
    if workspace_id is None:
        if not args.create:
            raise E2EFailure(
                f"Workspace '{args.workspace}' not found. Create it on a "
                "Fabric capacity and add the service principal as "
                "Contributor, or pass --create --capacity <name or ID>."
            )
        response = pf.create_workspace(
            args.workspace, capacity=args.capacity, df=False
        )
        workspace_id = (
            response.get("id") if isinstance(response, dict) else None
        )
        if not workspace_id:
            raise E2EFailure(
                f"Could not create workspace '{args.workspace}'; see the log."
            )
        created = True
        print(f"Workspace '{args.workspace}' created.")

    others = [
        f"{item['displayName']}.{item['type']}"
        for item in _list_items(workspace_id)
        if not item["displayName"].startswith(f"{args.prefix}_")
    ]
    if others and not args.allow_non_empty:
        raise E2EFailure(
            f"Workspace '{args.workspace}' holds items this script did not "
            f"create ({', '.join(others[:5])}); use an empty sandbox, or "
            "pass --allow-non-empty."
        )
    return workspace_id, created


def _remove_what_the_run_created(run: Run) -> None:
    """Delete the run's items and folder from the workspace."""
    # What needs an item goes before it: a report before its model.
    rank = {item_type: n for n, item_type in enumerate(pf.DEPLOY_ORDER)}
    created = [
        item
        for item in _list_items(run.workspace_id)
        if item["displayName"].startswith(f"{run.prefix}_")
        and item["type"] not in _CHILD_TYPES
    ]
    for item in sorted(created, key=lambda i: -rank.get(i["type"], -1)):
        pf.delete_item(run.workspace_id, item["id"])
        print(f"Deleted {item['displayName']}.{item['type']}.")
    for folder in pf.list_folders(run.workspace_id, df=False) or []:
        if folder["displayName"] == run.folder:
            pf.delete_folder(run.workspace_id, folder["id"])
            print(f"Deleted folder {run.folder}.")


def _delete_by_hand(run: Run, item_type: str, name: str) -> None:
    """Delete an item as a person would, then wait until it is gone."""
    for item in _list_items(run.workspace_id):
        if (item["type"], item["displayName"]) == (item_type, name):
            pf.delete_item(run.workspace_id, item["id"])
    for _ in range(30):
        if not any(
            (item["type"], item["displayName"]) == (item_type, name)
            for item in _list_items(run.workspace_id)
        ):
            print(f"    {name}.{item_type} deleted by hand")
            return
        time.sleep(2)
    raise E2EFailure(f"{name}.{item_type} is still in the workspace")


def _list_items(workspace_id: str) -> list[dict[str, Any]]:
    items = pf.list_items(workspace_id, df=False)
    if items is None:
        raise E2EFailure("Could not list the workspace items.")
    return list(items)


def _item_id(run: Run, item_type: str, name: str) -> str:
    """The ID of an item of the workspace."""
    for item in _list_items(run.workspace_id):
        if (item["type"], item["displayName"]) == (item_type, name):
            item_id: str = item["id"]
            return item_id
    raise E2EFailure(f"{name}.{item_type} is not in the workspace")


def _folder_of(run: Run, item_type: str, name: str) -> str | None:
    """The ID of the workspace folder an item is in, or None at the root."""
    for item in _list_items(run.workspace_id):
        if (item["type"], item["displayName"]) == (item_type, name):
            folder_id: str | None = item.get("folderId")
            return folder_id
    raise E2EFailure(f"{name}.{item_type} is not in the workspace")


def _remove_tree(path: Path) -> None:
    """Remove a folder, including the read-only files git leaves."""

    def _retry(function: Callable[..., Any], target: str, _: Any) -> None:
        os.chmod(target, stat.S_IWRITE)
        function(target)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_retry)
    else:
        shutil.rmtree(path, onerror=_retry)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _prefix(value: str) -> str:
    """Accept a prefix that keeps every name of the run valid."""
    # Lakehouse names are the strictest: a letter, then letters, digits and
    # underscores.
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value):
        raise argparse.ArgumentTypeError(
            "use a letter, then letters, digits or underscores, as lakehouse "
            "names must"
        )
    return value


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check the deployment engine against a sandbox workspace."
    )
    parser.add_argument(
        "--workspace",
        default=os.getenv("PYFABRICOPS_E2E_WORKSPACE"),
        help="The sandbox workspace (or PYFABRICOPS_E2E_WORKSPACE).",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="The .env file with the service principal. Default: .env",
    )
    parser.add_argument(
        "--prefix",
        type=_prefix,
        default="pfo_e2e",
        help="Prefix of the items the run creates. Default: pfo_e2e",
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="Create the workspace when it does not exist (needs --capacity).",
    )
    parser.add_argument(
        "--capacity", help="The capacity, by name or ID, for --create."
    )
    parser.add_argument(
        "--delete-workspace",
        action="store_true",
        help="Delete the workspace at the end, if this run created it.",
    )
    parser.add_argument(
        "--allow-non-empty",
        action="store_true",
        help="Run even if the workspace holds other items (left untouched).",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep the items and the local repository for inspection.",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Show the library log."
    )
    args = parser.parse_args(argv)
    if args.create and not args.capacity:
        parser.error("--create needs --capacity")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    """
    Run every step against the sandbox, then clean up.

    Args:
        argv (Sequence[str] | None): The arguments, or None for the command
            line.

    Returns:
        int: 0 when every step passed, 1 when one failed, 2 without a
            workspace.
    """
    args = _parse_args(argv)
    if not args.workspace:
        print(
            "Pass --workspace or set PYFABRICOPS_E2E_WORKSPACE: this script "
            "creates and deletes items there.",
            file=sys.stderr,
        )
        return 2

    try:
        _authenticate(args.env_file)
        pf.setup_logging(
            level="INFO" if args.verbose else "WARNING",
            format_style="minimal",
            include_colors=False,
        )
        workspace_id, created = _open_sandbox(args)
    except E2EFailure as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 1

    run = Run(
        workspace=args.workspace,
        workspace_id=workspace_id,
        prefix=args.prefix,
        root=Path(tempfile.mkdtemp(prefix="pyfabricops-e2e-")),
    )
    try:
        _remove_what_the_run_created(run)
        _init_repository(run)
        for step in _STEPS:
            step(run)
    except E2EFailure as e:
        print(f"\n[FAIL] {e}", file=sys.stderr)
        return 1
    finally:
        if args.keep:
            print(
                "\nKept the items, the local repository and the staging "
                f"copy at {run.root}."
            )
        else:
            print()
            _remove_what_the_run_created(run)
            _remove_tree(run.root)
            if args.delete_workspace and created:
                pf.delete_workspace(workspace_id)
                print(f"Deleted workspace '{args.workspace}'.")

    print("\nAll steps passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
