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
def list_items(
    workspace: str, *, df: Optional[bool] = True
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Returns a list of items from the specified workspace.
    This API supports pagination.

    Args:
        workspace (str): The workspace name or ID.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A list of items, excluding those that start with the specified prefixes. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        list_items('MyProjectWorkspace')
        list_items('MyProjectWorkspace', df=False)
        ```
    """
    workspace_id = resolve_workspace(workspace)
    return api_request(
        endpoint='/workspaces/' + workspace_id + '/items',
        support_pagination=True,
    )


def get_item_id(workspace: str, item: str) -> str | None:
    """
    Retrieves the ID of a specific item in the workspace.

    Args:
        workspace (str): The workspace name or ID.
        item (str): The name with type of the item.

    Returns:
        str|None: The ID of the item, or None if not found.

    Examples:
        ```python
        get_item_id('MyProjectWorkspace', 'SalesDataModel.SemanticModel')
        get_item_id('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    items = list_items(
        workspace=resolve_workspace(workspace),
        df=False,
    )

    for _item in items:
        if _item['displayName'] + '.' + _item['type'] == item:
            return _item['id']
    logger.warning(f"Item '{item}' not found in workspace '{workspace}'.")
    return None


def resolve_item(
    workspace: str,
    item: str,
) -> Union[str, None]:
    """
    Resolves a item name to its ID.

    Args:
        workspace (str): The ID of the workspace.
        item (str): The name of the item.

    Returns:
        (Union[str, None]): The ID of the item, or None if not found.

    Examples:
        ```python
        resolve_item('MyProjectWorkspace', 'SalesDataModel')
        resolve_item('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    if is_valid_uuid(item):
        return item
    else:
        return get_item_id(resolve_workspace(workspace), item)


@df
def get_item(
    workspace: str,
    item: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Retrieves a specific item from the workspace.

    Args:
        workspace (str): The workspace name or ID.
        item (str): The name or ID of the item to retrieve.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The item details as a dictionary or DataFrame, or None if not found.

    Examples:
        ```python
        get_item('MyProjectWorkspace', 'SalesDataModel')
        get_item('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', df=True)
        ```
    """
    workspace_id = resolve_workspace(workspace)

    item_id = resolve_item(workspace_id, item)

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/items/' + item_id,
    )


@df
def update_item(
    workspace: str,
    item: str,
    *,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Updates the properties of the specified semantic model.

    Args:
        workspace (str): The workspace name or ID.
        item (str): The name or ID of the item to update.
        display_name (str, optional): The new display name for the item.
        description (str, optional): The new description for the item.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The updated semantic model details if successful, otherwise None.

    Examples:
        ```python
        update_item('MyProjectWorkspace', 'SalesDataModel', display_name='UpdatedSalesDataModel')
        update_item('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', description='Updated description')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    item_id = resolve_item(workspace_id, item)

    payload = {}

    if display_name:
        payload['displayName'] = display_name

    if description:
        payload['description'] = description

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/items/' + item_id,
        method='patch',
        payload=payload,
    )


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

    item_id = resolve_item(workspace_id, item)

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/items/' + item_id,
        method='delete',
    )


def get_item_definition(
    workspace: str, item: str
) -> Union[Dict[str, Any], None]:
    """
    Retrieves the definition of a item by its name or ID from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        item (str): The name or ID of the item.

    Returns:
        (Union[Dict[str, Any], None]): The item definition if found, otherwise None.

    Examples:
        ```python
        get_item_definition('MyProjectWorkspace', 'Salesitem')
        get_item_definition('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    item_id = resolve_item(workspace_id, item)

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/items/'
        + item_id
        + '/getDefinition',
        method='post',
        support_lro=True,
    )


@df
def update_item_definition(
    workspace: str,
    item: str,
    item_definition: Dict[str, Any],
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Updates the definition of an existing item in the specified workspace.
    If the item does not exist, it returns None.

    Args:
        workspace (str): The workspace name or ID.
        item (str): The name or ID of the item to update.
        item_definition (Dict[str, Any]): The updated item definition.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The updated item details if successful, otherwise None.

    Examples:
        ```python
        update_item_definition(
            'MyProjectWorkspace',
            'SalesDataModel',
            item_definition = {...}  # Updated item definition
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)

    item_id = resolve_item(workspace_id, item)

    payload = {'definition': item_definition}

    params = {'updateMetadata': True}

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/items/'
        + item_id
        + '/updateDefinition',
        payload=payload,
        params=params,
        support_lro=True,
    )


@df
def create_item(
    workspace: str,
    display_name: str,
    item_definition: Dict[str, Any],
    *,
    description: Optional[str] = None,
    folder: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Creates a new item in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name of the item.
        item_definition (Dict[str, Any]): The item definition.
        description (str, optional): A description for the item.
        folder (str, optional): The folder to create the item in.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The created item details.

    Examples:
        ```python
        create_item(
            'MyProjectWorkspace', 'SalesDataModel', item_definition={...}
        )
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
        endpoint='/workspaces/' + workspace_id + '/items',
        method='post',
        payload=payload,
        support_lro=True,
    )


def delete_item(workspace: str, item: str) -> None:
    """
    Deletes an existing item in the specified workspace.
    If the item does not exist, it returns None.

    Args:
        workspace (str): The workspace name or ID.
        item (str): The name or ID of the item to delete.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The deleted item details if successful, otherwise None.

    Examples:
        ```python
        delete_item('MyProjectWorkspace', 'SalesDataModel')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    item_id = resolve_item(workspace_id, item)

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/items/' + item_id,
        method='delete',
    )
