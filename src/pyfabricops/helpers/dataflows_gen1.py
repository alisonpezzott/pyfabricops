import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Union

from ..api.api import _base_api
from ..core.workspaces import resolve_workspace
from ..items.dataflows_gen1 import (
    get_dataflow_gen1,
    get_dataflow_gen1_definition,
    list_dataflows_gen1,
)
from ..utils.logging import get_logger
from ..utils.utils import (
    list_paths_of_type,
    load_and_sanitize,
    write_single_line_json,
)

logger = get_logger(__name__)


def get_dataflow_gen1_config(
    workspace: str, dataflow_gen1: str
) -> Union[Dict[str, Any], None]:
    """
    Get a specific dataflow_gen1 config from a workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        dataflow_gen1 (str): The name or ID of the dataflow_gen1.

    Returns:
        (Union[Dict[str, Any], None]): The dict config from the dataflow_gen1.
    """
    item = dataflow_gen1
    item_data = get_dataflow_gen1(workspace, item, df=False)

    if item_data is None:
        return None

    else:
        config = {}
        config = config[item_data.get('name')] = {}

        config = {
            'id': item_data['objectId'],
            'description': item_data.get('description', None),
            'folder_id': '',
        }

        return config


def get_all_dataflows_gen1_config(
    workspace: str,
) -> Union[Dict[str, Any], None]:
    """
    Get dataflows_gen1 config from a workspace.

    Args:
        workspace (str): The name or ID from the workspace.

    Returns:
        (Union[Dict[str, Any], None]): The dict config of all dataflows_gen1 in the workspace
    """
    items = list_dataflows_gen1(workspace, df=False)

    if items is None:
        return None

    config = {}

    for item in items:
        config[item['name']] = {
            'id': item['objectId'],
            'description': item.get('description', None),
            'folder_id': '',
        }

    return config


def export_dataflow_gen1(
    workspace: str,
    dataflow: str,
    path: str,
) -> None:
    """
    Export a dataflow from a workspace to a file.

    Args:
        workspace (str): The workspace name or ID.
        dataflow (str): The dataflow name or ID.
        path (str, optional): The path to the project folder.

    Examples:
        ```python
        export_dataflow_gen1('MyProjectWorkspace', 'SalesDataflowGen1', path='path/to/project')
        export_dataflow_gen1('123e4567-e89b-12d3-a456-426614174000', 'SalesDataflowGen1', path='path/to/project')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    # Get the dataflow details
    dataflow_ = get_dataflow_gen1(workspace_id, dataflow)
    if not dataflow_:
        return None

    dataflow_id = dataflow_['objectId']
    dataflow_name = dataflow_['name']

    definition_response = get_dataflow_gen1_definition(
        workspace=workspace_id,
        dataflow=dataflow_id,
    )

    if not definition_response:
        return None

    dataflow_name = dataflow_['name']
    dataflow_path = Path(path) / dataflow_name + '.Dataflow'
    os.makedirs(dataflow_path, exist_ok=True)

    # Save the model as model.json inside the item folder in single-line format (Power BI portal format)
    model_json_path = dataflow_path / 'model.json'
    write_single_line_json(definition_response, model_json_path)

    logger.success(f'Exported dataflow {dataflow_name} to {dataflow_path}.')
    return None


def export_all_dataflows_gen1(
    workspace: str,
    path: str,
) -> None:
    """
    Export all dataflows gen1 from a workspace to a file.

    Args:
        workspace (str): The workspace name or ID.
        path (str): The path to the project folder.

    Examples:
        ```python
        export_all_dataflows_gen1('MyProjectWorkspace', path='path/to/project')
        export_all_dataflows_gen1('123e4567-e89b-12d3-a456-426614174000', path='path/to/project')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    dataflows = list_dataflows_gen1(workspace_id, df=False)

    if not dataflows:
        return None
    else:
        for dataflow in dataflows:
            export_dataflow_gen1(
                workspace=workspace, dataflow=dataflow['objectId'], path=path
            )
        return None


def _serialize_dataflow_gen1_model(path: str) -> tuple[bytes, str]:
    """
    Prepares the body for a dataflow deployment by reading and serializing the model.json file.

    Args:
        path (str): The path to the directory containing the model.json file.

    Returns:
        tuple[bytes, str]: The serialized multipart body and the boundary string.

    Raises:
        UnicodeEncodeError: If there is an encoding issue with the JSON content.

    Examples:
        ```python
        _serialize_dataflow_gen1_model('path/to/MyDataflowGen1.Dataflow')
        ```
    """
    # Read and clean JSON using load_and_sanitize function
    df_json = load_and_sanitize(Path(path) / 'model.json')

    json_str = json.dumps(df_json, ensure_ascii=False, separators=(',', ':'))

    # Boundary setup
    boundary = uuid.uuid4().hex
    LF = '\r\n'

    # Serialized Json Body
    body = (
        f'--{boundary}{LF}'
        f'Content-Disposition: form-data; name="model.json"; filename="model.json"{LF}'
        f'Content-Type: application/json{LF}{LF}'
        f'{json_str}{LF}'
        f'--{boundary}--{LF}'
    )

    try:
        body.encode('utf-8')
    except UnicodeEncodeError as e:
        logger.error(f'Encoding error: {e}')
        raise
    return body.encode('utf-8'), boundary


def deploy_dataflow_gen1(workspace: str, path: str) -> Union[bool, None]:
    """
    Deploy a dataflow in a workspace from a model.json file

    Args:
        workspace (str): The workspace name or ID.
        path (str): Path to the model.json file for the dataflow.

    Returns:
        None

    Raises:
        Exception: If the API request fails or returns an error.

    Examples:
        ```python
        deploy_dataflow_gen1('MyProjectWorkspace', 'path/to/MyDataflowGen1.Dataflow')
        deploy_dataflow_gen1('123e4567-e89b-12d3-a456-426614174000', 'path/to/MyDataflowGen1.Dataflow')
        ```
    """
    # Read and clean JSON
    body, boundary = _serialize_dataflow_gen1_model(path)

    content_type = f'multipart/form-data; boundary={boundary}'

    params = {
        'datasetDisplayName': 'model.json',
        'nameConflict': 'Abort',
    }

    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    response = _base_api(
        audience='powerbi',
        endpoint=f'/groups/{workspace_id}/imports',
        content_type=content_type,
        credential_type='user',
        method='post',
        data=body,
        params=params,
        return_raw=True,
    )
    # Handle response
    if not response.status_code in (200, 202):
        logger.error(
            f'Error deploying the dataflow: {response.status_code} - {response.json().get("error", {})}'
        )
        return None
    logger.success(f'Dataflow deployed successfully.')
    return True


def deploy_all_dataflows_gen1(
    workspace: str,
    path: str,
    start_path: Optional[str] = None,
) -> None:
    """
    Deploy all dataflows_gen1 to workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        path (str): The path to the dataflows_gen2.
        start_path (Optional[str]): The starting path for folder creation.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    dataflows_gen2_paths = list_paths_of_type(path, 'Dataflow')

    for path_ in dataflows_gen2_paths:

        deploy_dataflow_gen1(workspace_id, path_)

    logger.success(
        f'All dataflows_gen1 were deployed to workspace "{workspace}" successfully.'
    )
    return None
