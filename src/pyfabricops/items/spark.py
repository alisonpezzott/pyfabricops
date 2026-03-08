from typing import Any, Dict, List, Literal, Optional, Union

from pandas import DataFrame

from ..api.api import api_request
from ..core.workspaces import resolve_workspace
from ..utils.decorators import df
from ..utils.logging import get_logger
from ..utils.utils import is_valid_uuid

logger = get_logger(__name__)


@df
def list_workspace_custom_pools(
    workspace: str, *, df: Optional[bool] = True
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Returns a list of custom pools from the specified workspace.
    This API supports pagination.

    Args:
        workspace (str): The workspace name or ID.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A list of custom pools. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        list_workspace_custom_pools('MyProjectWorkspace')
        list_workspace_custom_pools('MyProjectWorkspace', df=False)
        ```
    """
    workspace_id = resolve_workspace(workspace)
    return api_request(
        endpoint='/workspaces/' + workspace_id + '/spark/pools',
        support_pagination=True,
    )


def get_workspace_custom_pool_id(
    workspace: str, workspace_custom_pool: str
) -> str | None:
    """
    Retrieves the ID of a specific custom pool in the workspace.

    Args:
        workspace (str): The workspace name or ID.
        workspace_custom_pool (str): The name of the workspace custom pool.

    Returns:
        str|None: The ID of the workspace custom pool, or None if not found.

    Examples:
        ```python
        get_workspace_custom_pool_id('MyProjectWorkspace', 'SmallPool')
        get_workspace_custom_pool_id('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    workspace_custom_pools = list_workspace_custom_pools(
        workspace=resolve_workspace(workspace),
        df=False,
    )

    for _workspace_custom_pool in workspace_custom_pools:
        if _workspace_custom_pool['name'] == workspace_custom_pool:
            return _workspace_custom_pool['id']
    logger.warning(
        f"Custom pool '{workspace_custom_pool}' not found in workspace '{workspace}'."
    )
    return None


def resolve_workspace_custom_pool(
    workspace: str,
    workspace_custom_pool: str,
) -> Union[str, None]:
    """
    Resolves a workspace custom pool name to its ID.

    Args:
        workspace (str): The ID of the workspace.
        workspace_custom_pool (str): The name of the workspace custom pool.

    Returns:
        (Union[str, None]): The ID of the workspace custom pool, or None if not found.

    Examples:
        ```python
        resolve_workspace_custom_pool('MyProjectWorkspace', 'MyCustoomPool')
        resolve_workspace_custom_pool('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    if is_valid_uuid(workspace_custom_pool):
        return workspace_custom_pool
    else:
        return get_workspace_custom_pool_id(
            resolve_workspace(workspace), workspace_custom_pool
        )


@df
def get_workspace_custom_pool(
    workspace: str,
    workspace_custom_pool: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Retrieves a specific custom pool from the workspace.

    Args:
        workspace (str): The workspace name or ID.
        workspace_custom_pool (str): The name or ID of the workspace custom pool to retrieve.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The workspace custom pool details as a dictionary or DataFrame, or None if not found.

    Examples:
        ```python
        get_workspace_custom_pool('MyProjectWorkspace', 'MyCustomPool')
        get_workspace_custom_pool('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', df=True)
        ```
    """
    workspace_id = resolve_workspace(workspace)

    workspace_custom_pool_id = resolve_workspace_custom_pool(
        workspace_id, workspace_custom_pool
    )

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/spark/pools/'
        + workspace_custom_pool_id,
    )


@df
def create_workspace_custom_pool(
    workspace: str,
    display_name: Optional[str] = None,
    *,
    auto_scale_enabled: Optional[bool] = None,
    min_node_count: Optional[int] = None,
    max_node_count: Optional[int] = None,
    dynamic_executor_allocation_enabled: Optional[bool] = None,
    min_executors: Optional[int] = None,
    max_executors: Optional[int] = None,
    node_family: Optional[str] = 'MemoryOptimized',
    node_size: Literal['Small', 'Medium', 'Large'] = 'Small',
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Creates the properties of the specified workspace custom pool.

    Args:
        workspace (str): The workspace name or ID.
        workspace_custom_pool (str): The name or ID of the workspace custom pool to update.
        display_name (str, optional): The new display name for the workspace custom pool.
        auto_scale_enabled (bool, optional): Whether auto-scaling is enabled.
        min_node_count (int, optional): The minimum number of nodes.
        max_node_count (int, optional): The maximum number of nodes.
        dynamic_executor_allocation_enabled (bool, optional): Whether dynamic executor allocation is enabled.
        min_executors (int, optional): The minimum number of executors.
        max_executors (int, optional): The maximum number of executors. Always less than max_node_count.
        node_family (str, optional): The node family. Default is 'MemoryOptimized'.
        node_size (Literal['Small', 'Medium', 'Large'], optional): The node size. Default is 'Small'.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The updated workspace custom pool details if successful, otherwise None.

    Examples:
        ```python
        create_workspace_custom_pool(
            'MyProjectWorkspace',
            'MyCustomPool',
            auto_scale_enabled=True,
            min_node_count=1,
            max_node_count=10,
            dynamic_executor_allocation_enabled=True,
            min_executors=1,
            max_executors=9,
            node_family='MemoryOptimized',
            node_size='Small'
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)

    payload = {}

    payload['name'] = display_name

    if auto_scale_enabled is not None:
        payload['autoScale'] = {}
        payload['autoScale']['enabled'] = auto_scale_enabled
    if min_node_count is not None:
        payload['autoScale']['minNodeCount'] = min_node_count
    if max_node_count is not None:
        payload['autoScale']['maxNodeCount'] = max_node_count
    if dynamic_executor_allocation_enabled is not None:
        payload['dynamicExecutorAllocation'] = {}
        payload['dynamicExecutorAllocation'][
            'enabled'
        ] = dynamic_executor_allocation_enabled
    if min_executors is not None:
        payload['dynamicExecutorAllocation']['minExecutors'] = min_executors
    if max_executors is not None:
        payload['dynamicExecutorAllocation']['maxExecutors'] = max_executors
    if node_family:
        payload['nodeFamily'] = node_family
    if node_size:
        payload['nodeSize'] = node_size

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/spark/pools',
        method='post',
        payload=payload,
    )


@df
def update_workspace_custom_pool(
    workspace: str,
    workspace_custom_pool: str,
    *,
    display_name: Optional[str] = None,
    auto_scale_enabled: Optional[bool] = None,
    min_node_count: Optional[int] = None,
    max_node_count: Optional[int] = None,
    dynamic_executor_allocation_enabled: Optional[bool] = None,
    min_executors: Optional[int] = None,
    max_executors: Optional[int] = None,
    node_family: Optional[str] = 'MemoryOptimized',
    node_size: Literal['Small', 'Medium', 'Large'] = 'Small',
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Updates the properties of the specified workspace custom pool.

    Args:
        workspace (str): The workspace name or ID.
        workspace_custom_pool (str): The name or ID of the workspace custom pool to update.
        display_name (str, optional): The new display name for the workspace custom pool.
        auto_scale_enabled (bool, optional): Whether auto-scaling is enabled.
        min_node_count (int, optional): The minimum number of nodes.
        max_node_count (int, optional): The maximum number of nodes.
        dynamic_executor_allocation_enabled (bool, optional): Whether dynamic executor allocation is enabled.
        min_executors (int, optional): The minimum number of executors.
        max_executors (int, optional): The maximum number of executors. Always less than max_node_count.
        node_family (str, optional): The node family. Default is 'MemoryOptimized'.
        node_size (Literal['Small', 'Medium', 'Large'], optional): The node size. Default is 'Small'.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The updated workspace custom pool details if successful, otherwise None.

    Examples:
        ```python
        update_workspace_custom_pool(
            'MyProjectWorkspace',
            'MyCustomPool',
            display_name='MyCustomPoolRenamed',
            auto_scale_enabled=True,
            min_node_count=1,
            max_node_count=10,
            dynamic_executor_allocation_enabled=True,
            min_executors=1,
            max_executors=9, # Always less than max_node_count
            node_family='MemoryOptimized',
            node_size='Small'
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)

    workspace_custom_pool_id = resolve_workspace_custom_pool(
        workspace_id, workspace_custom_pool
    )

    payload = {}

    if display_name:
        payload['name'] = display_name
    if auto_scale_enabled is not None:
        payload['autoScale'] = {}
        payload['autoScale']['enabled'] = auto_scale_enabled
    if min_node_count is not None:
        payload['autoScale']['minNodeCount'] = min_node_count
    if max_node_count is not None:
        payload['autoScale']['maxNodeCount'] = max_node_count
    if dynamic_executor_allocation_enabled is not None:
        payload['dynamicExecutorAllocation'] = {}
        payload['dynamicExecutorAllocation'][
            'enabled'
        ] = dynamic_executor_allocation_enabled
    if min_executors is not None:
        payload['dynamicExecutorAllocation']['minExecutors'] = min_executors
    if max_executors is not None:
        payload['dynamicExecutorAllocation']['maxExecutors'] = max_executors
    if node_family:
        payload['nodeFamily'] = node_family
    if node_size:
        payload['nodeSize'] = node_size

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/spark/pools/'
        + workspace_custom_pool_id,
        method='patch',
        payload=payload,
    )


def delete_workspace_custom_pool(
    workspace: str, workspace_custom_pool: str
) -> None:
    """
    Delete a custom pool from the specified workspace.

    Args:
        workspace (str): The name or ID of the workspace to delete.
        workspace_custom_pool (str): The name or ID of the workspace custom pool to delete.

    Returns:
        None: If the workspace custom pool is successfully deleted.

    Raises:
        ResourceNotFoundError: If the specified workspace is not found.

    Examples:
        ```python
        delete_workspace_custom_pool('MyProjectWorkspace', 'MyCustomPool')
        delete_workspace_custom_pool('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    workspace_custom_pool_id = resolve_workspace_custom_pool(
        workspace_id, workspace_custom_pool
    )

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/spark/pools/'
        + workspace_custom_pool_id,
        method='delete',
    )


@df
def get_workspace_spark_settings(
    workspace: str,
    *,
    df: Optional[bool] = True,
) -> str | None:
    """
    Get workspace Spark settings.

    Args:
        workspace (str): The workspace name or ID.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        str|None: The dict with workspace Spark settings.

    Examples:
        ```python
        get_workspace_spark_settings('MyProjectWorkspace')
        get_workspace_spark_settings('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/spark/settings'
    )


@df
def update_workspace_spark_settings(
    workspace: str,
    *,
    automatic_log_enabled: bool = None,
    high_concurrency_notebook_interactive_run_enabled: bool = None,
    high_concurrency_notebook_pipeline_run_enabled: bool = None,
    pool_customize_compute_enabled: bool = None,
    pool_default_name: str = None,
    pool_default_id: str = None,
    pool_default_type: str = None,
    starter_pool_max_node_count: int = None,
    starter_pool_max_executors: int = None,
    environment_name: str = None,
    environment_runtime_version: str = None,
    job_conservative_job_admission_enabled: bool = None,
    job_session_timeout_in_minutes: int = None,
    df: Optional[bool] = True,
) -> str | None:
    """
    Update workspace Spark settings.

    Args:
        workspace (str): The workspace name or ID.
        automatic_log_enabled (bool, optional): Enable or disable automatic logging.
        high_concurrency_notebook_interactive_run_enabled (bool, optional): Enable or disable high
            concurrency for notebook interactive runs.
        high_concurrency_notebook_pipeline_run_enabled (bool, optional): Enable or disable high
            concurrency for notebook pipeline runs.
        pool_customize_compute_enabled (bool, optional): Enable or disable custom compute for pools.
        pool_default_name (str, optional): The default pool name.
        pool_default_id (str, optional): The default pool ID.
        pool_default_type (str, optional): The default pool type.
        starter_pool_max_node_count (int, optional): The maximum node count for the starter pool
        starter_pool_max_executors (int, optional): The maximum executors for the starter pool.
        environment_name (str, optional): The name of the environment.
        environment_runtime_version (str, optional): The runtime version for the environment.
        job_conservative_job_admission_enabled (bool, optional): Enable or disable conservative job admission
        job_session_timeout_in_minutes (int, optional): The session timeout in minutes for jobs.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        str|None: The dict with updated workspace Spark settings.

    Examples:
        ```python
        update_workspace_spark_settings(
            'MyProjectWorkspace',
            True,
            'mystorageaccount',
            'mysparklogs',
            'logs/'
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)

    payload = {}

    if automatic_log_enabled is not None:
        payload['automaticLog'] = {'enabled': automatic_log_enabled}

    if (high_concurrency_notebook_interactive_run_enabled is not None) or (
        high_concurrency_notebook_pipeline_run_enabled is not None
    ):
        payload['highConcurrency'] = {}
        if high_concurrency_notebook_interactive_run_enabled is not None:
            payload['highConcurrency'][
                'notebookInteractiveRunEnabled'
            ] = high_concurrency_notebook_interactive_run_enabled
        if high_concurrency_notebook_pipeline_run_enabled is not None:
            payload['highConcurrency'][
                'notebookPipelineRunEnabled'
            ] = high_concurrency_notebook_pipeline_run_enabled

    if (
        (pool_customize_compute_enabled is not None)
        or (pool_default_name is not None)
        or (pool_default_id is not None)
        or (pool_default_type is not None)
        or (starter_pool_max_node_count is not None)
        or (starter_pool_max_executors is not None)
    ):
        payload['pool'] = {}
        if pool_customize_compute_enabled is not None:
            payload['pool'][
                'customizeComputeEnabled'
            ] = pool_customize_compute_enabled
        if (
            (pool_default_name is not None)
            or (pool_default_id is not None)
            or (pool_default_type is not None)
        ):
            payload['pool']['defaultPool'] = {}
            if pool_default_name is not None:
                payload['pool']['defaultPool']['name'] = pool_default_name
            if pool_default_id is not None:
                payload['pool']['defaultPool']['id'] = pool_default_id
            if pool_default_type is not None:
                payload['pool']['defaultPool']['type'] = pool_default_type
        if (starter_pool_max_node_count is not None) or (
            starter_pool_max_executors is not None
        ):
            payload['pool']['starterPool'] = {}
            if starter_pool_max_node_count is not None:
                payload['pool']['starterPool'][
                    'maxNodeCount'
                ] = starter_pool_max_node_count
            if starter_pool_max_executors is not None:
                payload['pool']['starterPool'][
                    'maxExecutors'
                ] = starter_pool_max_executors
    if environment_name is not None:
        payload['environment'] = {'name': environment_name}
    if environment_runtime_version is not None:
        payload['environment'] = {
            'runtimeVersion': environment_runtime_version
        }
    if (job_conservative_job_admission_enabled is not None) or (
        job_session_timeout_in_minutes is not None
    ):
        payload['job'] = {}
        if job_conservative_job_admission_enabled is not None:
            payload['job'][
                'conservativeJobAdmissionEnabled'
            ] = job_conservative_job_admission_enabled
        if job_session_timeout_in_minutes is not None:
            payload['job'][
                'sessionTimeoutInMinutes'
            ] = job_session_timeout_in_minutes

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/spark/settings',
        method='patch',
        payload=payload,
    )
