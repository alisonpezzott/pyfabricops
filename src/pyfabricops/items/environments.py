from typing import Any, Dict, List, Literal, Optional, Union

from pandas import DataFrame
from requests import get

from ..api.api import api_request
from ..core.folders import resolve_folder
from ..core.workspaces import resolve_workspace
from ..items.spark import get_workspace_custom_pool
from ..utils.decorators import df
from ..utils.logging import get_logger
from ..utils.utils import is_valid_uuid

logger = get_logger(__name__)


@df
def list_environments(
    workspace: str, *, df: Optional[bool] = True
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Returns a list of environments from the specified workspace.
    This API supports pagination.

    Args:
        workspace (str): The workspace name or ID.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A list of environments, excluding those that start with the specified prefixes. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        list_environments('MyProjectWorkspace')
        list_environments('MyProjectWorkspace', df=False)
        ```
    """
    workspace_id = resolve_workspace(workspace)
    return api_request(
        endpoint='/workspaces/' + workspace_id + '/environments',
        support_pagination=True,
    )


def get_environment_id(workspace: str, environment: str) -> str | None:
    """
    Retrieves the ID of a specific environment in the workspace.

    Args:
        workspace (str): The workspace name or ID.
        environment (str): The name of the environment.

    Returns:
        str|None: The ID of the environment, or None if not found.

    Examples:
        ```python
        get_environment_id('MyProjectWorkspace', 'MyEnvironment')
        get_environment_id('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    environments = list_environments(
        workspace=resolve_workspace(workspace),
        df=False,
    )

    for _environment in environments:
        if _environment['displayName'] == environment:
            return _environment['id']
    logger.warning(
        f"environment '{environment}' not found in workspace '{workspace}'."
    )
    return None


def resolve_environment(
    workspace: str,
    environment: str,
) -> Union[str, None]:
    """
    Resolves a environment name to its ID.

    Args:
        workspace (str): The ID of the workspace.
        environment (str): The name of the environment.

    Returns:
        (Union[str, None]): The ID of the environment, or None if not found.

    Examples:
        ```python
        resolve_environment('MyProjectWorkspace', 'MyEnvironment')
        resolve_environment('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    if is_valid_uuid(environment):
        return environment
    else:
        return get_environment_id(resolve_workspace(workspace), environment)


@df
def get_environment(
    workspace: str,
    environment: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Retrieves a specific environment from the workspace.

    Args:
        workspace (str): The workspace name or ID.
        environment (str): The name or ID of the environment to retrieve.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The environment details as a dictionary or DataFrame, or None if not found.

    Examples:
        ```python
        get_environment('MyProjectWorkspace', 'MyEnvironment')
        get_environment('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', df=True)
        ```
    """
    workspace_id = resolve_workspace(workspace)

    environment_id = resolve_environment(workspace_id, environment)

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/environments/'
        + environment_id,
    )


@df
def update_environment(
    workspace: str,
    environment: str,
    *,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Updates the properties of the specified environment.

    Args:
        workspace (str): The workspace name or ID.
        environment (str): The name or ID of the environment to update.
        display_name (str, optional): The new display name for the environment.
        description (str, optional): The new description for the environment.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The updated environment details if successful, otherwise None.

    Examples:
        ```python
        update_environment('MyProjectWorkspace', 'MyEnvironment', display_name='UpdatedMyEnvironment')
        update_environment('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', description='Updated description')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    environment_id = resolve_environment(workspace_id, environment)

    payload = {}

    if display_name:
        payload['displayName'] = display_name

    if description:
        payload['description'] = description

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/environments/'
        + environment_id,
        method='patch',
        payload=payload,
    )


def delete_environment(workspace: str, environment: str) -> None:
    """
    Delete a environment from the specified workspace.

    Args:
        workspace (str): The name or ID of the workspace to delete.
        environment (str): The name or ID of the environment to delete.

    Returns:
        None: If the environment is successfully deleted.

    Raises:
        ResourceNotFoundError: If the specified workspace is not found.

    Examples:
        ```python
        delete_environment('MyProjectWorkspace', 'MyEnvironment')
        delete_environment('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    environment_id = resolve_environment(workspace_id, environment)

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/environments/'
        + environment_id,
        method='delete',
    )


def get_environment_definition(
    workspace: str, environment: str
) -> Union[Dict[str, Any], None]:
    """
    Retrieves the definition of a environment by its name or ID from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        environment (str): The name or ID of the environment.

    Returns:
        (Union[Dict[str, Any], None]): The environment definition if found, otherwise None.

    Examples:
        ```python
        get_environment_definition('MyProjectWorkspace', 'MyEnvironment')
        get_environment_definition('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    environment_id = resolve_environment(workspace_id, environment)

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/environments/'
        + environment_id
        + '/getDefinition',
        method='post',
        support_lro=True,
    )


@df
def update_environment_definition(
    workspace: str,
    environment: str,
    environment_definition: Dict[str, Any],
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Updates the definition of an existing environment in the specified workspace.
    If the environment does not exist, it returns None.

    Args:
        workspace (str): The workspace name or ID.
        environment (str): The name or ID of the environment to update.
        environment_definition (Dict[str, Any]): The updated environment definition.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The updated environment details if successful, otherwise None.

    Examples:
        ```python
        update_environment_definition(
            'MyProjectWorkspace',
            'MyEnvironment',
            environment_definition = {...}  # Updated environment definition
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)

    environment_id = resolve_environment(workspace_id, environment)

    payload = {'definition': environment_definition}

    params = {'updateMetadata': True}

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/environments/'
        + environment_id
        + '/updateDefinition',
        payload=payload,
        params=params,
        support_lro=True,
    )


@df
def create_environment(
    workspace: str,
    display_name: str,
    *,
    environment_definition: Dict[str, Any] = None,
    description: Optional[str] = None,
    folder: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Creates a new environment in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name of the environment.
        environment_definition (Dict[str, Any]): The environment definition. If Not provided, an empty definition will be used.
        description (str, optional): A description for the environment.
        folder (str, optional): The folder to create the environment in.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The created environment details.

    Examples:
        ```python
        create_environment(
            'MyProjectWorkspace', 'MyEnvironment', environment_definition={...}
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)

    payload = {
        'displayName': display_name,
        'definition': environment_definition,
    }

    if description:
        payload['description'] = description

    if folder:
        folder_id = resolve_folder(workspace_id, folder)
        if folder_id:
            payload['folderId'] = folder_id

    if environment_definition:
        payload['definition'] = environment_definition

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/environments',
        method='post',
        payload=payload,
        support_lro=True,
    )


@df
def publish_environment(
    workspace: str,
    environment: str,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Trigger an environment publish operation.

    Args:
        workspace (str): The workspace name or ID.
        environment (str): The name or ID of the environment to publish.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The published environment details if successful, otherwise None.

    Examples:
        ```python
        publish_environment(
            'MyProjectWorkspace',
            'MyEnvironment'
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)

    environment_id = resolve_environment(workspace_id, environment)

    params = {'beta': False}

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/environments/'
        + environment_id
        + '/staging/publish',
        method='post',
        params=params,
        support_lro=True,
    )


@df
def get_environment_spark_compute(
    workspace: str, environment: str
) -> Union[Dict[str, Any], None]:
    """
    Get environment staging spark compute.

    Args:
        workspace (str): The workspace name or ID.
        environment (str): The name or ID of the environment.

    Returns:
        (Union[Dict[str, Any], None]): The environment definition if found, otherwise None.

    Examples:
        ```python
        get_environment_spark_compute('MyProjectWorkspace', 'MyEnvironment')
        get_environment_spark_compute('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    environment_id = resolve_environment(workspace_id, environment)

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/environments/'
        + environment_id
        + '/staging/sparkcompute',
        params={'beta': False},
    )


@df
def update_environment_spark_compute(
    workspace: str,
    environment: str,
    *,
    pool: str = None,
    driver_cores: Literal[4, 8] = None,
    driver_memory: Literal['28g', '56g'] = None,
    executor_cores: Literal[4, 8] = None,
    executor_memory: Literal['28g', '56g'] = None,
    dynamic_executor_allocation_enabled: bool = None,
    min_executors: int = None,
    max_executors: int = None,
    spark_properties: List[Dict[str, str]] = None,
    runtime_version: Literal['1.2', '1.3', '2.0'] = None,
) -> Union[Dict[str, Any], None]:
    """
    Update environment staging spark compute.

    Args:
        workspace (str): The workspace name or ID.
        environment (str): The name or ID of the environment.

    Returns:
        (Union[Dict[str, Any], None]): The environment definition if found, otherwise None.

    Examples:
        ```python
        update_environment_spark_compute(
            'MyProjectWorkspace',
            'MyEnvironment',
            pool='Custom Pool Name',
        )
        update_environment_spark_compute(
            'MyProjectWorkspace',
            'MyEnvironment',
            pool='Custom Pool Name',
            driver_cores=8,
            driver_memory='56g',
            executor_cores=8,
            executor_memory='56g',
            dynamic_executor_allocation_enabled=True,
            min_executors=1,
            max_executors=9,
            spark_properties=[
                {"key": "spark.sql.caseSensitive", "value": "true"}
            ],
            runtime_version='1.3'
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)

    environment_id = resolve_environment(workspace_id, environment)

    if pool:
        _pool = get_workspace_custom_pool(workspace_id, pool, df=False)
        if not _pool:
            return None
        pool_name = _pool['name']
        pool_id = _pool['id']
    else:
        pool_name = 'Starter Pool'
        pool_id = '00000000-0000-0000-0000-000000000000'

    payload = {
        'instancePool': {'name': pool_name, 'type': 'Workspace', 'id': pool_id}
    }

    if driver_cores is not None:
        payload['driverCores'] = driver_cores

    if driver_memory is not None:
        payload['driverMemory'] = driver_memory

    if executor_cores is not None:
        payload['executorCores'] = executor_cores

    if executor_memory is not None:
        payload['executorMemory'] = executor_memory

    if dynamic_executor_allocation_enabled is not None:
        payload['dynamicExecutorAllocation'] = {
            'enabled': dynamic_executor_allocation_enabled,
            'minExecutors': min_executors,
            'maxExecutors': max_executors,
        }

    if spark_properties is not None:
        payload['sparkProperties'] = spark_properties
    if runtime_version is not None:
        payload['runtimeVersion'] = runtime_version

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/environments/'
        + environment_id
        + '/staging/sparkcompute',
        params={'beta': False},
        method='patch',
        payload=payload,
    )
