import os

import pandas

from ..api.api import _api_request, _lro_handler, _pagination_handler
from ..utils.decorators import df
from .fabric_items import _FABRIC_ITEMS
from ..core.folders import resolve_folder
from ..utils.logging import get_logger
from ..utils.utils import (
    get_current_branch,
    get_workspace_suffix,
    is_valid_uuid,
    pack_item_definition,
    read_json,
    unpack_item_definition,
    write_json,
)
from ..core.workspaces import (
    _resolve_workspace_path,
    get_workspace,
    resolve_workspace,
)

logger = get_logger(__name__)


@df
def list_items(
    workspace: str, *, excluded_starts: tuple = ('Staging'), df: bool = False
) -> list | pandas.DataFrame:
    """
    Returns a list of items from the specified workspace.
    This API supports pagination.

    Args:
        workspace (str): The workspace name or ID.
        excluded_starts (tuple): A tuple of prefixes to exclude from the list.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (list|pandas.DataFrame): A list of items, excluding those that start with the specified prefixes. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        list_items('MyProjectWorkspace')
        list_items('MyProjectWorkspace', excluded_starts=('Staging', 'ware'))
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    response = _api_request(endpoint=f'/workspaces/{workspace_id}/items')
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        response = _pagination_handler(response)
    items = [
        item
        for item in response.data.get('value', [])
        if not item['displayName'].startswith(excluded_starts)
    ]
    if not items:
        logger.warning(f"No valid items found in workspace '{workspace}'.")
        return None
    else:
        return items


def resolve_item(
    workspace: str, item: str, *, silent: bool = False
) -> str | None:
    """
    Resolves a item name to its ID.

    Args:
        workspace (str): The ID of the workspace.
        item (str): The name of the item.
        silent (bool): If True, suppresses warnings. Defaults to False.

    Returns:
        str|None: The ID of the item, or None if not found.

    Examples:
        ```python
        resolve_item('MyProjectWorkspace', 'SalesDataModel')
        resolve_item('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    if is_valid_uuid(item):
        return item

    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    items = list_items(workspace, df=False)
    if not items:
        return None

    name = item.split('.')[0]
    type = item.split('.')[-1]
    if not name or not type:
        if not silent:
            logger.warning(
                f"Invalid item format '{item}'. Expected 'Name.Type'."
            )
        return None

    valid_types = _FABRIC_ITEMS.keys()
    if type not in valid_types:
        if not silent:
            logger.warning(
                f"Invalid item type '{type}'. Valid types are: {', '.join(valid_types)}."
            )
        return None

    for item_ in items:
        name_ = item_.get('displayName')
        type_ = item_.get('type')
        if name_ == name and type_ == type_:
            return item_['id']
    if not silent:
        logger.warning(f"Item '{item}' not found.")
    return None


@df
def get_item(
    workspace: str,
    item: str,
    *,
    df: bool = False,
) -> dict | pandas.DataFrame | None:
    """
    Retrieves a specific item from the workspace.

    Args:
        workspace (str): The workspace name or ID.
        item (str): The name or ID of the item to retrieve.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict | pandas.DataFrame | None): The item details as a dictionary or DataFrame, or None if not found.

    Examples:
        ```python
        get_item('MyProjectWorkspace', 'SalesDataModel')
        get_item('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', df=True)
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    item_id = resolve_item(workspace_id, item)
    if not item_id:
        return None

    response = _api_request(
        endpoint=f'/workspaces/{workspace_id}/items/{item_id}'
    )

    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


@df
def update_item(
    workspace: str,
    item: str,
    *,
    display_name: str = None,
    description: str = None,
    df: bool = False,
) -> dict | pandas.DataFrame:
    """
    Updates the properties of the specified semantic model.

    Args:
        workspace (str): The workspace name or ID.
        item (str): The name or ID of the item to update.
        display_name (str, optional): The new display name for the item.
        description (str, optional): The new description for the item.

    Returns:
        (dict or None): The updated semantic model details if successful, otherwise None.

    Examples:
        ```python
        update_item('MyProjectWorkspace', 'SalesDataModel', display_name='UpdatedSalesDataModel')
        update_item('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', description='Updated description')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    item_id = resolve_item(workspace_id, item)
    if not item_id:
        return None

    item_ = get_item(workspace_id, item_id)
    if not item_:
        return None

    item_description = item_['description']
    item_display_name = item_['displayName']

    payload = {}

    if item_display_name != display_name and display_name:
        payload['displayName'] = display_name

    if item_description != description and description:
        payload['description'] = description

    response = _api_request(
        endpoint=f'/workspaces/{workspace_id}/items/{item_id}',
        method='put',
        payload=payload,
    )

    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


def delete_item(workspace: str, item: str) -> None:
    """
    Delete a item from the specified workspace.

    Args:
        workspace (str): The name or ID of the workspace to delete.
        item (str): The name or ID of the item to delete.

    Returns:
        None: If the item is successfully deleted.

    Raises:
        ResourceNotFoundError: If the specified workspace is not found.

    Examples:
        ```python
        delete_item('MyProjectWorkspace', 'Salesitem')
        delete_item('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    item_id = resolve_item(workspace_id, item)
    if not item_id:
        return None

    response = _api_request(
        endpoint=f'/workspaces/{workspace_id}/items/{item_id}',
        method='delete',
        return_raw=True,
    )
    if not response.status_code == 200:
        logger.warning(f'{response.status_code}: {response.text}.')
        return False
    else:
        return True


def get_item_definition(workspace: str, item: str) -> dict:
    """
    Retrieves the definition of a item by its name or ID from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        item (str): The name or ID of the item.

    Returns:
        (dict): The item definition if found, otherwise None.

    Examples:
        ```python
        get_item_definition('MyProjectWorkspace', 'Salesitem')
        get_item_definition('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    # Resolving IDs
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    item_id = resolve_item(workspace_id, item)
    if not item_id:
        return None

    # Requesting
    response = _api_request(
        endpoint=f'/workspaces/{workspace_id}/items/{item_id}/getDefinition',
        method='post',
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    elif response.status_code == 202:
        # If the response is a long-running operation, handle it
        lro_response = _lro_handler(response)
        if not lro_response.success:
            logger.warning(
                f'{lro_response.status_code}: {lro_response.error}.'
            )
            return None
        else:
            return lro_response.data
    elif response.status_code == 200:
        # If the response is successful, we can process it
        return response.data
    else:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None


def update_item_definition(workspace: str, item: str, path: str) -> dict:
    """
    Updates the definition of an existing item in the specified workspace.
    If the item does not exist, it returns None.

    Args:
        workspace (str): The workspace name or ID.
        item (str): The name or ID of the item to update.
        path (str): The path to the item definition.

    Returns:
        (dict or None): The updated item details if successful, otherwise None.

    Examples:
        ```python
        update_item_definition('MyProjectWorkspace', 'SalesDataModel', '/path/to/updated/definition.json')
        update_item_definition('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', '/path/to/updated/definition.json')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    item_id = resolve_item(workspace_id, item)
    if not item_id:
        return None

    definition = pack_item_definition(path)

    params = {'updateMetadata': True}

    response = _api_request(
        endpoint=f'/workspaces/{workspace_id}/items/{item_id}/updateDefinition',
        method='post',
        payload={'definition': definition},
        params=params,
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    elif response.status_code == 202:
        # If the response is a long-running operation, handle it
        lro_response = _lro_handler(response)
        if not lro_response.success:
            logger.warning(
                f'{lro_response.status_code}: {lro_response.error}.'
            )
            return None
        else:
            return lro_response.data
    elif response.status_code == 200:
        # If the response is successful, we can process it
        return response.data
    else:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None


def create_item(
    workspace: str,
    display_name: str,
    path: str,
    *,
    description: str = None,
    folder: str = None,
):
    """
    Creates a new item in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name of the item.
        description (str, optional): A description for the item.
        folder (str, optional): The folder to create the item in.
        path (str): The path to the item definition file.

    Returns:
        (dict): The created item details.

    Examples:
        ```python
        create_item('MyProjectWorkspace', 'SalesDataModel', '/path/to/definition.json')
        create_item('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', '/path/to/definition.json')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    definition = pack_item_definition(path)

    payload = {'displayName': display_name, 'definition': definition}

    if description:
        payload['description'] = description

    if folder:
        folder_id = resolve_folder(workspace_id, folder)
        if not folder_id:
            logger.warning(
                f"Folder '{folder}' not found in workspace {workspace_id}."
            )
        else:
            payload['folderId'] = folder_id

    response = _api_request(
        endpoint=f'/workspaces/{workspace_id}/items',
        method='post',
        payload=payload,
    )

    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    elif response.status_code == 202:
        # If the response is a long-running operation, handle it
        lro_response = _lro_handler(response)
        if not lro_response.success:
            logger.warning(
                f'{lro_response.status_code}: {lro_response.error}.'
            )
            return None
        else:
            return lro_response.data
    elif response.status_code == 200:
        # If the response is successful, we can process it
        return response.data
    else:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None

