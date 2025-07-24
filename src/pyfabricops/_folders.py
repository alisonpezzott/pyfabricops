import pandas

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
    workspace_id: str, *, df: bool = True
) -> list | pandas.DataFrame | None:
    """
    List folders in a workspace

    Args:
        workspace_id (str): The workspace to list folders from.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (list or pandas.DataFrame or None): A list of folders in the workspace. df=True returns a DataFrame.

    Examples:
        ```python
        list_folders('my_workspace')
        ```
    """
    return _list_generic('folders', workspace_id)


@df
def get_folder(
    workspace_id: str, folder_id: str, *, df: bool = True
) -> dict | pandas.DataFrame | None:
    """
    Get a folder in a workspace.

    Args:
        workspace (str): The workspace to get the folder from.
        folder (str): The folder to get.

    Returns:
        (dict or pandas.DataFrame): The folder details if found, otherwise None.

    Examples:
        ```python
        get_folder('MyProjectWorkspace', 'SalesFolder')
        get_folder('123e4567-e89b-12d3-a456-426614174000', 'SalesFolder')
        ```
    """
    return _get_generic(
        'folders', workspace_id, item_id=folder_id
    )


@df
def create_folder(
    workspace_id: str, display_name: str, *, parent_folder_id: str = None, df: bool = True
) -> dict | pandas.DataFrame | None:
    """
    Create a new folder in the specified workspace.

    Args:
        workspace_id (str): The workspace where the folder will be created.
        display_name (str): The name of the folder to create.
        parent_folder_id (str): The ID of the parent folder.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame or None): The created folder details if successful, otherwise None.

    Examples:
        ```python
        create_folder('MyProjectWorkspace', 'NewFolder', 'ParentFolder')
        create_folder('123e4567-e89b-12d3-a456-426614174000', 'NewFolder', 'ParentFolder')
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


def delete_folder(workspace_id: str, folder_id: str) -> bool | None:
    """
    Delete a folder in a workspace

    Args:
        workspace_id (str): The workspace to delete the folder from.
        folder_id (str): The folder to delete.

    Returns:
        (bool | None): True if the folder was deleted successfully, False if not found, None if workspace is invalid.

    Examples:
        ```python
        delete_folder('MyProjectWorkspace', 'SalesFolder')
        delete_folder('123e4567-e89b-12d3-a456-426614174000', 'SalesFolder')
        ```
    """
    return _delete_generic(
        'folders', workspace_id, item_id=folder_id
    )


@df
def update_folder(
    workspace_id: str, folder_id: str, display_name: str, *, df: bool = True
) -> dict | pandas.DataFrame | None:
    """
    Update a existing folder in the specified workspace.

    Args:
        workspace_id (str): The workspace where the folder will be updated.
        folder_id (str): The folder to update.
        display_name (str): The name of the folder to update.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame | None): The updated folder details if successful, otherwise None.

    Examples:
        ```python
        update_folder('MyProjectWorkspace', 'OldFolderName', 'NewFolderName')
        update_folder('123e4567-e89b-12d3-a456-426614174000', 'OldFolderName', 'NewFolderName')
        ```
    """
    payload = {'displayName': display_name}
    return _patch_generic(
        'folders', workspace_id, item_id=folder_id, payload=payload
    )


@df
def move_folder(
    workspace_id: str, folder_id: str, target_folder_id: str, *, df: bool = True
) -> dict | pandas.DataFrame | None:
    """
    Move a existing folder into other or root folder.

    Args:
        workspace_id (str): The workspace where the folder will be updated.
        folder_id (str): The folder to be moved.
        target_folder_id (str): The name of the parent folder will receive the moved folder.

    Returns:
        (dict | pandas.DataFrame | None): The moved folder details if successful, otherwise None.

    Examples:
        ```python
        move_folder('MyProjectWorkspace', 'SalesFolder', 'Archive')
        move_folder('123e4567-e89b-12d3-a456-426614174000', 'SalesFolder', 'Archive')
        ```
    """
    payload = {'targetFolderId': target_folder_id}
    return _post_generic(
        'folders_move', workspace_id, item_id=folder_id, payload=payload
    )
