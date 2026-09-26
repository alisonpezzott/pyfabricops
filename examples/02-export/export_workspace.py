"""
Export the items of a workspace to a folder, to start a repository.

Each item becomes a folder in the format Fabric Git integration writes,
under the workspace folders it is in. Reports come back pointing to their
semantic model by connection; this script turns them back into a path to
the model's folder, the form a repository keeps and the deployment engine
reads.

Before committing, look through the exported files, and keep client data
out of the repository. They hold the IDs of that workspace, such as a
pipeline's notebook or a notebook's default lakehouse. Leave them: the
deployment of ``examples/Adventure-Works-LT``, given that workspace as its
source, turns them into the IDs of the workspace it deploys to.

Usage::

    python examples/02-export/export_workspace.py \\
        --workspace <workspace-name> --path exported
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from dotenv import load_dotenv

import pyfabricops as pf


def main(argv: Sequence[str] | None = None) -> None:
    """Export every item of the workspace, then point reports by path."""
    parser = argparse.ArgumentParser(
        description="Export the items of a workspace to a folder."
    )
    parser.add_argument(
        "--workspace", required=True, help="The workspace, by name or ID."
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("exported"),
        help="The folder to export into. Default: exported",
    )
    args = parser.parse_args(argv)

    load_dotenv()
    pf.set_auth_provider("env")

    pf.export_all_items(args.workspace, str(args.path))
    for report in sorted(args.path.rglob("*.Report")):
        pf.convert_report_definition_to_by_path(report, args.path)
    print(f"Exported {args.workspace} to {args.path}.")


if __name__ == "__main__":
    main()
