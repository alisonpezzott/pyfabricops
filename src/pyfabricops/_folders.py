from pandas import DataFrame
from typing import Dict, List, Union, Optional

from ._decorators import df
from ._generic_endpoints import (
    _list_generic,
    _get_generic,
    _post_generic,
    _patch_generic,
    _delete_generic,
)
from ._logging import get_logger


logger = get_logger(__name__)


@df
def list_folders(
    workspace_id: str, 
    *, 
    df: Optional[bool] = True
) -> Union[DataFrame, List[Dict[str, str]], None]: 
    """
    List folders in a workspace

    Args:
        workspace_id (str): The workspace to list folders from.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.  
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, str]], None]): A list of folders in the workspace.

    Examples:
        ```python
        list_folders('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    return _list_generic('folders', workspace_id)


@df
def get_folder(
    workspace_id: str, 
    folder_id: str, 
    *, df: 
    Optional[bool] = True
) -> Union[DataFrame, Dict[str, str], None]:
    """
    Get a folder in a workspace.

    Args:
        workspace_id (str): The workspace to get the folder from.
        folder_id (str): The folder to get.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.  
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, str], None]): The folder details if found, otherwise None.

    Examples:
        ```python
        get_folder(
            workspace_id='123e4567-e89b-12d3-a456-426614174000', 
            folder_id='98f6b7c8-1234-5678-90ab-cdef12345678'
        )
        ```
    """
    return _get_generic(
        'folders', workspace_id, item_id=folder_id
    )


@df
def create_folder(
    workspace_id: str, 
    display_name: str, 
    *, 
    parent_folder_id: str = None, 
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, str], None]:
    """
    Create a new folder in the specified workspace.

    Args:
        workspace_id (str): The workspace where the folder will be created.
        display_name (str): The name of the folder to create.
        parent_folder_id (str): The ID of the parent folder.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.  
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, str], None]): The created folder details if successful, otherwise None.

    Examples:
        ```python
        create_folder(
            workspace_id='123e4567-e89b-12d3-a456-426614174000',
            display_name='NewFolder',
            parent_folder_id='456e7890-e12b-34d5-a678-90abcdef1234'
        )
        ```
    """
    payload = {'displayName': display_name}

    if parent_folder_id:
        payload['parentFolderId'] = parent_folder_id

    return _post_generic(
        'folders',
        workspace_id,
        payload=payload,
    )


def delete_folder(workspace_id: str, folder_id: str) -> None:
    """
    Delete a folder in a workspace

    Args:
        workspace_id (str): The workspace to delete the folder from.
        folder_id (str): The folder to delete.

    Returns:
        None.

    Examples:
        ```python
        delete_folder(
            workspace_id='123e4567-e89b-12d3-a456-426614174000',
            folder_id='98f6b7c8-1234-5678-90ab-cdef12345678'
        )
        ```
    """
    return _delete_generic(
        'folders', workspace_id, item_id=folder_id
    )


@df
def update_folder(
    workspace_id: str, 
    folder_id: str, 
    display_name: str, 
    *, 
    df: Optional[bool] = True
) -> Union[DataFrame, Dict[str, str], None]:
    """
    Update a existing folder in the specified workspace.

    Args:
        workspace_id (str): The workspace where the folder will be updated.
        folder_id (str): The folder to update.
        display_name (str): The name of the folder to update.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.  
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, str], None]): The updated folder details if successful, otherwise None.

    Examples:
        ```python
        update_folder(
            workspace_id='123e4567-e89b-12d3-a456-426614174000',
            folder_id='98f6b7c8-1234-5678-90ab-cdef12345678',
            display_name='NewFolderName',
        )
        ```
    """
    payload = {'displayName': display_name}
    return _patch_generic(
        'folders', workspace_id, item_id=folder_id, payload=payload
    )


@df
def move_folder(
    workspace_id: str, 
    folder_id: str, 
    target_folder_id: str, 
    *, 
    df: Optional[bool] = True
) -> Union[DataFrame, Dict[str, str], None]:
    """
    Move a existing folder into other or root folder.

    Args:
        workspace_id (str): The workspace where the folder will be updated.
        folder_id (str): The folder to be moved.
        target_folder_id (str): The name of the parent folder will receive the moved folder.
        df (bool, optional): Keyword-only.  
            If True or not provided, returns a DataFrame with flattened keys.  
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, str], None]): The moved folder details if successful, otherwise None.

    Examples:
        ```python
        move_folder(
            workspace_id='123e4567-e89b-12d3-a456-426614174000',
            folder_id='414e7890-e12b-34d5-a678-90abcdef1234',
            target_folder_id='9859b7c8-1234-5678-90ab-cdef12345678',
        )
        ```
    """
    payload = {'targetFolderId': target_folder_id}
    return _post_generic(
        'folders', workspace_id, 
        item_id=folder_id, 
        payload=payload, 
        endpoint_suffix='/move',
    )
