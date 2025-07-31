from typing import Any, Dict, List, Optional, Union

from pandas import DataFrame

from ..api.api import api_request
from ..core.workspaces import resolve_workspace
from ..utils.decorators import df
from ..utils.logging import get_logger
from ..utils.utils import is_valid_uuid

logger = get_logger(__name__)


@df
def list_folders(
    workspace: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    List folders in a workspace

    Args:
        workspace (str): The workspace to list folders from.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A list of folders in the workspace.

    Examples:
        ```python
        list_folders('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    return api_request(
        '/workspaces/' + resolve_workspace(workspace) + '/folders',
        support_pagination=True,
    )


def get_folder_id(workspace: str, folder_name: str) -> Union[str, None]:
    """
    Retrieves the ID of a folder by its name.

    Args:
        folder_name (str): The name of the folder.

    Returns:
        str | None: The ID of the folder if found, otherwise None.
    """
    folders = list_folders(
        workspace=resolve_workspace(workspace),
        df=False,
    )
    for _folder in folders:
        if _folder['displayName'] == folder_name:
            return _folder['id']
    logger.warning(
        f"Folder '{folder_name}' not found in workspace '{workspace}'."
    )
    return None


def resolve_folder(workspace: str, folder: str) -> Union[str, None]:
    """
    Resolves a folder name to its ID.

    Args:
        workspace (str): The name or ID of the workspace.
        folder (str): The name or ID of the folder.

    Returns:
        str | None: The ID of the folder if found, otherwise None.
    """
    if is_valid_uuid(folder):
        return folder
    else:
        return get_folder_id(workspace, folder)


@df
def get_folder(
    workspace: str, folder: str, *, df: Optional[bool] = True
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Get a folder in a workspace.

    Args:
        workspace (str): The name or id of the workspace to get the folder from.
        folder (str): The name or id of the folder to get.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The folder details if found, otherwise None.

    Examples:
        ```python
        get_folder(
            workspace_id='123e4567-e89b-12d3-a456-426614174000',
            folder_id='98f6b7c8-1234-5678-90ab-cdef12345678'
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)
    return api_request(
        '/workspaces/'
        + workspace_id
        + '/folders/'
        + resolve_folder(workspace_id, folder),
    )


@df
def create_folder(
    workspace: str,
    display_name: str,
    *,
    parent_folder: str = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Create a new folder in the specified workspace.

    Args:
        workspace (str): The name or ID of the workspace where the folder will be created.
        display_name (str): The name of the folder to create.
        parent_folder (str): The name or ID of the parent folder.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The created folder details if successful, otherwise None.

    Examples:
        ```python
        create_folder(
            workspace_id='123e4567-e89b-12d3-a456-426614174000',
            display_name='NewFolder',
            parent_folder_id='456e7890-e12b-34d5-a678-90abcdef1234'
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)

    payload = {'displayName': display_name}

    if parent_folder:
        payload['parentFolderId'] = resolve_folder(workspace_id, parent_folder)

    return api_request(
        '/workspaces/' + workspace_id + '/folders',
        payload=payload,
        method='post',
    )


def delete_folder(workspace: str, folder: str) -> None:
    """
    Delete a folder in a workspace

    Args:
        workspace (str): The name or ID of the workspace to delete the folder from.
        folder (str): The name or ID of the folder to delete.

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
    workspace_id = resolve_workspace(workspace)

    return api_request(
        '/workspaces/'
        + workspace_id
        + '/folders/'
        + resolve_folder(workspace_id, folder),
        method='delete',
    )


@df
def update_folder(
    workspace: str,
    folder: str,
    display_name: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Update a existing folder in the specified workspace.

    Args:
        workspace (str): The name or id of the workspace where the folder will be updated.
        folder (str): The name or id of the folder to update.
        display_name (str): The name of the folder to update.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The updated folder details if successful, otherwise None.

    Examples:
        ```python
        update_folder(
            workspace_id='123e4567-e89b-12d3-a456-426614174000',
            folder_id='98f6b7c8-1234-5678-90ab-cdef12345678',
            display_name='NewFolderName',
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)

    payload = {'displayName': display_name}

    return api_request(
        '/workspaces/'
        + workspace_id
        + '/folders/'
        + resolve_folder(workspace_id, folder),
        payload=payload,
        method='patch',
    )


@df
def move_folder(
    workspace: str,
    folder: str,
    *,
    target_folder: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Move a existing folder into other or root folder.

    Args:
        workspace (str): The workspace where the folder will be updated.
        folder (str): The folder to be moved.
        target_folder (str): The name of the parent folder will receive the moved folder.
        df (bool, optional): Keyword-only.
            If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The moved folder details if successful, otherwise None.

    Examples:
        ```python
        move_folder(
            workspace_id='123e4567-e89b-12d3-a456-426614174000',
            folder_id='414e7890-e12b-34d5-a678-90abcdef1234',
            target_folder_id='9859b7c8-1234-5678-90ab-cdef12345678',
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)

    payload = {}

    if target_folder:
        payload = {
            'targetFolderId': resolve_folder(workspace_id, target_folder)
        }

    return api_request(
        '/workspaces/'
        + workspace_id
        + '/folders/'
        + resolve_folder(workspace_id, folder)
        + '/move',
        payload=payload,
        method='post',
    )
