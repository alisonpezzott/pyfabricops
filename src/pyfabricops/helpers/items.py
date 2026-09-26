import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pandas import DataFrame

from ..core.workspaces import resolve_workspace
from ..helpers.deployment import (
    DeploymentReport,
    _deploy_all,
    _plan_all,
    _reconcile_all,
)
from ..helpers.deployment_plan import DeploymentPlan
from ..helpers.deployment_state import DeploymentStateBackend
from ..helpers.folders import (
    create_folders_from_path_string,
    resolve_folder_from_id_to_path,
)
from ..helpers.reconciliation import Reconciliation
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
    resolve_dependencies: bool = True,
    allow_deletions: bool = False,
) -> DeploymentReport:
    """
    Deploy all items found under a local path to a workspace.

    Local items are matched to workspace items by type and display name (from
    ``.platform``): existing items get their definition updated, and are
    moved when their local folder differs; missing items are created. The
    workspace items and folders are listed once per run, and the item types
    are deployed in dependency order (``DEPLOY_ORDER``). A failed item does
    not stop the run unless ``fail_fast`` is set.

    With ``baseline_commit``, only the items changed in Git between that
    commit and HEAD are deployed (selective deployment).

    An item deleted in Git since the baseline is deleted from the workspace
    only with ``allow_deletions``, once every other item succeeded, and by
    type in the reverse of ``DEPLOY_ORDER``, so that an item goes before
    what it refers to. Without it the item is blocked, so the run fails and
    the state stays until a run allows it or the item is deleted by hand.
    It is blocked as well while an item that stays in the source refers to
    it: by a reference the engine reads (a report's semantic model, a
    notebook's default lakehouse, environment or ``%run``), whatever
    ``resolve_dependencies`` says, or by its ID in the workspace, for a
    lakehouse its SQL analytics endpoint's too. No item is deleted because
    another one is. It needs nothing when the source still defines it in
    another folder, or the workspace no longer has it. A run without a
    baseline, or a type left out of ``item_types``, deletes nothing. Fabric
    keeps a deleted item in the workspace recycle bin when its type supports
    it, such as a lakehouse or a notebook; it deletes a semantic model or a
    report for good.

    With ``state_backend``, the baseline comes from the last successful
    deployment to ``environment``, kept per item type: a type deploys what
    changed since it was last deployed, or every item when it never was.
    An item whose definition and folder are those its last successful
    deployment sent is skipped, even when Git lists it, since changes of
    layout or line endings do not count; one whose folder only changed is
    moved without sending its definition, to the workspace root too. When
    every item succeeds, HEAD and
    what was sent for each item are recorded; otherwise the state stays,
    and the next run compares from the same commits. A run without
    ``state_backend`` compares nothing and deploys every candidate. With a
    backend that locks, as the backends of pyfabricops do, the run holds the
    lock of the environment from before it reads the state until after it
    records it, so two runs never deploy to one environment at a time.

    With ``resolve_dependencies`` (the default), the references between
    local items are read, such as a report's semantic model. Each item
    is deployed after what it needs. What an item to deploy needs, when
    not selected, is validated if the workspace has it, and created
    otherwise when it is in the source and among ``item_types``. An item
    is blocked when a reference of its definition is broken, when it is
    part of a dependency cycle, or when something it needs is blocked or
    cannot be created.

    A report whose ``definition.pbir`` points to its semantic model by path
    is sent with a connection to that model's ID in the workspace instead,
    as the Fabric API accepts no path; the file is left as it is.

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
        resolve_dependencies (bool, optional): Order, meet and check the
            dependencies of the items. Defaults to True; False keeps the
            type and path order and deploys only the selected items.
        allow_deletions (bool, optional): Delete from the workspace the
            items deleted in Git since the baseline. Defaults to False: each
            is blocked and fails the run, so the deletion is not missed.

    Returns:
        DeploymentReport: The outcome of each item; ``report.failed`` lists
            the items that failed.

    Raises:
        ConfigurationError: With ``baseline_commit`` or ``state_backend``, if
            git cannot run, the folder is not in a Git repository or a commit
            is not in its history (a shallow clone may lack it); with
            ``state_backend``, also if the stored state is invalid.
        DeploymentLockedError: If another run holds the lock of the
            environment; nothing was deployed.

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
        resolve_dependencies=resolve_dependencies,
        allow_deletions=allow_deletions,
    )


def plan_all_items(
    workspace: str,
    path: str,
    start_path: str | None = None,
    *,
    item_types: Sequence[str] | None = None,
    baseline_commit: str | None = None,
    repository_path: str | None = None,
    state_backend: DeploymentStateBackend | None = None,
    environment: str | None = None,
    resolve_dependencies: bool = True,
    allow_deletions: bool = False,
) -> DeploymentPlan:
    """
    Show what ``deploy_all_items`` would do, without doing it.

    The plan is built as ``deploy_all_items`` builds it with the same
    arguments: same items, baselines, hashes and decisions. It is not
    applied, and the deployment state is read but never updated. Only reads
    happen: the local items, Git, and one listing of the workspace items and
    folders.

    Args:
        workspace (str): The name or ID of the workspace.
        path (str): The path to the items.
        start_path (Optional[str]): The local path that maps to the
            workspace root, used to derive each item's folder.
        item_types (Sequence[str], optional): The item types to plan.
            Defaults to every type in ``DEPLOY_ORDER``.
        baseline_commit (str, optional): Plan only the items changed since
            this commit. Defaults to None: every item.
        repository_path (str, optional): The folder of the Git repository
            that ``path`` was copied from. Defaults to ``path``.
        state_backend (DeploymentStateBackend, optional): Where the
            deployment state is kept. Defaults to None: no state.
        environment (str, optional): The name the state is kept under.
            Defaults to ``workspace``.
        resolve_dependencies (bool, optional): Order, meet and check the
            dependencies of the items, as ``deploy_all_items`` does.
            Defaults to True.
        allow_deletions (bool, optional): Plan as DELETE the deletions
            ``deploy_all_items`` would make with ``allow_deletions``.
            Defaults to False: they are planned as blocked.

    Returns:
        DeploymentPlan: One action per selected item, and per dependency
            met, saying what would happen and why; ``plan.describe()``
            gives it as text.

    Raises:
        ConfigurationError: If the workspace is not found, or, with
            ``baseline_commit`` or ``state_backend``, for the Git and state
            errors ``deploy_all_items`` raises.
        RequestError: If the workspace items and folders cannot be listed.

    Examples:
        ```python
        plan = plan_all_items(
            'Sales-PRD',
            staging,
            start_path=staging,
            repository_path='workspace',
            state_backend=LocalJsonStateBackend('.pyfabricops/state'),
            environment='prod',
        )
        print(plan.describe())
        ```
    """
    return _plan_all(
        workspace,
        path,
        start_path=start_path,
        item_types=item_types,
        baseline_commit=baseline_commit,
        repository_path=repository_path,
        state_backend=state_backend,
        environment=environment,
        resolve_dependencies=resolve_dependencies,
        allow_deletions=allow_deletions,
    )


def reconcile_items(
    workspace: str,
    path: str,
    start_path: str | None = None,
    *,
    item_types: Sequence[str] | None = None,
    state_backend: DeploymentStateBackend | None = None,
    environment: str | None = None,
) -> Reconciliation:
    """
    Tell how a workspace stands against the source, changing nothing.

    Every local item in scope is compared with the workspace: an item the
    workspace lacks, one whose definition differs, one in another folder.
    Each definition is compared with the one the workspace returns,
    leaving out what Fabric rewrites by itself, such as the logical ID it
    assigns or a report's connection to its model. The items the workspace
    holds and the source does not are listed as unmanaged, of any type but
    the SQL endpoint that comes with a lakehouse.

    With ``state_backend``, a difference tells where it comes from:
    changed in the workspace since the last successful deployment
    (``WORKSPACE_DRIFT``), or in the source, a deployment still to run
    (``SOURCE_CHANGED``). Without it, every difference counts as drift.

    Nothing in the workspace changes, and the state is only read. It reads
    the definition of every item found on both sides, so it suits a
    scheduled run, or a check before a release, more than every
    deployment.

    Args:
        workspace (str): The name or ID of the workspace.
        path (str): The path to the items, such as a staging copy with the
            placeholders of the environment replaced.
        start_path (Optional[str]): The local path that maps to the
            workspace root, used to derive each item's folder.
        item_types (Sequence[str], optional): The item types to compare.
            Defaults to every type in ``DEPLOY_ORDER``. An item of the
            source of another type is still never unmanaged.
        state_backend (DeploymentStateBackend, optional): Where the
            deployment state is kept. Defaults to None: no state.
        environment (str, optional): The name the state is kept under.
            Defaults to ``workspace``.

    Returns:
        Reconciliation: The plan that would bring the workspace back to the
            source, the unmanaged items, the items whose definition could
            not be compared, and the items in sync; ``describe()`` gives it
            as text, and ``ok`` tells whether anything differs.

    Raises:
        ConfigurationError: If the workspace is not found, or the state is
            invalid.
        RequestError: If the workspace items and folders cannot be listed.

    Examples:
        ```python
        reconciliation = reconcile_items(
            'Sales-PRD',
            staging,
            start_path=staging,
            state_backend=LocalJsonStateBackend('.pyfabricops/state'),
            environment='prod',
        )
        print(reconciliation.describe())
        if not reconciliation.ok:
            raise SystemExit(1)
        ```
    """
    return _reconcile_all(
        workspace,
        path,
        start_path=start_path,
        item_types=item_types,
        state_backend=state_backend,
        environment=environment,
    )
