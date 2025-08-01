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
def list_data_pipelines(
    workspace: str, *, df: Optional[bool] = True
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Lists all data_pipelines in the specified workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        list | pandas.DataFrame | None: A list of data_pipelines if successful, otherwise None.

    Examples:
        ```python
        list_data_pipelines('MyProjectWorkspace')
        list_data_pipelines('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    return api_request(
        '/workspaces/' + resolve_workspace(workspace) + '/dataPipelines',
        support_pagination=True,
    )


def get_data_pipeline_id(
    workspace: str, data_pipeline_name: str
) -> Union[str, None]:
    """
    Retrieves the ID of a data pipeline by its name.

    Args:
        data_pipeline_name (str): The name of the data pipeline.

    Returns:
        str | None: The ID of the data pipeline if found, otherwise None.
    """
    data_pipelines = list_data_pipelines(
        workspace=resolve_workspace(workspace),
        df=False,
    )
    for _data_pipeline in data_pipelines:
        if _data_pipeline['displayName'] == data_pipeline_name:
            return _data_pipeline['id']
    logger.warning(
        f"DataPipeline '{data_pipeline_name}' not found in workspace '{workspace}'."
    )
    return None


def resolve_data_pipeline(
    workspace: str, data_pipeline: str
) -> Union[str, None]:
    """
    Resolves a data pipeline name to its ID.

    Args:
        workspace (str): The name or ID of the workspace.
        data_pipeline (str): The name or ID of the data pipeline.

    Returns:
        str | None: The ID of the data pipeline if found, otherwise None.
    """
    if is_valid_uuid(data_pipeline):
        return data_pipeline
    else:
        return get_data_pipeline_id(workspace, data_pipeline)


@df
def get_data_pipeline(
    workspace: str, data_pipeline: str
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Retrieves the details of a data pipeline by its ID.

    Args:
        workspace (str): The name or ID of the workspace.
        data_pipeline (str): The name or ID of the data pipeline.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.


    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The data pipeline details if found, otherwise None.

    Examples:
        ```python
        get_data_pipeline('123e4567-e89b-12d3-a456-426614174000', 'SalesDataPipeline')
        get_data_pipeline('my-workspace', 'SalesDataPipeline')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    return api_request(
        '/workspaces/'
        + workspace_id
        + '/dataPipelines/'
        + resolve_data_pipeline(workspace_id, data_pipeline),
    )


@df
def update_data_pipeline(
    workspace: str,
    data_pipeline: str,
    *,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Updates the properties of the specified data pipeline.

    Args:
        workspace (str): The workspace name or ID.
        data_pipeline (str): The name or ID of the data_pipeline to update.
        display_name (str, optional): The new display name for the data_pipeline.
        description (str, optional): The new description for the data_pipeline.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The updated data pipeline details if successful, otherwise None.

    Examples:
        ```python
        update_data_pipeline('MyProjectWorkspace', 'SalesDataModel', display_name='UpdatedSalesDataModel')
        update_data_pipeline('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', description='Updated description')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    data_pipeline_id = resolve_data_pipeline(workspace_id, data_pipeline)

    payload = {}

    if display_name:
        payload['displayName'] = display_name

    if description:
        payload['description'] = description

    return api_request(
        '/workspaces/' + workspace_id + '/dataPipelines/' + data_pipeline_id,
        method='patch',
        payload=payload,
    )


def delete_data_pipeline(workspace: str, data_pipeline: str) -> None:
    """
    Delete a data_pipeline from the specified workspace.

    Args:
        workspace (str): The name or ID of the workspace to delete.
        data_pipeline (str): The name or ID of the data_pipeline to delete.

    Returns:
        None: If the data_pipeline is successfully deleted.

    Raises:
        ResourceNotFoundError: If the specified workspace is not found.

    Examples:
        ```python
        delete_data_pipeline('123e4567-e89b-12d3-a456-426614174000', 'Salesdata_pipeline')
        delete_data_pipeline('MyProject', 'Salesdata_pipeline')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    data_pipeline_id = resolve_data_pipeline(workspace_id, data_pipeline)

    return api_request(
        '/workspaces/' + workspace_id + '/dataPipelines/' + data_pipeline_id,
        method='delete',
    )


def get_data_pipeline_definition(workspace: str, data_pipeline: str) -> dict:
    """
    Retrieves the definition of a data_pipeline by its name or ID from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        data_pipeline (str): The name or ID of the data_pipeline.

    Returns:
        (dict): The data_pipeline definition if found, otherwise None.

    Examples:
        ```python
        get_data_pipeline_definition('MyProjectWorkspace', 'Salesdata_pipeline')
        get_data_pipeline_definition('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    # Resolving IDs
    workspace_id = resolve_workspace(workspace)

    data_pipeline_id = resolve_data_pipeline(workspace_id, data_pipeline)

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/dataPipelines/'
        + data_pipeline_id
        + '/getDefinition',
        method='post',
        support_lro=True,
    )


@df
def update_data_pipeline_definition(
    workspace: str, data_pipeline: str, item_definition: Dict[str, Any]
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Updates the definition of an existing data_pipeline in the specified workspace.
    If the data_pipeline does not exist, it returns None.

    Args:
        workspace (str): The workspace name or ID.
        data_pipeline (str): The name or ID of the data_pipeline to update.
        item_definition (Dict[str, Any]): The item_definition of the data_pipeline.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The updated data_pipeline details if successful, otherwise None.

    Examples:
        ```python
        update_data_pipeline_definition(
            workspace='MyProjectWorkspace',
            data_pipeline='SalesDataPipeline',
            item_definition={...} # The definition of the data_pipeline
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)

    data_pipeline_id = resolve_data_pipeline(workspace_id, data_pipeline)

    params = {'updateMetadata': True}
    payload = {'definition': item_definition}

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/dataPipelines/'
        + data_pipeline_id,
        method='post',
        payload=payload,
        params=params,
    )


@df
def create_data_pipeline(
    workspace: str,
    display_name: str,
    item_definition: Dict[str, Any],
    *,
    description: Optional[str] = None,
    folder: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Creates a new data_pipeline in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name of the data_pipeline.
        description (str, optional): A description for the data_pipeline.
        folder (str, optional): The folder to create the data_pipeline in.
        item_definition (Dict[str, Any]): The definition of the data_pipeline.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The created data_pipeline details.

    Examples:
        ```python
        create_data_pipeline(
            workspace='MyProjectWorkspace',
            display_name='SalesDataPipeline',
            item_definition={...},
            description='This is a sales data pipeline',
            folder='SalesDataPipelinesFolder'
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)

    payload = {
        'displayName': display_name,
        'definition': item_definition,
    }

    if folder:
        folder_id = resolve_folder(workspace_id, folder)
        if folder_id:
            payload['folderId'] = folder_id

    if description:
        payload['description'] = description

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/dataPipelines',
        method='post',
        payload=payload,
    )


def delete_data_pipeline(workspace: str, data_pipeline: str) -> None:
    """
    Deletes a data_pipeline from the specified workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        data_pipeline (str): The name or ID of the data_pipeline to delete.

    Returns:
        None: If the data_pipeline is successfully deleted.

    Examples:
        ```python
        delete_data_pipeline('MyProjectWorkspace', 'SalesDataPipeline')
        delete_data_pipeline('123e4567-e89b-12d3-a456-426614174000', 'SalesDataPipeline')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    data_pipeline_id = resolve_data_pipeline(workspace_id, data_pipeline)

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/dataPipelines/'
        + data_pipeline_id,
        method='delete',
    )
