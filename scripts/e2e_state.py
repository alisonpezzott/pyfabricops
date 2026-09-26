"""
End-to-end check of OneLakeStateBackend against a real Fabric workspace.

Creates a lakehouse in a sandbox workspace and keeps deployment states in
it, as a deployment pipeline would. Steps: a state saved and read back; a
save refused because another run saved first; a lock another run holds;
an expired lock taken over; a lock removed with ``force_unlock``; and a
deployment whose state lives in the lakehouse, which a second run then
reads. At the end the script deletes what it created.

Prerequisites, as for ``scripts/e2e_deployment.py``:

- A service principal in an ``.env`` file (``FAB_CLIENT_ID``,
  ``FAB_CLIENT_SECRET``, ``FAB_TENANT_ID``), in a tenant that lets service
  principals use Fabric APIs.
- A sandbox workspace on a Fabric capacity, with the service principal as
  Contributor or above, holding nothing but what this script creates.
- git on PATH.

Usage::

    uv run --frozen python scripts/e2e_state.py \\
        --workspace pyfabricops-e2e --env-file project/.env

It runs only with an explicit workspace (``--workspace`` or
``PYFABRICOPS_E2E_WORKSPACE``).
"""

from __future__ import annotations

import argparse
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
_CREDENTIALS = ("FAB_CLIENT_ID", "FAB_CLIENT_SECRET", "FAB_TENANT_ID")
# The folder of the states in the lakehouse Files.
_FOLDER = "pyfabricops/e2e"
_PLATFORM_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/"
    "platformProperties/2.0.0/schema.json"
)
# Items Fabric creates along with a lakehouse, and deletes with it.
_CHILD_TYPES = frozenset({"SQLEndpoint"})
_NOTEBOOK = """# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# CELL ********************

print("Hello from the pyfabricops state e2e run, version __VERSION__")

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
    def lakehouse(self) -> str:
        """The lakehouse that keeps the states."""
        return f"{self.prefix}_L"

    @property
    def notebook(self) -> str:
        """The notebook the deployment step deploys."""
        return f"{self.prefix}_N"

    @property
    def items(self) -> Path:
        """The local Git repository of the deployment step."""
        return self.root / "repo"

    def backend(self, **kwargs: Any) -> pf.OneLakeStateBackend:
        """A backend over the run's lakehouse, as a new run would make."""
        return pf.OneLakeStateBackend(
            self.workspace, self.lakehouse, _FOLDER, **kwargs
        )


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def _step_lakehouse(run: Run) -> None:
    print("\n== A lakehouse for the states")
    pf.create_lakehouse(run.workspace_id, run.lakehouse, df=False)
    _check(
        _wait(lambda: _item_id(run, "Lakehouse", run.lakehouse) is not None),
        "the lakehouse is created",
    )


def _step_round_trip(run: Run) -> None:
    print("\n== A state saved in OneLake and read back")
    backend = run.backend()
    _check(backend.load(_ENVIRONMENT) is None, "there is no state yet")
    backend.save(_ENVIRONMENT, _state(run, "a"))
    _check(
        run.backend().load(_ENVIRONMENT) == _state(run, "a"),
        "a new run reads the state saved",
    )


def _step_conflict(run: Run) -> None:
    print("\n== Two runs save over the same state")
    first, second = run.backend(), run.backend()
    first.load(_ENVIRONMENT)
    second.load(_ENVIRONMENT)
    first.save(_ENVIRONMENT, _state(run, "b"))
    try:
        second.save(_ENVIRONMENT, _state(run, "c"))
    except pf.RequestError as e:
        print(f"    {e}")
        _check("since this run read it" in str(e), "the later save is refused")
    else:
        raise E2EFailure("the later save overwrote the earlier one")
    _check(
        run.backend().load(_ENVIRONMENT) == _state(run, "b"),
        "the state saved first is kept",
    )


def _step_lock_held(run: Run) -> None:
    print("\n== A lock another run holds")
    with run.backend().lock(_ENVIRONMENT) as held:
        try:
            with run.backend().lock(_ENVIRONMENT):
                raise E2EFailure("two runs held the lock at once")
        except pf.DeploymentLockedError as e:
            print(f"    {e}")
            _check(held.holder in str(e), "the error names who holds it")
    with run.backend().lock(_ENVIRONMENT):
        _check(True, "once released, the lock can be taken again")


def _step_lock_expired(run: Run) -> None:
    print("\n== The lock of a run that died, once expired")
    abandoned = run.backend(lock_ttl=1).lock(_ENVIRONMENT)
    gone = abandoned.__enter__()
    time.sleep(3)
    with run.backend().lock(_ENVIRONMENT) as held:
        _check(held.lock_id != gone.lock_id, "another run takes it over")
    # The run that died cannot remove the lock of the one that took over.
    abandoned.__exit__(None, None, None)
    _check(run.backend().force_unlock(_ENVIRONMENT) is None, "no lock is left")


def _step_force_unlock(run: Run) -> None:
    print("\n== force_unlock for a run that is gone")
    abandoned = run.backend().lock(_ENVIRONMENT)
    gone = abandoned.__enter__()
    removed = run.backend().force_unlock(_ENVIRONMENT)
    _check(
        removed is not None and removed.lock_id == gone.lock_id,
        "it removes that run's lock and says whose it was",
    )
    with run.backend().lock(_ENVIRONMENT):
        _check(True, "then the lock can be taken")
    abandoned.__exit__(None, None, None)


def _step_deployment(run: Run) -> None:
    print("\n== A deployment whose state lives in the lakehouse")
    _init_repository(run)
    _write_notebook(run, version=1)
    head = _commit(run, "Add the notebook")
    arguments: dict[str, Any] = {
        "start_path": str(run.items),
        "repository_path": str(run.items),
        "environment": "deploy",
    }

    report = pf.deploy_all_items(
        run.workspace, str(run.items), state_backend=run.backend(), **arguments
    )
    print(_indent(report.describe()))
    _check(
        [(r.display_name, r.action) for r in report.results]
        == [(run.notebook, "created")],
        "the notebook is deployed",
    )
    state = run.backend().load("deploy")
    _check(
        state is not None
        and state.source_commit == head
        and ("Notebook", run.notebook) in state.items,
        "the state in the lakehouse records the deployment",
    )
    _check(
        run.backend().force_unlock("deploy") is None,
        "the deployment released its lock",
    )

    again = pf.deploy_all_items(
        run.workspace, str(run.items), state_backend=run.backend(), **arguments
    )
    _check(
        again.results == [],
        "a second run reads the state and has nothing to do",
    )


_STEPS: tuple[Callable[[Run], None], ...] = (
    _step_lakehouse,
    _step_round_trip,
    _step_conflict,
    _step_lock_held,
    _step_lock_expired,
    _step_force_unlock,
    _step_deployment,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check(condition: bool, what: str) -> None:
    """Print a passed check, or stop the run on a failed one."""
    if not condition:
        raise E2EFailure(what)
    print(f"  [ok] {what}")


def _state(run: Run, letter: str) -> pf.DeploymentState:
    """A state of the sandbox, told apart by the commit it records."""
    commit = letter * 40
    return pf.DeploymentState(
        environment=_ENVIRONMENT,
        workspace=run.workspace,
        workspace_id=run.workspace_id,
        source_commit=commit,
        commits={"Notebook": commit},
        deployed_at_utc="2026-09-25T12:00:00Z",
    )


def _wait(condition: Callable[[], bool]) -> bool:
    """Wait up to a minute for a condition to hold."""
    for _ in range(30):
        if condition():
            return True
        time.sleep(2)
    return False


def _indent(text: str) -> str:
    return "\n".join(f"    {line}" for line in text.splitlines())


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
    _git(run, "commit", "--quiet", "--message", message)
    return _git(run, "rev-parse", "HEAD")


def _git(run: Run, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(run.items), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _write_notebook(run: Run, *, version: int) -> None:
    item = run.items / f"{run.notebook}.Notebook"
    item.mkdir(parents=True, exist_ok=True)
    platform = {
        "$schema": _PLATFORM_SCHEMA,
        "metadata": {"type": "Notebook", "displayName": run.notebook},
        "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
    }
    (item / ".platform").write_text(
        json.dumps(platform, indent=2), encoding="utf-8"
    )
    (item / "notebook-content.py").write_text(
        _NOTEBOOK.replace("__VERSION__", str(version)), encoding="utf-8"
    )


def _list_items(workspace_id: str) -> list[dict[str, Any]]:
    items = pf.list_items(workspace_id, df=False)
    if items is None:
        raise E2EFailure("Could not list the workspace items.")
    return list(items)


def _item_id(run: Run, item_type: str, name: str) -> str | None:
    """The ID of an item of the workspace, or None if it has none."""
    for item in _list_items(run.workspace_id):
        if (item["type"], item["displayName"]) == (item_type, name):
            item_id: str = item["id"]
            return item_id
    return None


def _remove_what_the_run_created(run: Run) -> None:
    """Delete the run's items, the notebook before the lakehouse."""
    created = [
        item
        for item in _list_items(run.workspace_id)
        if item["displayName"].startswith(f"{run.prefix}_")
        and item["type"] not in _CHILD_TYPES
    ]
    for item in sorted(created, key=lambda i: i["type"] == "Lakehouse"):
        pf.delete_item(run.workspace_id, item["id"])
        print(f"Deleted {item['displayName']}.{item['type']}.")


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
    pf.clear_token_cache()
    pf.set_auth_provider("env")


def _open_sandbox(workspace: str, prefix: str) -> str:
    """Find the sandbox and make sure it holds nothing else."""
    workspace_id = pf.resolve_workspace(workspace)
    if workspace_id is None:
        raise E2EFailure(
            f"Workspace '{workspace}' not found. Create it on a Fabric "
            "capacity and add the service principal as Contributor."
        )
    others = [
        f"{item['displayName']}.{item['type']}"
        for item in _list_items(workspace_id)
        if not item["displayName"].startswith(f"{prefix}_")
    ]
    if others:
        raise E2EFailure(
            f"Workspace '{workspace}' holds items this script did not "
            f"create ({', '.join(others[:5])}); use an empty sandbox."
        )
    return workspace_id


def _prefix(value: str) -> str:
    """Accept a prefix that keeps the lakehouse name valid."""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value):
        raise argparse.ArgumentTypeError(
            "use a letter, then letters, digits or underscores, as lakehouse "
            "names must"
        )
    return value


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check OneLakeStateBackend against a sandbox workspace."
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
        default="pfo_state",
        help="Prefix of the items the run creates. Default: pfo_state",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Show the library log."
    )
    return parser.parse_args(argv)


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
        workspace_id = _open_sandbox(args.workspace, args.prefix)
    except E2EFailure as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 1

    run = Run(
        workspace=args.workspace,
        workspace_id=workspace_id,
        prefix=args.prefix,
        root=Path(tempfile.mkdtemp(prefix="pyfabricops-e2e-state-")),
    )
    try:
        _remove_what_the_run_created(run)
        for step in _STEPS:
            step(run)
    except (E2EFailure, pf.PyFabricOpsError) as e:
        print(f"\n[FAIL] {e}", file=sys.stderr)
        return 1
    finally:
        print()
        _remove_what_the_run_created(run)
        _remove_tree(run.root)

    print("\nAll steps passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
