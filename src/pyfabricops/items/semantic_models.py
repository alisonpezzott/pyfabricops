from typing import Any, Dict, List, Optional, Union

from pandas import DataFrame

from pyfabricops.core import workspaces

from ..api.api import api_request
from ..core.folders import resolve_folder
from ..core.workspaces import resolve_workspace
from ..utils.decorators import df
from ..utils.logging import get_logger
from ..utils.utils import is_valid_uuid

logger = get_logger(__name__)


@df
def list_semantic_models(
    workspace: str,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Returns a list of semantic models in a specified workspace.

    Args:
        workspace_id (str): The ID of the workspace.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A list of semantic models or a DataFrame if df is True.
    """
    return api_request(
        endpoint='/workspaces/'
        + resolve_workspace(workspace)
        + '/semanticModels',
        support_pagination=True,
    )


def get_semantic_model_id(
    workspace: str, semantic_model: str
) -> Union[str, None]:
    """
    Retrieves the ID of a semantic model by its name from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        semantic_model (str): The name of the semantic model.

    Returns:
        (Optional[str]): The ID of the semantic model if found, otherwise None.

    Examples:
        ```python
        get_semantic_model_id('123e4567-e89b-12d3-a456-426614174000', 'SalesDataModel')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    semantic_models = list_semantic_models(workspace_id, df=False)
    for semantic_model_ in semantic_models:
        if semantic_model_['displayName'] == semantic_model:
            return semantic_model_['id']
    return None


def resolve_semantic_model(
    workspace: str,
    semantic_model: str,
) -> Union[str, None]:
    if is_valid_uuid(semantic_model):
        return semantic_model
    else:
        return get_semantic_model_id(workspace, semantic_model)


@df
def get_semantic_model(
    workspace: str, semantic_model: str, *, df: Optional[bool] = True
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Retrieves a semantic model by its name or ID from the specified workspace.

    Args:
        workspace_id (str): The workspace ID.
        semantic_model_id (str): The ID of the semantic model.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The semantic model details if found. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        get_semantic_model('123e4567-e89b-12d3-a456-426614174000', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    semantic_model_id = resolve_semantic_model(workspace, semantic_model)
    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/semanticModels/'
        + semantic_model_id,
    )


@df
def create_semantic_model(
    workspace: str,
    display_name: str,
    item_definition: Dict[str, Any],
    *,
    description: Optional[str] = None,
    folder: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Creates a new semantic model in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name of the semantic model.
        item_definition (Dict[str, Any]): The definition of the semantic model.
        description (Optional[str]): A description for the semantic model.
        folder (Optional[str]): The ID of the folder to create the semantic model in.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The created semantic model details.

    Examples:
        ```python
        create_semantic_model(
            workspace_id='123e4567-e89b-12d3-a456-426614174000',
            display_name='SalesDataModel',
            item_definition= {}, # Definition dict of the semantic model
            description='A semantic model for sales data',
            folder_id='456e7890-e12b-34d5-a678-9012345678901',
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
        endpoint='/workspaces/' + workspace_id + '/semanticModels',
        method='post',
        payload=payload,
        support_lro=True,
    )


@df
def update_semantic_model(
    workspace: str,
    semantic_model: str,
    *,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    df: Optional[bool] = False,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Updates the properties of the specified semantic model.

    Args:
        workspace (str): The workspace name or ID.
        semantic_model (str): The ID of the semantic model to update.
        display_name (str, optional): The new display name for the semantic model.
        description (str, optional): The new description for the semantic model.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The updated semantic model details if successful, otherwise None.

    Examples:
        ```python
        update_semantic_model(
            workspace_id='123e4567-e89b-12d3-a456-426614174000',
            semantic_model_id='456e7890-e12b-34d5-a678-9012345678901',
            display_name='UpdatedDisplayName',
            description='Updated description'
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)
    semantic_model_id = resolve_semantic_model(workspace, semantic_model)

    payload = {}

    if display_name:
        payload['displayName'] = display_name

    if description:
        payload['description'] = description

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/semanticModels/'
        + semantic_model_id,
        method='patch',
        payload=payload,
    )


def delete_semantic_model(workspace: str, semantic_model: str) -> None:
    """
    Delete a semantic model from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        semantic_model (str): The name or ID of the semantic model to delete.

    Returns:
        None

    Examples:
        ```python
        delete_semantic_model('123e4567-e89b-12d3-a456-426614174000', '456e7890-e12b-34d5-a678-9012345678901')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    semantic_model_id = resolve_semantic_model(workspace, semantic_model)

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/semanticModels/'
        + semantic_model_id,
        method='delete',
    )


def get_semantic_model_definition(
    workspace: str, semantic_model: str
) -> Union[Dict[str, Any], None]:
    """
    Retrieves the definition of a semantic model by its name or ID from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        semantic_model (str): The name or ID of the semantic model.

    Returns:
        ( Union[Dict[str, Any], None]): The semantic model definition if found, otherwise None.

    Examples:
        ```python
        get_semantic_model_definition(
            workspace_id='123e4567-e89b-12d3-a456-426614174000',
            semantic_model_id='456e7890-e12b-34d5-a678-9012345678901',
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)

    semantic_model_id = resolve_semantic_model(workspace, semantic_model)

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/semanticModels/'
        + semantic_model_id
        + '/getDefinition',
        method='post',
        support_lro=True,
    )


@df
def update_semantic_model_definition(
    workspace: str,
    semantic_model: str,
    item_definition: Dict[str, Any],
    *,
    df: Optional[bool] = True,
) -> Union[Dict[str, Any], None]:
    """
    Updates the definition of an existing semantic model in the specified workspace.
    If the semantic model does not exist, it returns None.

    Args:
        workspace (str): The workspace name or ID.
        semantic_model (str): The name or ID of the semantic model to update.
        item_definition (Dict[str, Any]): The new definition for the semantic model.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[Dict[str, Any], None]): The updated semantic model details if successful, otherwise None.

    Examples:
        ```python
        update_semantic_model(
            workspace_id='123e4567-e89b-12d3-a456-426614174000',
            semantic_model_id='456e7890-e12b-34d5-a678-9012345678901',
            item_definition={...} # New definition dict of the semantic model
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)
    semantic_model_id = resolve_semantic_model(workspace, semantic_model)
    params = {'updateMetadata': True}
    payload = {'definition': item_definition}
    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/semanticModels/'
        + semantic_model_id
        + '/updateDefinition',
        method='post',
        payload=payload,
        params=params,
        support_lro=True,
    )
