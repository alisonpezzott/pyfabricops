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
def list_notebooks(
    workspace: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Lists all notebooks in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A list of notebooks, a DataFrame with flattened keys, or None if not found.

    Examples:
        ```python
        list_notebooks('MyProjectWorkspace')
        list_notebooks('MyProjectWorkspace', df=True)
        ```
    """
    return api_request(
        endpoint='/workspaces/' + resolve_workspace(workspace) + '/notebooks',
        support_pagination=True,
    )


def get_notebook_id(workspace: str, notebook: str) -> Union[str, None]:
    """
    Retrieves the ID of a notebook by its name or ID from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        notebook (str): The name or ID of the notebook.

    Returns:
        (Union[str, None]): The ID of the notebook if found, otherwise None.

    Examples:
        ```python
        get_notebook_id('MyProjectWorkspace', 'SalesDataNotebook')
        get_notebook_id('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    notebooks = list_notebooks(workspace, df=False)
    for nb in notebooks:
        if nb['displayName'] == notebook or nb['id'] == notebook:
            return nb['id']
    return None


def resolve_notebook(
    workspace: str,
    notebook: str,
) -> Union[str, None]:
    """
    Resolves a notebook name or ID to its ID in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        notebook (str): The name or ID of the notebook.
        silent (bool): If True, suppresses warnings. Defaults to False.

    Returns:
        Optional[str]: The ID of the notebook if found, otherwise None.

    Examples:
        ```python
        resolve_notebook('MyProjectWorkspace', 'SalesDataNotebook')
        resolve_notebook('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    if is_valid_uuid(notebook):
        return notebook
    else:
        return get_notebook_id(workspace, notebook)


@df
def get_notebook(
    workspace: str,
    notebook: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Retrieves a notebook by its name or ID from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        notebook (str): The name or ID of the notebook.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The notebook details if found. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        get_notebook('MyProjectWorkspace', 'SalesDataNotebook')
        get_notebook('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', df=True)
        ```
    """
    workspace_id = resolve_workspace(workspace)

    notebook_id = resolve_notebook(workspace_id, notebook)

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/notebooks/' + notebook_id,
    )


@df
def update_notebook(
    workspace: str,
    notebook: str,
    *,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Updates the properties of the specified notebook.

    Args:
        workspace (str): The workspace name or ID.
        notebook (str): The name or ID of the notebook to update.
        display_name (Optional[str]): The new display name for the notebook.
        description (Optional[str]): The new description for the notebook.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The updated notebook details if successful, otherwise None.

    Examples:
        ```python
        update_notebook('MyProjectWorkspace', 'SalesDataModel', display_name='UpdatedSalesDataModel')
        update_notebook('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', description='Updated description')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    notebook_id = resolve_notebook(workspace_id, notebook)

    payload = {}

    if display_name:
        payload['displayName'] = display_name

    if description:
        payload['description'] = description

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/notebooks/' + notebook_id,
        method='patch',
        payload=payload,
    )


def delete_notebook(workspace: str, notebook: str) -> None:
    """
    Delete a notebook from the specified workspace.

    Args:
        workspace (str): The name or ID of the workspace to delete.
        notebook (str): The name or ID of the notebook to delete.

    Returns:
        None: If the notebook is successfully deleted.

    Raises:
        ResourceNotFoundError: If the specified workspace is not found.

    Examples:
        ```python
        delete_notebook('MyProjectWorkspace', 'SalesDataNotebook')
        delete_notebook('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    notebook_id = resolve_notebook(workspace_id, notebook)

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/notebooks/' + notebook_id,
        method='delete',
    )


def get_notebook_definition(
    workspace: str, notebook: str
) -> Union[Dict[str, Any], None]:
    """
    Retrieves the definition of a notebook by its name or ID from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        notebook (str): The name or ID of the notebook.

    Returns:
        (Union[Dict[str, Any], None]): The notebook definition if found, otherwise None.

    Examples:
        ```python
        get_notebook_definition('MyProjectWorkspace', 'Salesnotebook')
        get_notebook_definition('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    notebook_id = resolve_notebook(workspace_id, notebook)

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/notebooks/'
        + notebook_id
        + '/getDefinition',
        method='post',
        support_lro=True,
    )


@df
def update_notebook_definition(
    workspace: str,
    notebook: str,
    item_definition: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Updates the definition of an existing notebook in the specified workspace.
    If the notebook does not exist, it returns None.

    Args:
        workspace (str): The workspace name or ID.
        notebook (str): The name or ID of the notebook to update.
        path (str): The path to the notebook definition.

    Returns:
        (dict or None): The updated notebook details if successful, otherwise None.

    Examples:
        ```python
        update_notebook('MyProjectWorkspace', 'SalesDataModel', display_name='UpdatedSalesDataModel')
        update_notebook('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', description='Updated description')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    notebook_id = resolve_notebook(workspace_id, notebook)

    payload = {'definition': item_definition}

    params = {'updateMetadata': True}

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/notebooks/'
        + notebook_id
        + '/updateDefinition',
        method='post',
        payload=payload,
        params=params,
        support_lro=True,
    )


@df
def create_notebook(
    workspace: str,
    display_name: str,
    item_definition: str,
    *,
    description: Optional[str] = None,
    folder: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Creates a new notebook in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name of the notebook.
        description (str, optional): A description for the notebook.
        folder (str, optional): The folder to create the notebook in.
        path (str): The path to the notebook definition file.

    Returns:
        (dict): The created notebook details.

    Examples:
        ```python
        create_notebook('MyProjectWorkspace', 'SalesDataModel', 'path/to/definition.json')
        create_notebook('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', 'path/to/definition.json')
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
        endpoint='/workspaces/' + workspace_id + '/notebooks',
        method='post',
        payload=payload,
        support_lro=True,
    )
