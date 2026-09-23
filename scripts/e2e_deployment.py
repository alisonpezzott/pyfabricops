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
by hand).

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
import contextlib
import json
import os
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
_NOTEBOOK = """# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

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
    staging: Path | None = None

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
        return f"{self.prefix}-folder"

    def name(self, letter: str) -> str:
        """The display name of an item of the run."""
        return f"{self.prefix}-{letter}"


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
) -> pf.DeploymentReport:
    """Plan, check the plan, deploy, check the report."""
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

    report = pf.deploy_all_items(run.workspace, staging, **arguments)
    for result in report.results:
        error = f": {result.error}" if result.error else ""
        print(f"    {result.display_name} {result.action}{error}")
    _check(
        [(r.display_name, r.action) for r in report.results]
        == [(run.name(letter), outcome) for letter, outcome in results],
        "the deployment did what the plan said",
    )
    return report


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
    staging: str = pf.copy_to_staging(str(run.items))
    run.staging = Path(staging)
    pf.find_and_replace(staging, {(r".*\.py$", r"#\{GREETING\}#"): _GREETING})
    return staging


def _write_notebook(run: Run, letter: str, *, version: int) -> None:
    item = _item_folder(run, letter, "Notebook")
    content = _NOTEBOOK.replace("__LETTER__", letter).replace(
        "__VERSION__", str(version)
    )
    (item / "notebook-content.py").write_text(content, encoding="utf-8")


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
        if not item["displayName"].startswith(f"{args.prefix}-")
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
    for item in _list_items(run.workspace_id):
        if item["displayName"].startswith(f"{run.prefix}-"):
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


def _folder_of(run: Run, item_type: str, name: str) -> str | None:
    """The ID of the workspace folder an item is in, or None at the root."""
    for item in _list_items(run.workspace_id):
        if (item["type"], item["displayName"]) == (item_type, name):
            folder_id: str | None = item.get("folderId")
            return folder_id
    raise E2EFailure(f"{name}.{item_type} is not in the workspace")


def _remove_staging(run: Run) -> None:
    """
    Remove the staging copy, and its parent if nothing else is there.

    ``copy_to_staging`` writes inside the pyfabricops package, so the copy
    would outlive the run.
    """
    if run.staging is None or not run.staging.exists():
        return
    _remove_tree(run.staging)
    with contextlib.suppress(OSError):
        run.staging.parent.rmdir()


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
        default="pfo-e2e",
        help="Prefix of the items the run creates. Default: pfo-e2e",
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
            print(f"\nKept the items and the local repository at {run.root}.")
            if run.staging is not None:
                print(f"Kept the staging copy at {run.staging}.")
        else:
            print()
            _remove_what_the_run_created(run)
            _remove_tree(run.root)
            _remove_staging(run)
            if args.delete_workspace and created:
                pf.delete_workspace(workspace_id)
                print(f"Deleted workspace '{args.workspace}'.")

    print("\nAll steps passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
