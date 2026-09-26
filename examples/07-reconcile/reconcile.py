"""
Report how a workspace stands against the source, changing nothing.

Run it on a schedule, or before a release. It stages the items and sets
their placeholders as a deployment would, then compares every item with
the workspace: an item missing there, one changed by hand, one in another
folder, and the items the workspace holds that the source does not.

With the deployment state of ``04-deploy-selective``, read from its
lakehouse (``--state-workspace`` and ``--state-lakehouse``) or its folder
(``--state-dir``), a difference tells where it comes from: changed in the
workspace since the last deployment (``WORKSPACE_DRIFT``), or in the
source, a deployment still to run (``SOURCE_CHANGED``). Without it, every
difference counts as drift. The state is only read, and not locked.

It exits with 1 when anything differs, so that a scheduled CI job fails
and someone looks. Nothing in the workspace changes: deploy to bring back
what differs, and delete unmanaged items by hand when they should go.

With ``--restore`` it brings back what drifted instead: what was deleted,
edited or moved in the workspace goes back, pipelines last, once the items
they refer to by ID are back. Items changed in the source since the last
deployment are left to the next one, which takes the deployment state.
Nothing is deleted. It exits with 1 when an item fails.

Usage::

    python examples/07-reconcile/reconcile.py \\
        --workspace <workspace-name> --environment PRD \\
        --state-workspace <ops-workspace> --state-lakehouse <lakehouse>
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

import pyfabricops as pf

SAMPLE = Path(__file__).resolve().parents[1] / "sample-workspace"
PIPELINES = r".*pipeline-content\.json$"
# The item each pipeline placeholder stands for, by type and display name.
PIPELINE_IDS = {
    "#{load_orders_notebook_id}#": ("Notebook", "LoadOrders"),
}


def stage(source: Path, staging_dir: str, environment: str) -> str:
    """Copy the items to staging, and set the environment there."""
    staging: str = pf.copy_to_staging(str(source), staging_dir=staging_dir)
    pf.find_and_replace(
        staging,
        {(r".*\.tmdl$", re.escape("#{environment}#")): environment},
    )
    return staging


def set_pipeline_ids(staging: str, workspace: str) -> None:
    """
    Replace the pipeline placeholders with IDs from the workspace.

    An item the workspace lacks keeps its placeholder: the reconciliation
    reports it missing, and the pipeline different.
    """
    workspace_id = pf.resolve_workspace(workspace)
    if workspace_id is None:
        raise SystemExit(f"Workspace {workspace} not found.")
    ids = {
        (item["type"], item["displayName"]): item["id"]
        for item in pf.list_items(workspace_id, df=False) or []
    }
    replacements = {
        (PIPELINES, re.escape("#{workspace_id}#")): workspace_id,
    }
    for placeholder, key in PIPELINE_IDS.items():
        if key in ids:
            replacements[(PIPELINES, re.escape(placeholder))] = ids[key]
    pf.find_and_replace(staging, replacements)


def restore(workspace: str, staging: str, arguments: dict[str, Any]) -> int:
    """Bring back what drifted, pipelines last; 1 when an item fails."""
    others = [t for t in pf.DEPLOY_ORDER if t != "DataPipeline"]
    first = pf.restore_items(
        workspace, staging, item_types=others, **arguments
    )
    print(first.describe())
    # The pipelines refer to items by ID: set the IDs once those are back.
    set_pipeline_ids(staging, workspace)
    pipelines = pf.restore_items(
        workspace, staging, item_types=["DataPipeline"], **arguments
    )
    print(pipelines.describe())
    return 0 if first.ok and pipelines.ok else 1


def state_backend(
    args: argparse.Namespace,
) -> pf.DeploymentStateBackend | None:
    """The state in a lakehouse or a folder, when either is given."""
    if args.state_lakehouse:
        return pf.OneLakeStateBackend(
            args.state_workspace, args.state_lakehouse
        )
    if args.state_dir:
        return pf.LocalJsonStateBackend(args.state_dir)
    return None


def main(argv: Sequence[str] | None = None) -> int:
    """Reconcile the source with the workspace; 1 when anything differs."""
    parser = argparse.ArgumentParser(
        description="Report how a workspace stands against the source."
    )
    parser.add_argument(
        "--workspace", required=True, help="The workspace, by name or ID."
    )
    parser.add_argument(
        "--environment",
        default="PRD",
        help="The environment, which also names its state. Default: PRD",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=SAMPLE,
        help="The folder of items. Default: the sample workspace",
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
        "--restore",
        action="store_true",
        help="Bring back what drifted, instead of only reporting it.",
    )
    args = parser.parse_args(argv)
    if bool(args.state_workspace) != bool(args.state_lakehouse):
        parser.error("--state-workspace and --state-lakehouse go together")

    load_dotenv()
    pf.set_auth_provider("env")

    with tempfile.TemporaryDirectory(prefix="pyfabricops-") as staging_dir:
        staging = stage(args.source, staging_dir, args.environment)
        arguments: dict[str, Any] = {
            "start_path": staging,
            "state_backend": state_backend(args),
            "environment": args.environment,
        }
        if args.restore:
            return restore(args.workspace, staging, arguments)
        set_pipeline_ids(staging, args.workspace)
        reconciliation = pf.reconcile_items(
            args.workspace, staging, **arguments
        )
    print(reconciliation.describe())
    return 0 if reconciliation.ok else 1


if __name__ == "__main__":
    sys.exit(main())
