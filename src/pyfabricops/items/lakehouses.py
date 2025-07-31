import time
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
def list_lakehouses(
    workspace: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Returns a list of lakehouses from the specified workspace.
    This API supports pagination.

    Args:
        workspace (str): The workspace name or ID.
        ddf (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A list of lakehouses, excluding those that start with the specified prefixes. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        list_lakehouses('MyProjectWorkspace')
        ```
    """
    return api_request(
        endpoint='/workspaces/' + resolve_workspace(workspace) + '/lakehouses',
        support_pagination=True,
    )


def get_lakehouse_id(workspace: str, lakehouse: str) -> Union[str, None]:
    """
    Retrieves the ID of a lakehouse by its name from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        lakehouse (str): The name of the lakehouse.

    Returns:
        (Union[str, None]): The ID of the lakehouse, or None if not found.

    Examples:
        ```python
        get_lakehouse_id('MyProjectWorkspace', 'SalesDataLakehouse')
        ```
    """
    lakehouses = list_lakehouses(workspace, df=False)
    if not lakehouses:
        return None

    for lakehouse_ in lakehouses:
        if lakehouse_['displayName'] == lakehouse:
            return lakehouse_['id']

    logger.warning(
        f'Lakehouse {lakehouse} not found in workspace {workspace}.'
    )
    return None


def resolve_lakehouse(
    workspace: str,
    lakehouse: str,
) -> Union[str, None]:
    """
    Resolves a lakehouse name to its ID.

    Args:
        workspace (str): The ID of the workspace.
        lakehouse (str): The name of the lakehouse.

    Returns:
        (Union[str, None]): The ID of the lakehouse, or None if not found.

    Examples:
        ```python
        resolve_lakehouse('MyProjectWorkspace', 'SalesDataLakehouse')
        ```
    """
    if is_valid_uuid(lakehouse):
        return lakehouse
    else:
        return get_lakehouse_id(workspace, lakehouse)


@df
def get_lakehouse(
    workspace: str,
    lakehouse: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Retrieves a lakehouse by its name or ID from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        lakehouse (str): The name or ID of the lakehouse.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The lakehouse details if found. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        get_lakehouse('MyProjectWorkspace', 'SalesDataLakehouse')
        get_lakehouse('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        get_lakehouse('123e4567-e89b-12d3-a456-426614174000', 'SalesDataLakehouse', df=True)
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    lakehouse_id = resolve_lakehouse(workspace_id, lakehouse)
    if not lakehouse_id:
        return None

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/lakehouses/' + lakehouse_id,
    )


@df
def create_lakehouse(
    workspace: str,
    display_name: str,
    *,
    description: Optional[str] = None,
    folder: Optional[str] = None,
    enable_schemas: Optional[bool] = False,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Create a lakehouse in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name for the lakehouse.
        description (Optional[str]): The description for the lakehouse.
        folder (Optional[str]): The folder to create the lakehouse in.
        enable_schemas (Optional[bool]): Whether to enable schemas for the lakehouse.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The created lakehouse details if successful, otherwise None.

    Examples:
        ```python
        create_lakehouse('MyProjectWorkspace', 'SalesDataLakehouse')
        create_lakehouse('MyProjectWorkspace', 'SalesDataLakehouse', description='Sales data lakehouse')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    payload = {'displayName': display_name}

    if description:
        payload['description'] = description

    if folder:
        folder_id = resolve_folder(workspace_id, folder)
        if folder_id:
            payload['folderId'] = folder_id

    if enable_schemas:
        payload['creationPayload'] = {'enableSchemas': True}

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/lakehouses',
        method='post',
        payload=payload,
    )


@df
def update_lakehouse(
    workspace: str,
    lakehouse: str,
    *,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Updates the properties of the specified lakehouse.

    Args:
        workspace (str): The workspace name or ID.
        lakehouse (str): The name or ID of the lakehouse to update.
        display_name (Optional[str]): The new display name for the lakehouse.
        description (Optional[str]): The new description for the lakehouse.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The updated lakehouse details if successful, otherwise None.

    Examples:
        ```python
        update_lakehouse('MyProjectWorkspace', 'SalesDataLakehouse', display_name='UpdatedSalesDataLakehouse')
        update_lakehouse('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', description='Updated description')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    lakehouse_id = resolve_lakehouse(workspace_id, lakehouse)

    payload = {}

    if display_name:
        payload['displayName'] = display_name

    if description:
        payload['description'] = description

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/lakehouses/' + lakehouse_id,
        method='patch',
        payload=payload,
    )


def delete_lakehouse(workspace: str, lakehouse: str) -> None:
    """
    Delete a lakehouse in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        lakehouse (str): The name or ID of the lakehouse to delete.

    Returns:
        (bool): True if the lakehouse was deleted successfully, otherwise False.

    Examples:
        ```python
        delete_lakehouse('MyProjectWorkspace', 'SalesDataLakehouse')
        delete_lakehouse('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    lakehouse_id = resolve_lakehouse(workspace_id, lakehouse)
    return api_request(
        endpoint='/workspaces/' + workspace_id + '/lakehouses/' + lakehouse_id,
        method='delete',
    )
