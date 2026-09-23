import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pandas import DataFrame

from ..core.workspaces import resolve_workspace
from ..helpers.deployment import DeploymentReport, _deploy_all
from ..helpers.deployment_state import DeploymentStateBackend
from ..helpers.folders import (
    create_folders_from_path_string,
    resolve_folder_from_id_to_path,
)
from ..items.items import (
    create_item,
    get_item,
    get_item_definition,
    list_items,
    move_item,
    resolve_item,
    update_item_definition,
)
from ..utils.decorators import df
from ..utils.logging import get_logger
from ..utils.utils import (
    extract_display_name_from_platform,
    extract_middle_path,
    pack_item_definition,
    unpack_item_definition,
)

logger = get_logger(__name__)


def export_item(
    workspace: str,
    item: str,
    path: str,
):
    """
    Exports a item definition to a specified folder structure.

    Args:
        workspace (str): The workspace name or ID.
        item (str): The name of the item to export.
        path (str): The root path of the project.

    Examples:
        ```python
        export_item('MyProjectWorkspace', 'SalesDataModel', '/path/to/project')
        export_item('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', '/path/to/project')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    item_ = get_item(workspace_id, item, df=False)
    if not item_:
        return None

    item_id = item_["id"]
    definition = get_item_definition(workspace_id, item_id)
    if not definition:
        return None

    item_type = item_["type"]
    item_name = item_["displayName"]

    folder_id = None
    folder_path = None

    if "folderId" in item_:
        folder_id = item_["folderId"]
        try:
            folder_path = resolve_folder_from_id_to_path(
                workspace_id, folder_id
            )
        except Exception:
            logger.info(f"{item_name}.{item_type} is not inside a folder.")
            folder_path = None

    if folder_path is None:
        item_path = Path(path) / f"{item_name}.{item_type}"
    else:
        item_path = Path(path) / folder_path / f"{item_name}.{item_type}"

    os.makedirs(item_path, exist_ok=True)

    unpack_item_definition(definition, item_path)

    logger.success(
        f"{item_name}.{item_type} was exported to {item_path} successfully."
    )
    return None


def export_all_items(
    workspace: str,
    path: str,
) -> None:
    """
    Exports all items to the specified folder structure.

    An item that cannot be read is logged and skipped; the export goes on
    with the next one.

    Args:
        workspace (str): The workspace name or ID.
        path (str): The root path of the project.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    items = list_items(workspace_id, df=False)

    if items is None:
        return None

    items = [item for item in items if item["type"] != "SQLEndpoint"]

    failed = []

    for item in items:
        item_id = item["id"]
        item_ = get_item(workspace_id, item_id, df=False)
        if not item_:
            logger.error(
                f"Could not get {item['displayName']}.{item['type']}; "
                "skipping it."
            )
            failed.append(f"{item['displayName']}.{item['type']}")
            continue

        item_id = item_["id"]
        item_name = item_["displayName"]
        item_type = item_["type"]

        definition = get_item_definition(workspace_id, item_id)
        if not definition:
            logger.error(
                f"Could not get the definition of {item_name}.{item_type}; "
                "skipping it."
            )
            failed.append(f"{item_name}.{item_type}")
            continue

        folder_id = None
        folder_path = None

        if "folderId" in item_:
            folder_id = item_["folderId"]

            try:
                folder_path = resolve_folder_from_id_to_path(
                    workspace_id, folder_id
                )
            except Exception:
                logger.info(
                    f"{item['displayName']}.{item_type} is not inside a folder."
                )
                folder_path = None

        if folder_path is None:
            item_path = Path(path) / f"{item_name}.{item_type}"
        else:
            item_path = Path(path) / folder_path / f"{item_name}.{item_type}"
        os.makedirs(item_path, exist_ok=True)

        unpack_item_definition(definition, item_path)

        logger.success(
            f"{item_name}.{item_type} was exported to {item_path} successfully."
        )

    if failed:
        logger.warning(
            f"{len(failed)} item(s) could not be exported: {', '.join(failed)}."
        )
    return None


@df
def deploy_item(
    workspace: str,
    path: str,
    start_path: str | None = None,
    description: str | None = None,
    df: bool | None = True,
) -> DataFrame | dict[str, Any] | None:
    """
    Creates or updates a item in Fabric based on local folder structure.
    Automatically detects the folder_id based on where the item is located locally.

    Args:
        workspace (str): The workspace name or ID.
        path (str): The root path of the project.
        start_path (str, optional): The starting path for the item.
        description (str, optional): A description for the item.
        df (bool, optional): Whether to return a DataFrame. Defaults to True.
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    display_name = extract_display_name_from_platform(path)
    if display_name is None:
        return None
    item_type = path.split(".")[-1]
    item_with_type = f"{display_name}.{item_type}"
    item_id = resolve_item(workspace_id, item_with_type)

    item_definition = pack_item_definition(path)

    folder_path_string = extract_middle_path(path, start_path=start_path)
    folder_id = create_folders_from_path_string(
        workspace_id, folder_path_string
    )

    if item_id is None:
        return create_item(
            workspace_id,
            display_name=display_name,
            item_definition=item_definition,
            item_type=item_type,
            description=description,
            folder=folder_id,
            df=False,
        )

    else:
        if folder_id:
            move_item(workspace_id, item_id, target_folder=folder_id)
        return update_item_definition(
            workspace_id,
            item_id,
            item_definition=item_definition,
            df=False,
        )


def deploy_all_items(
    workspace: str,
    path: str,
    start_path: str | None = None,
    *,
    item_types: Sequence[str] | None = None,
    fail_fast: bool = False,
    baseline_commit: str | None = None,
    repository_path: str | None = None,
    state_backend: DeploymentStateBackend | None = None,
    environment: str | None = None,
) -> DeploymentReport:
    """
    Deploy all items found under a local path to a workspace.

    Local items are matched to workspace items by type and display name (from
    ``.platform``): existing items get their definition updated, and are
    moved when their local folder differs; missing items are created. The
    workspace items and folders are listed once per run, and the item types
    are deployed in dependency order (``DEPLOY_ORDER``). A failed item does
    not stop the run unless ``fail_fast`` is set. Nothing is ever deleted.

    With ``baseline_commit``, only the items changed in Git between that
    commit and HEAD are deployed (selective deployment). An item deleted
    since then is reported as failed while the workspace still has it,
    because deleting is not supported yet; once it is gone, it needs
    nothing.

    With ``state_backend``, the baseline comes from the last successful
    deployment to ``environment``, kept per item type: a type deploys what
    changed since it was last deployed, or every item when it never was.
    An item whose definition and folder are those its last successful
    deployment sent is skipped, even when Git lists it, since changes of
    layout or line endings do not count. When every item succeeds, HEAD and
    what was sent for each item are recorded; otherwise the state stays,
    and the next run compares from the same commits. A run without
    ``state_backend`` compares nothing and deploys every candidate.

    Args:
        workspace (str): The name or ID of the workspace.
        path (str): The path to the items.
        start_path (Optional[str]): The local path that maps to the
            workspace root, used to derive each item's folder.
        item_types (Sequence[str], optional): The item types to deploy.
            Defaults to every type in ``DEPLOY_ORDER``. Whatever the order
            given, the types are deployed in dependency order.
        fail_fast (bool, optional): Stop at the first failed item and mark
            the remaining ones as skipped. Defaults to False.
        baseline_commit (str, optional): Deploy only the items changed since
            this commit (an ID, tag or branch). Needs git, and the commit in
            the local history. Defaults to None: every item.
        repository_path (str, optional): The folder of the Git repository
            that ``path`` was copied from, such as the one given to
            ``copy_to_staging``: changes are found there and the items read
            from ``path``. Only used with ``baseline_commit`` or
            ``state_backend``. Defaults to ``path``.
        state_backend (DeploymentStateBackend, optional): Where the
            deployment state is kept, such as a ``LocalJsonStateBackend``.
            An explicit ``baseline_commit`` still wins over the state.
            Defaults to None: no state.
        environment (str, optional): The name the state is kept under, such
            as ``'prod'``. Defaults to ``workspace``.

    Returns:
        DeploymentReport: The outcome of each item; ``report.failed`` lists
            the items that failed.

    Raises:
        ConfigurationError: With ``baseline_commit`` or ``state_backend``, if
            git cannot run, the folder is not in a Git repository or a commit
            is not in its history (a shallow clone may lack it); with
            ``state_backend``, also if the stored state is invalid.

    Examples:
        ```python
        report = deploy_all_items(
            'Sales-DEV',
            'stg/workspace',
            start_path='stg/workspace',
            item_types=['Notebook', 'DataPipeline'],
        )
        if report.failed:
            raise SystemExit(1)

        # Only what changed since the last deployment
        staging = copy_to_staging('workspace')
        report = deploy_all_items(
            'Sales-PRD',
            staging,
            start_path=staging,
            baseline_commit=last_deployed_commit,
            repository_path='workspace',
        )

        # The same, with the baseline kept by the deployment state
        report = deploy_all_items(
            'Sales-PRD',
            staging,
            start_path=staging,
            repository_path='workspace',
            state_backend=LocalJsonStateBackend('.pyfabricops/state'),
            environment='prod',
        )
        ```
    """
    return _deploy_all(
        workspace,
        path,
        start_path=start_path,
        item_types=item_types,
        fail_fast=fail_fast,
        baseline_commit=baseline_commit,
        repository_path=repository_path,
        state_backend=state_backend,
        environment=environment,
    )
