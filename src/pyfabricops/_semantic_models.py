from typing import Literal, Dict, List, Union, Optional

from pandas import DataFrame

from ._decorators import df
from ._generic_endpoints import (
    _post_generic,
    _delete_generic,
    _get_generic,
    _list_generic,
)
from ._logging import get_logger


logger = get_logger(__name__)


@df
def list_semantic_models(
    workspace_id: str, 
    df: Optional[bool] = True, 
) -> Union[DataFrame, List[Dict[str, str]], None]:
    """
    Returns a list of semantic models in a specified workspace.

    Args:
        workspace_id (str): The ID of the workspace.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.  
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, str]], None]): A list of semantic models or a DataFrame if df is True.
    """
    return _list_generic('semantic_models', workspace_id=workspace_id)


@df
def get_semantic_model(
    workspace_id: str, 
    semantic_model_id: str, 
    *, 
    df: Optional[bool] = True
) -> Union[DataFrame, Dict[str, str], None]:
    """
    Retrieves a semantic model by its name or ID from the specified workspace.

    Args:
        workspace_id (str): The workspace ID.
        semantic_model_id (str): The ID of the semantic model.  
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.  
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, str], None]): The semantic model details if found. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        get_semantic_model('123e4567-e89b-12d3-a456-426614174000', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    return _get_generic(
        'semantic_models', workspace_id=workspace_id, item_id=semantic_model_id
    )


@df
def create_semantic_model(
    workspace_id: str,
    display_name: str,
    item_definition: Dict[str, str],
    *,
    description: Optional[str] = None,
    folder_id: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, str], None]:
    """
    Creates a new semantic model in the specified workspace.

    Args:
        workspace_id (str): The workspace ID.
        display_name (str): The display name of the semantic model.
        item_definition (Dict[str, str]): The definition of the semantic model.
        description (Optional[str]): A description for the semantic model.
        folder_id (Optional[str]): The ID of the folder to create the semantic model in.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.  
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, str], None]): The created semantic model details.

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
    payload = {'displayName': display_name, 'definition': item_definition}

    if description:
        payload['description'] = description

    if folder_id:
        payload['folderId'] = folder_id

    return _post_generic(
        'semantic_models', workspace_id=workspace_id, payload=payload
    )


@df
def update_semantic_model(
    workspace_id: str,
    semantic_model_id: str,
    *,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    df: Optional[bool] = False,
) -> Union[DataFrame, Dict[str, str], None]:
    """
    Updates the properties of the specified semantic model.

    Args:
        workspace_id (str): The workspace ID.
        semantic_model_id (str): The ID of the semantic model to update.
        display_name (str, optional): The new display name for the semantic model.
        description (str, optional): The new description for the semantic model.  
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.  
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, str], None]): The updated semantic model details if successful, otherwise None.

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
    if not display_name and not description:
        logger.warning(
            'No display_name or description provided. Nothing to update.'
        )
        return None

    payload = {}

    if display_name:
        payload['displayName'] = display_name

    if description:
        payload['description'] = description

    return _post_generic(
        'semantic_models',
        workspace_id=workspace_id,
        item_id=semantic_model_id,
        payload=payload,
    )


def delete_semantic_model(workspace_id: str, semantic_model_id: str) -> None:
    """
    Delete a semantic model from the specified workspace.

    Args:
        workspace_id (str): The ID of the workspace to delete.
        semantic_model_id (str): The ID of the semantic model to delete.

    Returns:
        None

    Examples:
        ```python
        delete_semantic_model('123e4567-e89b-12d3-a456-426614174000', '456e7890-e12b-34d5-a678-9012345678901')
        ```
    """
    return _delete_generic(
        'semantic_models', workspace_id=workspace_id, item_id=semantic_model_id
    )


def get_semantic_model_definition(
        workspace_id: str, 
        semantic_model_id: str
    ) -> Union[Dict[str, str], None]:
    """
    Retrieves the definition of a semantic model by its name or ID from the specified workspace.

    Args:
        workspace_id (str): The workspace name or ID.
        semantic_model_id (str): The name or ID of the semantic model.

    Returns:
        ( Union[Dict[str, str], None]): The semantic model definition if found, otherwise None.

    Examples:
        ```python
        get_semantic_model_definition(
            workspace_id='123e4567-e89b-12d3-a456-426614174000',
            semantic_model_id='456e7890-e12b-34d5-a678-9012345678901', 
        ) 
        ```
    """
    return _post_generic(
        'semantic_models',
        workspace_id=workspace_id,
        item_id=semantic_model_id,
        endpoint_suffix='/getDefinition',
    )  
    

@df
def update_semantic_model_definition(
    workspace_id: str, 
    semantic_model_id: str, 
    item_definition: Dict[str, str],
    *,
    df: Optional[bool] = True,
) -> Union[Dict[str, str], None]:
    """
    Updates the definition of an existing semantic model in the specified workspace.
    If the semantic model does not exist, it returns None.

    Args:
        workspace_id (str): The workspace name or ID.
        semantic_model_id (str): The name or ID of the semantic model to update.
        item_definition (Dict[str, str]): The new definition for the semantic model.  
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.  
            If False, returns a list of dictionaries.

    Returns:
        (Union[Dict[str, str], None]): The updated semantic model details if successful, otherwise None.

    Examples:
        ```python
        update_semantic_model(
            workspace_id='123e4567-e89b-12d3-a456-426614174000',
            semantic_model_id='456e7890-e12b-34d5-a678-9012345678901',
            item_definition={...} # New definition dict of the semantic model
        ) 
        ```
    """
    params = {'updateMetadata': True}
    payload = {'definition': item_definition}
    return _post_generic(
        'semantic_models',
        workspace_id=workspace_id,
        item_id=semantic_model_id,
        payload=payload,
        params=params,
        endpoint_suffix='/updateDefinition',
    )
