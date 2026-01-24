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
def list_variable_libraries(
    workspace: str,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Returns a list of variable libraries in a specified workspace.

    Args:
        workspace_id (str): The ID of the workspace.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A list of variable libraries or a DataFrame if df is True.
    """
    return api_request(
        endpoint='/workspaces/'
        + resolve_workspace(workspace)
        + '/VariableLibraries',
        support_pagination=True,
    )


def get_variable_library_id(
    workspace: str, variable_library_name: str
) -> Union[str, None]:
    """
    Retrieves the ID of a variable library by its name from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        variable_library_name (str): The name of the variable_library.

    Returns:
        (Optional[str]): The ID of the variable_library if found, otherwise None.

    Examples:
        ```python
        get_variable_library_id('123e4567-e89b-12d3-a456-426614174000', 'Variables')
        ```
    """
    libraries = list_variable_libraries(
        workspace=resolve_workspace(workspace), df=False
    )
    for library in libraries:
        if library.get('displayName') == variable_library_name:
            return library.get('id')
    return None


def resolve_variable_library(
    workspace: str,
    variable_library: str,
) -> Union[str, None]:
    if is_valid_uuid(variable_library):
        return variable_library
    else:
        return get_variable_library_id(workspace, variable_library)


@df
def get_variable_library(
    workspace: str, variable_library: str, *, df: Optional[bool] = True
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Retrieves a variable_library by its name or ID from the specified workspace.

    Args:
        workspace_id (str): The workspace ID.
        variable_library (str): The ID or name of the variable_library.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The variable_library details if found. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        get_variable_library('123e4567-e89b-12d3-a456-426614174000', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    variable_library_id = resolve_variable_library(workspace, variable_library)
    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/VariableLibrary/'
        + variable_library_id,
    )


@df
def create_variable_library(
    workspace: str,
    display_name: str,
    item_definition: Dict[str, Any],
    *,
    description: Optional[str] = None,
    folder: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Creates a new variable library in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name of the variable library.
        item_definition (Dict[str, Any]): The definition of the variable library.
        description (Optional[str]): A description for the variable library.
        folder (Optional[str]): The ID of the folder to create the variable library in.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The created variable library details.

    Examples:
        ```python
        create_variable_library(
            workspace_id='123e4567-e89b-12d3-a456-426614174000',
            display_name='vl_variables',
            item_definition= {}, # Definition dict of the variable library
            description='A variable library for CI/CD implementation',
            folder_id='456e7890-e12b-34d5-a678-9012345678901',
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)

    payload = {'displayName': display_name, 'definition': item_definition}

    if description:
        payload['description'] = description

    if folder:
        folder_id = resolve_folder(folder, workspace_id=workspace_id)
        if folder_id:
            payload['folderId'] = folder_id

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/VariableLibrary',
        method='post',
        payload=payload,
        support_lro=True,
    )


@df
def update_variable_library(
    workspace: str,
    variable_library: str,
    *,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    df: Optional[bool] = False,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Updates the properties of the specified variable_library.

    Args:
        workspace (str): The workspace name or ID.
        report (str): The ID of the variable_library to update.
        display_name (str, optional): The new display name for the variable_library.
        description (str, optional): The new description for the variable_library.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The updated variable_library details if successful, otherwise None.

    Examples:
        ```python
        update_variable_library(
            workspace_id='123e4567-e89b-12d3-a456-426614174000',
            report_id='456e7890-e12b-34d5-a678-9012345678901',
            display_name='UpdatedDisplayName',
            description='Updated description'
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)
    variable_library_id = resolve_variable_library(workspace, variable_library)

    payload = {}

    if display_name:
        payload['displayName'] = display_name

    if description:
        payload['description'] = description

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/VariableLibraries/'
        + variable_library_id,
        method='patch',
        payload=payload,
    )


def delete_variable_library(workspace: str, variable_library: str) -> None:
    """
    Delete a semantic model from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        variable_library (str): The name or ID of the semantic model to delete.

    Returns:
        None

    Examples:
        ```python
        delete_variable_library('123e4567-e89b-12d3-a456-426614174000', '456e7890-e12b-34d5-a678-9012345678901')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    variable_library_id = resolve_variable_library(workspace, variable_library)

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/VariableLibraries/'
        + variable_library_id,
        method='delete',
    )


def get_variable_library_definition(
    workspace: str, variable_library: str
) -> Union[Dict[str, Any], None]:
    """
    Retrieves the definition of a variable library by its name or ID from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        variable_library (str): The name or ID of the variable library.

    Returns:
        ( Union[Dict[str, Any], None]): The variable library definition if found, otherwise None.

    Examples:
        ```python
        get_variable_library_definition(
            workspace_id='123e4567-e89b-12d3-a456-426614174000',
            variable_library_id='456e7890-e12b-34d5-a678-9012345678901',
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)

    variable_library_id = resolve_variable_library(workspace, variable_library)

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/VariableLibraries/'
        + variable_library_id
        + '/getDefinition',
        method='post',
        support_lro=True,
    )


@df
def update_variable_library_definition(
    workspace: str,
    variable_library: str,
    item_definition: Dict[str, Any],
    *,
    df: Optional[bool] = True,
) -> Union[Dict[str, Any], None]:
    """
    Updates the definition of an existing variable_library in the specified workspace.
    If the variable_library does not exist, it returns None.

    Args:
        workspace (str): The workspace name or ID.
        variable_library (str): The name or ID of the variable library to update.
        item_definition (Dict[str, Any]): The new definition for the variable library.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[Dict[str, Any], None]): The updated variable library details if successful, otherwise None.

    Examples:
        ```python
        update_variable_library(
            workspace_id='123e4567-e89b-12d3-a456-426614174000',
            variable_library_id='456e7890-e12b-34d5-a678-9012345678901',
            item_definition={...} # New definition dict of the semantic model
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)
    variable_library_id = resolve_variable_library(workspace, variable_library)
    params = {'updateMetadata': True}
    payload = {'definition': item_definition}
    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/VariableLibraries/'
        + variable_library
        + '/updateDefinition',
        method='post',
        payload=payload,
        params=params,
        support_lro=True,
    )
