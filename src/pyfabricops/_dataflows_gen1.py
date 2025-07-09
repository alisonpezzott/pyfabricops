import json
import logging
import os
import uuid

import pandas

from ._core import api_core_request
from ._decorators import df
from ._utils import (
    get_current_branch,
    is_valid_uuid,
    load_and_sanitize,
    read_json,
    write_json,
    write_single_line_json,
)
from ._workspaces import get_workspace, get_workspace_suffix, resolve_workspace

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


@df
def list_dataflows_gen1(
    workspace: str, *, df: bool = False, silent: bool = False
) -> list | pandas.DataFrame | None:
    """
    Lists all dataflows gen1 in the specified workspace.

    Args:
        workspace (str): The ID of the workspace.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.
        silent (bool, optional): Keyword-only. If True, suppresses warnings. Defaults to False.

    Returns:
        list | pandas.DataFrame | None: A list of dataflows if successful, otherwise None.

    Examples:
        ```python
        list_dataflows_gen1('MyProjectWorkspace')
        list_dataflows_gen1('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    response = api_core_request(
        audience='powerbi',
        endpoint=f'/groups/{workspace_id}/dataflows',
    )
    if not response.success:
        if not silent:
            logger.warning(f'{response.status_code}: {response.error}')
        return None
    return response.data.get('value', [])


def resolve_dataflow_gen1(workspace: str, dataflow: str) -> str | None:
    """
    Resolve a Power BI dataflow by its name.

    Args:
        workspace (str): The workspace name or ID.
        dataflow_name (str): The name of the dataflow.

    Returns:
        str: The resolved dataflow ID.

    Examples:
        ```python
        resolve_dataflow_gen1('MyProjectWorkspace', 'SalesDataflowGen1')
        resolve_dataflow_gen1('123e4567-e89b-12d3-a456-426614174000', 'SalesDataflowGen1')
        ```
    """
    if is_valid_uuid(dataflow):
        return dataflow

    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    dataflows = list_dataflows_gen1(workspace, df=False)
    for df in dataflows:
        if df['name'] == dataflow:
            return df['objectId']
    logger.warning(f"Dataflow '{dataflow}' not found.")
    return None


@df
def get_dataflow_gen1(
    workspace: str, dataflow: str, *, df: bool = False
) -> dict | pandas.DataFrame | None:
    """
    Resolve a Power BI dataflow by its name.

    Args:
        workspace (str): The workspace name or ID.
        dataflow_name (str): The name of the dataflow.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        str: The resolved dataflow ID.

    Examples:
        ```python
        get_dataflow_gen1('MyProjectWorkspace', 'SalesDataflowGen1')
        get_dataflow_gen1('123e4567-e89b-12d3-a456-426614174000', 'SalesDataflowGen1')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    dataflows = list_dataflows_gen1(workspace, df=False)
    if not dataflows:
        return None

    if is_valid_uuid(dataflow):
        for df in dataflows:
            if df['objectId'] == dataflow:
                return df
    else:
        for df in dataflows:
            if df['name'] == dataflow:
                return df

    logger.warning(f"Dataflow '{dataflow}' not found.")
    return None


def get_dataflow_gen1_definition(workspace: str, dataflow: str) -> dict | None:
    """
    Get the definition of a Power BI dataflow.

    Args:
        workspace (str): The workspace name or ID.
        dataflow (str): The dataflow name or ID.

    Returns:
        dict: The dataflow definition.

    Examples:
        ```python
        get_dataflow_gen1_definition('MyProjectWorkspace', 'SalesDataflowGen1')
        get_dataflow_gen1_definition('123e4567-e89b-12d3-a456-426614174000', 'SalesDataflowGen1')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    dataflow_id = resolve_dataflow_gen1(workspace_id, dataflow)
    if not dataflow_id:
        return None

    response = api_core_request(
        audience='powerbi',
        endpoint=f'/groups/{workspace_id}/dataflows/{dataflow_id}',
        method='get',
        return_raw=True,
    )
    if response.status_code != 200:
        logger.warning(
            f'{response.status_code}: {response.json().get("error", {})}'
        )
        return None
    else:
        return response.json()


def _serialize_dataflow_gen1_model(path: str) -> tuple[bytes, str]:
    """
    Prepares the body for a dataflow deployment by reading and serializing the model.json file.

    Args:
        dataflow_path (str): The path to the directory containing the model.json file.

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
    df_json = load_and_sanitize(os.path.join(path, 'model.json'))

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


def deploy_dataflow_gen1(workspace: str, path: str) -> bool | None:
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
        'nameConflict': 'CreateOrOverwrite',
    }

    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    response = api_core_request(
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
    logger.info(f'Dataflow deployed successfully.')
    return True


def takeover_dataflow_gen1(workspace: str, dataflow: str) -> bool | None:
    """
    Take over a dataflow in a workspace

    Args:
        workspace (str): The workspace name or ID.
        dataflow (str): The dataflow name or ID.

    Examples:
        ```python
        takeover_dataflow_gen1('MyProjectWorkspace', 'SalesDataflowGen1')
        takeover_dataflow_gen1('123e4567-e89b-12d3-a456-426614174000', 'SalesDataflowGen1')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    dataflow_id = resolve_dataflow_gen1(workspace_id, dataflow)
    if not dataflow_id:
        return None

    response = api_core_request(
        audience='powerbi',
        endpoint=f'/groups/{workspace_id}/dataflows/{dataflow_id}/Default.Takeover',
        method='post',
        return_raw=True,
    )

    return response


def export_dataflow_gen1(
    workspace: str,
    dataflow: str,
    project_path: str = None,
    workspace_path: str = 'workspace',
    update_config: bool = True,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
) -> bool | None:
    """
    Export a dataflow from a workspace to a file.

    Args:
        workspace (str): The workspace name or ID.
        dataflow (str): The dataflow name or ID.
        project_path (str, optional): The path to the project folder.
        workspace_path (str, optional): The path to the workspace folder.
        update_config (bool, optional): Whether to update the config file.
        config_path (str, optional): The path to the config file.
        branch (str, optional): The branch name.
        workspace_suffix (str, optional): The workspace suffix.
        branches_path (str, optional): The path to the branches folder.

    Returns:
        bool | None: True if the export was successful, False otherwise.

    Examples:
        ```python
        export_dataflow_gen1('MyProjectWorkspace', 'SalesDataflowGen1', project_path='path/to/project')
        export_dataflow_gen1('123e4567-e89b-12d3-a456-426614174000', 'SalesDataflowGen1', project_path='path/to/project')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    workspace_name = get_workspace(workspace_id).get('displayName')

    # Get the dataflow details
    dataflow_ = get_dataflow_gen1(workspace_id, dataflow)
    if not dataflow_:
        return None

    dataflow_id = dataflow_['objectId']
    dataflow_name = dataflow_['name']
    dataflow_description = dataflow_.get('description', '')

    definition_response = get_dataflow_gen1_definition(
        workspace=workspace_id,
        dataflow=dataflow_id,
    )

    if not definition_response:
        return None

    dataflow_name = dataflow_['name']
    dataflow_path = os.path.join(
        project_path, workspace_path, dataflow_name + '.Dataflow'
    )
    os.makedirs(dataflow_path, exist_ok=True)

    # Save the model as model.json inside the item folder in single-line format (Power BI portal format)
    model_json_path = os.path.join(dataflow_path, 'model.json')
    write_single_line_json(definition_response, model_json_path)

    logger.info(f'Exported dataflow {dataflow_name} to {dataflow_path}.')

    if not update_config:
        return None

    else:

        # Get branch
        branch = get_current_branch(branch)

        # Get the workspace suffix and treating the name
        workspace_suffix = get_workspace_suffix(
            branch, workspace_suffix, branches_path
        )
        workspace_name_without_suffix = workspace_name.split(workspace_suffix)[
            0
        ]

        # Try to read existing config.json
        if not config_path:
            config_path = os.path.join(project_path, 'config.json')
        try:
            existing_config = read_json(config_path)
            logger.info(
                f'Found existing config file at {config_path}, merging workspace config...'
            )
        except FileNotFoundError:
            logger.warning(
                f'No existing config found at {config_path}, creating a new one.'
            )
            existing_config = {}

        config = existing_config[branch][workspace_name_without_suffix]

        if 'dataflows_gen1' not in config:
            config['dataflows_gen1'] = {}
        if dataflow_name not in config['dataflows_gen1']:
            config['dataflows_gen1'][dataflow_name] = {}
        if 'id' not in config['dataflows_gen1'][dataflow_name]:
            config['dataflows_gen1'][dataflow_name]['id'] = dataflow_id
        if 'description' not in config['dataflows_gen1'][dataflow_name]:
            config['dataflows_gen1'][dataflow_name][
                'description'
            ] = dataflow_description

        # Update the config with the new dataflow details
        config['dataflows_gen1'][dataflow_name]['id'] = dataflow_id
        config['dataflows_gen1'][dataflow_name][
            'description'
        ] = dataflow_description

        # Saving the updated config back to the config file
        existing_config[branch][workspace_name_without_suffix] = config
        write_json(existing_config, config_path)


def export_all_dataflows_gen1(
    workspace: str,
    project_path: str,
    workspace_path: str = 'workspace',
    update_config: bool = True,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
) -> bool | None:
    """
    Export all dataflows from a workspace to a file.

    Args:
        workspace (str): The workspace name or ID.
        project_path (str): The path to the project folder.
        workspace_path (str): The path to the workspace folder.
        update_config (bool): Whether to update the config file.
        config_path (str): The path to the config file.
        branch (str): The branch name.
        workspace_suffix (str): The workspace suffix.
        branches_path (str): The path to the branches folder.

    Returns:
        bool | None: True if the export was successful, False otherwise.

    Examples:
        ```python
        export_all_dataflows_gen1('MyProjectWorkspace', project_path='path/to/project')
        export_all_dataflows_gen1('123e4567-e89b-12d3-a456-426614174000', project_path='path/to/project')
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
                workspace=workspace,
                dataflow=dataflow['objectId'],
                project_path=project_path,
                workspace_path=workspace_path,
                update_config=update_config,
                config_path=config_path,
                branch=branch,
                workspace_suffix=workspace_suffix,
                branches_path=branches_path,
            )
