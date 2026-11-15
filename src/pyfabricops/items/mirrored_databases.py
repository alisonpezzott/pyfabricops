"""
Mirroring of a mirrored database: its status, and starting or stopping it.

A mirrored database deploys like any item with a definition, its
``mirroring.json``, which names the connection to its source. Deploying the
definition does not start the replication, nor does the replication state
belong to it: start it once the database is deployed, and read its status
to know when it runs. The source must let the mirrored database in, such as
by granting its managed identity access to an Azure SQL database, which no
API of Fabric does.
"""

import time
from typing import Any, cast

from ..api.api import ApiResult, api_request
from ..core.workspaces import resolve_workspace
from ..utils.exceptions import RequestError, ResourceNotFoundError
from ..utils.logging import get_logger
from ..utils.utils import is_valid_uuid
from .items import list_items

logger = get_logger(__name__)

# What getMirroringStatus returns once the replication is up.
MIRRORING_RUNNING = "Running"
# What it returns while the replication is on its way up: no start is
# sent then. Initialized is not one: a mirrored database created through
# the API stays there until it is started.
_UNDER_WAY = frozenset({"Initializing", "Starting"})
# What it may return after a start, before it runs.
_STARTING = _UNDER_WAY | {"Initialized"}


def get_mirroring_status(workspace: str, mirrored_database: str) -> str:
    """
    Returns the status of the replication of a mirrored database.

    Args:
        workspace (str): The workspace name or ID.
        mirrored_database (str): The name or ID of the mirrored database.

    Returns:
        (str): ``Running`` once it replicates; ``Initializing`` or
            ``Starting`` on its way there; ``Initialized`` when created and
            never started, as through the API; ``Stopping`` or ``Stopped``
            otherwise.

    Raises:
        ResourceNotFoundError: If the workspace or the mirrored database is
            not found.
        RequestError: If the status cannot be read.

    Examples:
        ```python
        get_mirroring_status('Sales-PRD', 'ERP')
        ```
    """
    return _read_status(_endpoint(workspace, mirrored_database))


def get_tables_mirroring_status(
    workspace: str, mirrored_database: str
) -> list[dict[str, Any]]:
    """
    Returns the status of the replication of each table of a mirrored
    database.

    Args:
        workspace (str): The workspace name or ID.
        mirrored_database (str): The name or ID of the mirrored database.

    Returns:
        (list[dict[str, Any]]): One entry per table, as Fabric returns it,
            such as ``sourceSchemaName``, ``sourceTableName``, ``status``
            and ``metrics``.

    Raises:
        ResourceNotFoundError: If the workspace or the mirrored database is
            not found.
        RequestError: If the status cannot be read.

    Examples:
        ```python
        for table in get_tables_mirroring_status('Sales-PRD', 'ERP'):
            print(table['sourceTableName'], table['status'])
        ```
    """
    endpoint = _endpoint(workspace, mirrored_database)
    tables: list[dict[str, Any]] = []
    token: str | None = None
    while True:
        result = cast(
            ApiResult,
            api_request(
                f"{endpoint}/getTablesMirroringStatus",
                method="post",
                params={"continuationToken": token} if token else None,
                return_result=True,
            ),
        )
        if not result.success:
            raise RequestError(
                f"Could not read the tables mirroring status of "
                f"'{mirrored_database}': {result.error}"
            )
        data = result.data or {}
        tables += list(data.get("data") or [])
        token = data.get("continuationToken")
        if not token:
            return tables


def start_mirroring(workspace: str, mirrored_database: str) -> None:
    """
    Starts the replication of a mirrored database.

    Nothing is sent when it runs already, or is on its way up. One that
    is ``Initialized``, as a mirrored database created through the API
    stays until started, is started.

    Args:
        workspace (str): The workspace name or ID.
        mirrored_database (str): The name or ID of the mirrored database.

    Raises:
        ResourceNotFoundError: If the workspace or the mirrored database is
            not found.
        RequestError: If the status cannot be read, or the replication
            cannot be started, such as when the source refuses it.

    Examples:
        ```python
        start_mirroring('Sales-PRD', 'ERP')
        ```
    """
    endpoint = _endpoint(workspace, mirrored_database)
    status = _read_status(endpoint)
    if status == MIRRORING_RUNNING or status in _UNDER_WAY:
        logger.info(f"Mirrored database '{mirrored_database}' is {status}.")
        return
    _start(endpoint, mirrored_database)
    logger.success(f"Mirroring of '{mirrored_database}' started.")


def stop_mirroring(workspace: str, mirrored_database: str) -> None:
    """
    Stops the replication of a mirrored database.

    The tables replicated so far stay; starting it again replicates every
    table from the start.

    Args:
        workspace (str): The workspace name or ID.
        mirrored_database (str): The name or ID of the mirrored database.

    Raises:
        ResourceNotFoundError: If the workspace or the mirrored database is
            not found.
        RequestError: If the replication cannot be stopped.

    Examples:
        ```python
        stop_mirroring('Sales-PRD', 'ERP')
        ```
    """
    endpoint = _endpoint(workspace, mirrored_database)
    result = cast(
        ApiResult,
        api_request(
            f"{endpoint}/stopMirroring", method="post", return_result=True
        ),
    )
    if not result.success:
        raise RequestError(
            f"Could not stop the mirroring of '{mirrored_database}': "
            f"{result.error}"
        )
    logger.success(f"Mirroring of '{mirrored_database}' stopped.")


def start_mirroring_and_wait(
    workspace: str,
    mirrored_database: str,
    *,
    timeout: float = 600,
    poll_interval: float = 15,
) -> str:
    """
    Starts the replication of a mirrored database and waits for it to run.

    It waits for the replication to start, not for the first copy of the
    tables, which can take far longer: read
    ``get_tables_mirroring_status`` for that.

    Args:
        workspace (str): The workspace name or ID.
        mirrored_database (str): The name or ID of the mirrored database.
        timeout (float, optional): How long to wait in all, in seconds.
            Defaults to ten minutes.
        poll_interval (float, optional): How often the status is read, in
            seconds. Defaults to 15.

    Returns:
        (str): ``Running``.

    Raises:
        ResourceNotFoundError: If the workspace or the mirrored database is
            not found.
        RequestError: If the replication cannot be started, or stops on its
            way up.
        TimeoutError: If it does not run within ``timeout``.

    Examples:
        ```python
        start_mirroring_and_wait('Sales-PRD', 'ERP')
        ```
    """
    endpoint = _endpoint(workspace, mirrored_database)
    deadline = time.monotonic() + timeout
    status = _read_status(endpoint)
    if status != MIRRORING_RUNNING and status not in _UNDER_WAY:
        _start(endpoint, mirrored_database)
        logger.info(f"Mirroring of '{mirrored_database}' started.")
    while True:
        status = _read_status(endpoint)
        if status == MIRRORING_RUNNING:
            logger.success(f"Mirrored database '{mirrored_database}' runs.")
            return status
        if status not in _STARTING:
            raise RequestError(
                f"Mirrored database '{mirrored_database}' is {status} after "
                "it was started: check its connection and the access of its "
                "managed identity to the source."
            )
        if time.monotonic() + poll_interval > deadline:
            raise TimeoutError(
                f"Mirrored database '{mirrored_database}' is still {status} "
                f"after {timeout:.0f} seconds."
            )
        logger.info(
            f"Mirrored database '{mirrored_database}' is {status}; waiting."
        )
        time.sleep(poll_interval)


def _endpoint(workspace: str, mirrored_database: str) -> str:
    """The endpoint of a mirrored database, given by name or ID."""
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        raise ResourceNotFoundError(f"Workspace '{workspace}' not found.")
    database_id = _resolve_mirrored_database(workspace_id, mirrored_database)
    return f"/workspaces/{workspace_id}/mirroredDatabases/{database_id}"


def _resolve_mirrored_database(
    workspace_id: str, mirrored_database: str
) -> str:
    """The ID of a mirrored database, given by name or ID."""
    if is_valid_uuid(mirrored_database):
        return mirrored_database
    items = list_items(workspace_id, df=False)
    if items is None:
        raise RequestError(
            f"Could not list the items of workspace '{workspace_id}'."
        )
    for item in items:
        if (
            item["type"] == "MirroredDatabase"
            and item["displayName"] == mirrored_database
        ):
            return str(item["id"])
    raise ResourceNotFoundError(
        f"Mirrored database '{mirrored_database}' not found in workspace "
        f"'{workspace_id}'."
    )


def _read_status(endpoint: str) -> str:
    """The mirroring status at the endpoint of a mirrored database."""
    result = cast(
        ApiResult,
        api_request(
            f"{endpoint}/getMirroringStatus",
            method="post",
            return_result=True,
        ),
    )
    if not result.success:
        raise RequestError(
            f"Could not read the mirroring status at {endpoint}: "
            f"{result.error}"
        )
    return str((result.data or {}).get("status"))


def _start(endpoint: str, mirrored_database: str) -> None:
    """Start the replication at the endpoint of a mirrored database."""
    result = cast(
        ApiResult,
        api_request(
            f"{endpoint}/startMirroring", method="post", return_result=True
        ),
    )
    if not result.success:
        raise RequestError(
            f"Could not start the mirroring of '{mirrored_database}': "
            f"{result.error}"
        )
