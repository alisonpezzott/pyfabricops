from typing import Any, Dict, List, Literal, Optional, Union

from pandas import DataFrame

from ..api.api import api_request
from ..core.folders import resolve_folder
from ..core.workspaces import resolve_workspace
from ..utils.decorators import df
from ..utils.logging import get_logger
from ..utils.utils import is_valid_uuid

logger = get_logger(__name__)


@df
def list_dataflows_gen1(
    workspace: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Returns a list of Gen1 dataflows in a specified workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A list of Gen1 dataflows or a DataFrame if df is True.
    """
    return api_request(
        endpoint='/groups/' + resolve_workspace(workspace) + '/dataflows',
        audience='powerbi',
        method='get',
        support_pagination=True,
    )


def get_dataflow_gen1_id(
    workspace: str, dataflow_name: str
) -> Union[str, None]:
    """
    Retrieves the ID of a Gen1 dataflow by its name.

    Args:
        dataflow_name (str): The name of the dataflow.

    Returns:
        str | None: The ID of the dataflow if found, otherwise None.
    """
    dataflows = list_dataflows_gen1(
        workspace=resolve_workspace(workspace),
        df=False,
    )
    for _dataflow in dataflows:
        if _dataflow['displayName'] == dataflow_name:
            return _dataflow['id']
    logger.warning(
        f"Dataflow '{dataflow_name}' not found in workspace '{workspace}'."
    )
    return None


def resolve_dataflow_gen1(workspace: str, dataflow: str) -> Union[str, None]:
    """
    Resolves a dataflow name to its ID.

    Args:
        workspace (str): The name or ID of the workspace.
        dataflow (str): The name or ID of the dataflow.

    Returns:
        str | None: The ID of the dataflow if found, otherwise None.
    """
    if is_valid_uuid(dataflow):
        return dataflow
    else:
        return get_dataflow_gen1_id(workspace, dataflow)


@df
def get_dataflow_gen1(
    workspace: str,
    dataflow: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Get a Power BI dataflow.

    Args:
        workspace (str): The workspace name or ID.
        dataflow (str): The name of the dataflow.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The dataflow.

    Examples:
        ```python
        get_dataflow_gen1('MyProjectWorkspace', 'SalesDataflowGen1')
        get_dataflow_gen1('123e4567-e89b-12d3-a456-426614174000', 'SalesDataflowGen1')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    return api_request(
        endpoint='/groups/'
        + workspace_id
        + '/dataflows/'
        + resolve_dataflow_gen1(workspace_id, dataflow),
        method='get',
        audience='powerbi',
    )


def get_dataflow_gen1_definition(workspace: str, dataflow: str) -> dict | None:
    """
    Get the definition of a Power BI dataflow Gen1.

    Args:
        workspace (str): The workspace name or ID.
        dataflow (str): The dataflow name or ID.

    Returns:
        dict: The dataflow definition.

    Examples:
        ```python
        get_dataflow_gen1_definition('MyProjectWorkspace', 'SalesDataflowGen1')
        get_dataflow_gen1_definition('123e4567-e89b-12d3-a456-426614174000', 'SalesDataflowGen1')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    dataflow_id = resolve_dataflow_gen1(workspace_id, dataflow)

    return api_request(
        endpoint='/groups/'
        + workspace_id
        + '/dataflows/'
        + dataflow_id
        + '/getDefinition',
        method='post',
        support_lro=True,
        audience='powerbi',
    )


@df
def update_dataflow_gen1_definition(
    workspace: str, dataflow: str, item_definition: Dict[str, Any]
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Updates the definition of an existing dataflow in the specified workspace.
    If the dataflow does not exist, it returns None.

    Args:
        workspace (str): The workspace name or ID.
        dataflow (str): The name or ID of the dataflow to update.
        item_definition (Dict[str, Any]): The item_definition of the dataflow.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The updated dataflow details if successful, otherwise None.

    Examples:
        ```python
        update_dataflow_gen1_definition(
            workspace='MyProjectWorkspace',
            dataflow='SalesDataflowGen1',
            item_definition={...} # The definition of the dataflow
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)

    dataflow_id = resolve_dataflow_gen1(workspace_id, dataflow)

    params = {'updateMetadata': True}
    payload = {'definition': item_definition}

    return api_request(
        endpoint='/groups/' + workspace_id + '/dataflows/' + dataflow_id,
        method='patch',
        payload=payload,
        params=params,
        audience='powerbi',
    )


@df
def create_dataflow_gen1(
    workspace: str,
    display_name: str,
    item_definition: Dict[str, Any],
    *,
    description: Optional[str] = None,
    folder: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
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
        (Union[DataFrame, Dict[str, Any], None]): The created dataflow details.

    Examples:
        ```python
        create_dataflow_gen1(
            workspace='MyProjectWorkspace',
            display_name='SalesDataflowGen1',
            item_definition={...},
            description='This is a sales dataflow',
            folder='SalesDataflowsFolder'
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)

    payload = {
        'displayName': display_name,
        'definition': item_definition,
    }

    if folder:
        folder_id = resolve_folder(workspace_id, folder)
        if folder_id:
            payload['folderId'] = folder_id

    if description:
        payload['description'] = description

    return api_request(
        endpoint='/groups/' + workspace_id + '/dataflows',
        method='post',
        payload=payload,
        audience='powerbi',
    )


@df
def update_dataflow_gen1(
    workspace: str,
    dataflow: str,
    *,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Updates the properties of the specified dataflow.

    Args:
        workspace (str): The workspace name or ID.
        dataflow (str): The name or ID of the dataflow to update.
        display_name (str, optional): The new display name for the dataflow.
        description (str, optional): The new description for the dataflow.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The updated dataflow details if successful, otherwise None.

    Examples:
        ```python
        update_dataflow_gen1('MyProjectWorkspace', 'SalesDataflowGen1', display_name='UpdatedSalesDataflowGen1')
        update_dataflow_gen1('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', description='Updated description')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    dataflow_id = resolve_dataflow_gen1(workspace_id, dataflow)

    payload = {}

    if display_name:
        payload['displayName'] = display_name

    if description:
        payload['description'] = description

    return api_request(
        endpoint='/groups/' + workspace_id + '/dataflows/' + dataflow_id,
        method='patch',
        payload=payload,
        audience='powerbi',
    )


def delete_dataflow_gen1(workspace: str, dataflow: str) -> None:
    """
    Deletes a dataflow from the specified workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        dataflow (str): The name or ID of the dataflow to delete.

    Returns:
        None: If the dataflow is successfully deleted.

    Examples:
        ```python
        delete_dataflow_gen1('MyProjectWorkspace', 'SalesDataflowGen1')
        delete_dataflow_gen1('123e4567-e89b-12d3-a456-426614174000', 'SalesDataflowGen1')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    dataflow_id = resolve_dataflow_gen1(workspace_id, dataflow)

    return api_request(
        endpoint='/groups/' + workspace_id + '/dataflows/' + dataflow_id,
        method='delete',
        audience='powerbi',
    )


def takeover_dataflow_gen1(workspace: str, dataflow: str) -> Union[bool, None]:
    """
    Take over a dataflow in a workspace

    Args:
        workspace (str): The workspace name or ID.
        dataflow (str): The dataflow name or ID.

    Examples:
        ```python
        takeover_dataflow_gen1('MyProjectWorkspace', 'SalesDataflowGen1')
        takeover_dataflow_gen1('123e4567-e89b-12d3-a456-426614174000', 'SalesDataflowGen1')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    dataflow_id = resolve_dataflow_gen1(workspace_id, dataflow)

    return api_request(
        endpoint='/groups/'
        + workspace_id
        + '/dataflows/'
        + dataflow_id
        + '/Default.Takeover',
        method='post',
        support_lro=True,
    )


def refresh_dataflow_gen1(
    workspace: str,
    dataflow: str,
    *,
    process_type: Optional[str] = 'default',
    notify_option: Literal[
        'MailOnFailure', 'NoNotification'
    ] = 'NoNotification',
) -> None:
    """
    Refresh a dataflow in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        dataflow (str): The name or ID of the dataflow to refresh.
        process_type (str, optional): The process type to use for the refresh. Defaults to 'default'.
        notify_option (Literal['MailOnFailure', 'NoNotification'], optional): The notification option to use for the refresh. Defaults to 'NoNotification'.

    Returns:
        None: If the refresh was successful.

    Examples:
        ```python
        refresh_dataflow_gen1('MyProjectWorkspace', 'SalesDataflow')
        refresh_dataflow_gen1('123e4567-e89b-12d3-a456-426614174000', 'SalesDataflow')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    dataflow_id = resolve_dataflow_gen1(workspace_id, dataflow)

    payload = {'notifyOption': notify_option}

    params = {'processType': process_type}

    return api_request(
        endpoint='/groups/'
        + workspace_id
        + '/dataflows/'
        + dataflow_id
        + '/refreshes',
        method='post',
        payload=payload,
        params=params,
        audience='powerbi',
    )


@df
def get_dataflow_gen1_transactions(
    workspace: str,
    dataflow: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Get transactions for a dataflow in a workspace.

    Args:
        workspace (str): The workspace name or ID.
        dataflow (str): The dataflow name or ID.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        Union[DataFrame, List[Dict[str, Any]], None]: The dataflow transactions or None if not found.

    Examples:
        ```python
        get_dataflow_gen1_transactions('MyProjectWorkspace', 'SalesDataflowGen1')
        get_dataflow_gen1_transactions('123e4567-e89b-12d3-a456-426614174000', 'SalesDataflowGen1')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    dataflow_id = resolve_dataflow_gen1(workspace_id, dataflow)

    return api_request(
        endpoint='/groups/'
        + workspace_id
        + '/dataflows/'
        + dataflow_id
        + '/transactions',
        method='post',
        audience='powerbi',
    )


@df
def get_dataflows_gen1_datasources(
    workspace: str,
    dataflow: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Get the data sources for a dataflow in a workspace.

    Args:
        workspace (str): The workspace name or ID.
        dataflow (str): The dataflow name or ID.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        Union[DataFrame, List[Dict[str, Any]], None]: The dataflow datasources or None if not found.

    Examples:
        ```python
        get_dataflows_gen1_datasources('MyProjectWorkspace', 'SalesDataflowGen1')
        get_dataflows_gen1_datasources('123e4567-e89b-12d3-a456-426614174000', 'SalesDataflowGen1')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    dataflow_id = resolve_dataflow_gen1(workspace_id, dataflow)

    return api_request(
        endpoint='/groups/'
        + workspace_id
        + '/dataflows/'
        + dataflow_id
        + '/datasources',
        method='post',
        audience='powerbi',
    )
