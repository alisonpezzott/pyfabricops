from typing import Any, Dict, List, Optional, Union

from pandas import DataFrame

from ..api.api import api_request
from ..core.folders import resolve_folder
from ..core.workspaces import resolve_workspace
from ..utils.decorators import df
from ..utils.logging import get_logger
from ..utils.utils import is_valid_uuid

logger = get_logger(__name__)


@df
def list_dataflows_gen2(
    workspace: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Lists all dataflows in a workspace.

    Args:
        workspace (str): The workspace name or ID.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        list | pandas.DataFrame | None: A list of dataflows if successful, otherwise None.
    """
    workspace_id = resolve_workspace(workspace)

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/dataflows',
        support_pagination=True,
    )


def get_dataflow_gen2_id(
    workspace: str, dataflow_gen2_name: str
) -> Union[str, None]:
    """
    Retrieves the ID of a dataflow by its name.

    Args:
        dataflow_gen2_name (str): The name of the dataflow.

    Returns:
        (Union[str, None]): The ID of the dataflow if found, otherwise None.
    """
    dataflows = list_dataflows_gen2(
        workspace=resolve_workspace(workspace),
        df=False,
    )

    for _dataflow in dataflows:
        if _dataflow['displayName'] == dataflow_gen2_name:
            return _dataflow['id']
    logger.warning(
        f"Dataflow '{dataflow_gen2_name}' not found in workspace '{workspace}'."
    )
    return None


def resolve_dataflow_gen2(
    workspace: str,
    dataflow: str,
) -> Union[str, None]:
    """
    Resolves a dataflow name to its ID.

    Args:
        workspace (str): The ID of the workspace.
        dataflow (str): The name of the dataflow.

    Returns:
        (Union[str, None]): The ID of the dataflow, or None if not found.

    Examples:
        ```python
        resolve_dataflow('MyProjectWorkspace', 'SalesDataflow')
        resolve_dataflow('123e4567-e89b-12d3-a456-426614174000', 'SalesDataflow')
        ```
    """
    if is_valid_uuid(dataflow):
        return dataflow
    else:
        return get_dataflow_gen2_id(resolve_workspace(workspace), dataflow)


@df
def get_dataflow_gen2(
    workspace: str,
    dataflow: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Gets a dataflow by its name or ID.

    Args:
        workspace (str): The workspace name or ID.
        dataflow (str): The name or ID of the dataflow.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The dataflow details if found, otherwise None.

    Examples:
        ```python
        get_dataflow('MyProjectWorkspace', 'SalesDataflow')
        get_dataflow('123e4567-e89b-12d3-a456-426614174000', 'SalesDataflow')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    dataflow_id = resolve_dataflow_gen2(workspace_id, dataflow)

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/dataflows/' + dataflow_id,
    )


@df
def update_dataflow_gen2(
    workspace: str,
    dataflow: str,
    *,
    display_name: str = None,
    description: str = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Updates the properties of the specified dataflow.

    Args:
        workspace (str): The workspace name or ID.
        dataflow (str): The name or ID of the dataflow to update.
        display_name (str, optional): The new display name for the dataflow.
        description (str, optional): The new description for the dataflow.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The updated dataflow details if successful, otherwise None.

    Examples:
        ```python
        update_dataflow('MyProjectWorkspace', 'SalesDataModel', display_name='UpdatedSalesDataModel')
        update_dataflow('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', description='Updated description')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    dataflow_id = resolve_dataflow_gen2(workspace_id, dataflow)

    payload = {}

    if display_name:
        payload['displayName'] = display_name

    if description:
        payload['description'] = description

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/dataflows/' + dataflow_id,
        method='patch',
        payload=payload,
    )


def delete_dataflow_gen2(workspace: str, dataflow: str) -> None:
    """
    Delete a dataflow from the specified workspace.

    Args:
        workspace (str): The name or ID of the workspace to delete.
        dataflow (str): The name or ID of the dataflow to delete.

    Returns:
        None: If the dataflow is successfully deleted.

    Raises:
        ResourceNotFoundError: If the specified workspace is not found.

    Examples:
        ```python
        delete_dataflow('MyProjectWorkspace', 'SalesDataflow')
        delete_dataflow('123e4567-e89b-12d3-a456-426614174000', 'SalesDataflow')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    dataflow_id = resolve_dataflow_gen2(workspace_id, dataflow)

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/dataflows/' + dataflow_id,
        method='delete',
    )


def get_dataflow_gen2_definition(
    workspace: str, dataflow: str
) -> Union[Dict[str, Any], None]:
    """
    Retrieves the definition of a dataflow by its name or ID from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        dataflow (str): The name or ID of the dataflow.

    Returns:
        (Union[Dict[str, Any], None]): The dataflow definition if found, otherwise None.

    Examples:
        ```python
        get_dataflow_definition('MyProjectWorkspace', 'Salesdataflow')
        get_dataflow_definition('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    # Resolving IDs
    workspace_id = resolve_workspace(workspace)

    dataflow_id = resolve_dataflow_gen2(workspace_id, dataflow)

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/dataflows/'
        + dataflow_id
        + '/getDefinition',
        method='post',
        support_lro=True,
    )


@df
def update_dataflow_gen2_definition(
    workspace: str,
    dataflow: str,
    item_definition: Dict[str, Any],
    df: Optional[bool] = True,
) -> Union[Dict[str, Any], None]:
    """
    Updates the definition of an existing dataflow in the specified workspace.
    If the dataflow does not exist, it returns None.

    Args:
        workspace (str): The workspace name or ID.
        dataflow (str): The name or ID of the dataflow to update.
        item_definition (Dict[str, Any]): The updated item definition.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[Dict[str, Any], None]): The updated dataflow details if successful, otherwise None.

    Examples:
        ```python
        update_dataflow('MyProjectWorkspace', 'SalesDataModel', display_name='UpdatedSalesDataModel')
        update_dataflow('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', description='Updated description')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    dataflow_id = resolve_dataflow_gen2(workspace_id, dataflow)

    payload = {'definition': item_definition}

    params = {'updateMetadata': True}

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/dataflows/'
        + dataflow_id
        + '/updateDefinition',
        method='patch',
        payload=payload,
        params=params,
        support_lro=True,
    )


@df
def create_dataflow_gen2(
    workspace: str,
    display_name: str,
    item_definition: Dict[str, Any],
    *,
    description: Optional[str] = None,
    folder: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[dict, None]:
    """
    Creates a new dataflow in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name of the dataflow.
        description (str, optional): A description for the dataflow.
        folder (str, optional): The folder to create the dataflow in.
        item_definition (Dict[str, Any]): The definition of the dataflow.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (dict): The created dataflow details.

    Examples:
        ```python
        create_dataflow('MyProjectWorkspace', 'SalesDataModel', 'path/to/definition.json')
        create_dataflow('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', 'path/to/definition.json', description='Sales data model')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    payload = {'displayName': display_name, 'definition': item_definition}

    if description:
        payload['description'] = description

    if folder:
        folder_id = resolve_folder(workspace_id, folder)
        if folder_id:
            payload['folderId'] = folder_id

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/dataflows',
        method='post',
        payload=payload,
        support_lro=True,
    )
