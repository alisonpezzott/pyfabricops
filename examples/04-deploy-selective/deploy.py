"""
Deploy only what changed in Git since the last successful deployment.

Run it in a deployment pipeline, from a clone of the repository with its
history. A deployment state, a JSON file per environment in
``--state-dir``, records the commit and a hash of each item a successful
run deployed. The next run starts from there:

- items changed in Git since then are deployed; the others are left alone;
- an item whose definition hash is unchanged needs nothing, even when its
  files changed, as when a file is only reformatted;
- what a changed item needs is checked in the workspace, and created when
  missing: change only the report, and its model is checked first.

A run with a failed item records nothing, so the next one compares from
the same commits. Keep ``--state-dir`` between runs, as the CI examples
do with a cache: without it, a run deploys every item, which is safe but
slower. The steps are those of ``03-deploy-full``, pipelines last.

Usage::

    python examples/04-deploy-selective/deploy.py \\
        --workspace <workspace-name> --environment PRD \\
        --state-dir .deploy-state
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
    """Replace the pipeline placeholders with IDs from the workspace."""
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
        if key not in ids:
            raise SystemExit(f"{key[1]}.{key[0]} is not in the workspace.")
        replacements[(PIPELINES, re.escape(placeholder))] = ids[key]
    pf.find_and_replace(staging, replacements)


def deploy(workspace: str, staging: str, arguments: dict[str, Any]) -> bool:
    """Plan and deploy; True when every item succeeded."""
    print(pf.plan_all_items(workspace, staging, **arguments).describe())
    report = pf.deploy_all_items(workspace, staging, **arguments)
    print(report.describe())
    ok: bool = report.ok
    return ok


def main(argv: Sequence[str] | None = None) -> int:
    """Deploy what changed, pipelines last; 0 when every item succeeded."""
    parser = argparse.ArgumentParser(
        description="Deploy what changed in Git since the last deployment."
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
        help="The folder of items, in a Git repository. Default: the sample",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path(".deploy-state"),
        help="Where the deployment state is kept. Default: .deploy-state",
    )
    args = parser.parse_args(argv)

    load_dotenv()
    pf.set_auth_provider("env")

    with tempfile.TemporaryDirectory(prefix="pyfabricops-") as staging_dir:
        staging = stage(args.source, staging_dir, args.environment)
        arguments: dict[str, Any] = {
            "start_path": staging,
            # The items in Git, which the staging copy came from.
            "repository_path": str(args.source),
            "state_backend": pf.LocalJsonStateBackend(args.state_dir),
            "environment": args.environment,
        }

        print("== Everything but the pipelines")
        others = [t for t in pf.DEPLOY_ORDER if t != "DataPipeline"]
        if not deploy(
            args.workspace, staging, {**arguments, "item_types": others}
        ):
            return 1

        print("== The pipelines")
        set_pipeline_ids(staging, args.workspace)
        if not deploy(
            args.workspace,
            staging,
            {**arguments, "item_types": ["DataPipeline"]},
        ):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
