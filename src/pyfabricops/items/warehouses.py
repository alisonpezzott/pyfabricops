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
def list_warehouses(
    workspace: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Returns a list of warehouses from the specified workspace.
    This API supports pagination.

    Args:
        workspace (str): The workspace name or ID.
        ddf (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A list of warehouses, excluding those that start with the specified prefixes. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        list_warehouses('MyProjectWorkspace')
        ```
    """
    return api_request(
        endpoint='/workspaces/' + resolve_workspace(workspace) + '/warehouses',
        support_pagination=True,
    )


def get_warehouse_id(workspace: str, warehouse: str) -> Union[str, None]:
    """
    Retrieves the ID of a warehouse by its name from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        warehouse (str): The name of the warehouse.

    Returns:
        (Union[str, None]): The ID of the warehouse, or None if not found.

    Examples:
        ```python
        get_warehouse_id('MyProjectWorkspace', 'SalesDatawarehouse')
        ```
    """
    warehouses = list_warehouses(workspace, df=False)
    if not warehouses:
        return None

    for warehouse_ in warehouses:
        if warehouse_['displayName'] == warehouse:
            return warehouse_['id']
    return None


def resolve_warehouse(
    workspace: str,
    warehouse: str,
) -> Union[str, None]:
    """
    Resolves a warehouse name to its ID.

    Args:
        workspace (str): The ID of the workspace.
        warehouse (str): The name of the warehouse.

    Returns:
        (Union[str, None]): The ID of the warehouse, or None if not found.

    Examples:
        ```python
        resolve_warehouse('MyProjectWorkspace', 'SalesDatawarehouse')
        ```
    """
    if is_valid_uuid(warehouse):
        return warehouse
    else:
        return get_warehouse_id(workspace, warehouse)


@df
def get_warehouse(
    workspace: str,
    warehouse: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Retrieves a warehouse by its name or ID from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        warehouse (str): The name or ID of the warehouse.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The warehouse details if found. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        get_warehouse('MyProjectWorkspace', 'SalesDatawarehouse')
        get_warehouse('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        get_warehouse('123e4567-e89b-12d3-a456-426614174000', 'SalesDatawarehouse', df=True)
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    warehouse_id = resolve_warehouse(workspace_id, warehouse)
    if not warehouse_id:
        return None

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/warehouses/' + warehouse_id,
    )


@df
def create_warehouse(
    workspace: str,
    display_name: str,
    *,
    description: Optional[str] = None,
    folder: Optional[str] = None,
    enable_schemas: Optional[bool] = False,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Create a warehouse in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name for the warehouse.
        description (Optional[str]): The description for the warehouse.
        folder (Optional[str]): The folder to create the warehouse in.
        enable_schemas (Optional[bool]): Whether to enable schemas for the warehouse.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The created warehouse details if successful, otherwise None.

    Examples:
        ```python
        create_warehouse('MyProjectWorkspace', 'SalesDatawarehouse')
        create_warehouse('MyProjectWorkspace', 'SalesDatawarehouse', description='Sales data warehouse')
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
        endpoint='/workspaces/' + workspace_id + '/warehouses',
        method='post',
        payload=payload,
        support_lro=True,
    )


@df
def update_warehouse(
    workspace: str,
    warehouse: str,
    *,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Updates the properties of the specified warehouse.

    Args:
        workspace (str): The workspace name or ID.
        warehouse (str): The name or ID of the warehouse to update.
        display_name (Optional[str]): The new display name for the warehouse.
        description (Optional[str]): The new description for the warehouse.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The updated warehouse details if successful, otherwise None.

    Examples:
        ```python
        update_warehouse('MyProjectWorkspace', 'SalesDatawarehouse', display_name='UpdatedSalesDatawarehouse')
        update_warehouse('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', description='Updated description')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    warehouse_id = resolve_warehouse(workspace_id, warehouse)

    payload = {}

    if display_name:
        payload['displayName'] = display_name

    if description:
        payload['description'] = description

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/warehouses/' + warehouse_id,
        method='patch',
        payload=payload,
    )


def delete_warehouse(workspace: str, warehouse: str) -> None:
    """
    Delete a warehouse in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        warehouse (str): The name or ID of the warehouse to delete.

    Returns:
        (bool): True if the warehouse was deleted successfully, otherwise False.

    Examples:
        ```python
        delete_warehouse('MyProjectWorkspace', 'SalesDatawarehouse')
        delete_warehouse('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    warehouse_id = resolve_warehouse(workspace_id, warehouse)
    return api_request(
        endpoint='/workspaces/' + workspace_id + '/warehouses/' + warehouse_id,
        method='delete',
    )
