"""
Deploy a folder of Fabric items to a workspace: the sample, by default.

What a deployment pipeline runs, in order:

1. Copy the items to a staging folder, so the repository is never changed.
2. Replace the placeholders in the copy with the values of the target:
   here the environment name, which the sample report shows.
3. Plan: print what will be created, updated or left alone, and why.
4. Deploy. Each item comes after what it needs, and a report is bound to
   its semantic model in the target workspace.

A data pipeline refers to the notebooks it runs by ID, which exists only
once the notebook is in the workspace. So pipelines go last, in a second
pass, once those IDs are known. For another folder of items, list its
pipeline placeholders in ``PIPELINE_IDS``.

Usage::

    python examples/03-deploy-full/deploy.py \\
        --workspace <workspace-name> --environment DEV
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


def deploy(workspace: str, staging: str, item_types: list[str]) -> bool:
    """Plan and deploy some item types; True when every item succeeded."""
    arguments: dict[str, Any] = {
        "start_path": staging,
        "item_types": item_types,
    }
    print(pf.plan_all_items(workspace, staging, **arguments).describe())
    report = pf.deploy_all_items(workspace, staging, **arguments)
    for result in report.results:
        error = f": {result.error}" if result.error else ""
        print(
            f"  {result.display_name}.{result.item_type} {result.action}{error}"
        )
    ok: bool = report.ok
    return ok


def main(argv: Sequence[str] | None = None) -> int:
    """Deploy the items, pipelines last; 0 when every item succeeded."""
    parser = argparse.ArgumentParser(
        description="Deploy a folder of Fabric items to a workspace."
    )
    parser.add_argument(
        "--workspace", required=True, help="The workspace, by name or ID."
    )
    parser.add_argument(
        "--environment",
        default="DEV",
        help="The environment name the items are set up for. Default: DEV",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=SAMPLE,
        help="The folder of items. Default: the sample workspace",
    )
    args = parser.parse_args(argv)

    load_dotenv()
    pf.set_auth_provider("env")

    with tempfile.TemporaryDirectory(prefix="pyfabricops-") as staging_dir:
        staging = stage(args.source, staging_dir, args.environment)

        print("== Everything but the pipelines")
        others = [t for t in pf.DEPLOY_ORDER if t != "DataPipeline"]
        if not deploy(args.workspace, staging, others):
            return 1

        print("== The pipelines")
        set_pipeline_ids(staging, args.workspace)
        if not deploy(args.workspace, staging, ["DataPipeline"]):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
