import logging
import os

import pandas

from ._core import api_core_request, lro_handler, pagination_handler
from ._decorators import df
from ._folders import resolve_folder
from ._utils import (
    get_current_branch,
    get_workspace_suffix,
    is_valid_uuid,
    pack_item_definition,
    read_json,
    unpack_item_definition,
    write_json,
)
from ._workspaces import get_workspace, resolve_workspace

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


@df
def list_data_pipelines(
    workspace: str, *, df: bool = False
) -> list | pandas.DataFrame | None:
    """
    Lists all data_pipelines in the specified workspace.

    Args:
        workspace (str): The ID of the workspace.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        list | pandas.DataFrame | None: A list of data_pipelines if successful, otherwise None.

    Examples:
        ```python
        list_data_pipelines('MyProjectWorkspace')
        list_data_pipelines('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None
    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/dataPipelines'
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        response = pagination_handler(response)
        return response.data.get('value')


def resolve_data_pipeline(
    workspace: str, data_pipeline: str, *, silent: bool = False
) -> str | None:
    """
    Resolves a data_pipeline name to its ID.

    Args:
        workspace (str): The ID of the workspace.
        data_pipeline (str): The name of the data_pipeline.

    Returns:
        (str or None): The ID of the data_pipeline, or None if not found.

    Examples:
        ```python
        resolve_data_pipeline('MyProjectWorkspace', 'SalesDataPipeline')
        resolve_data_pipeline('123e4567-e89b-12d3-a456-426614174000', 'SalesDataPipeline')
        ```
    """
    if is_valid_uuid(data_pipeline):
        return data_pipeline

    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    data_pipelines = list_data_pipelines(workspace, df=False)
    if not data_pipelines:
        return None

    for data_pipeline_ in data_pipelines:
        if data_pipeline_['displayName'] == data_pipeline:
            return data_pipeline_['id']
    if not silent:
        logger.warning(f"DataPipeline '{data_pipeline}' not found.")
    return None


@df
def get_data_pipeline(
    workspace: str, data_pipeline: str, *, df: bool = False
) -> dict | pandas.DataFrame | None:
    """
    Retrieves the details of a specific data pipeline.

    Args:
        workspace (str): The ID of the workspace.
        data_pipeline (str): The name or ID of the data pipeline.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        dict | pandas.DataFrame | None: The data pipeline details if found, otherwise None.

    Examples:
        ```python
        get_data_pipeline('MyProjectWorkspace', 'SalesDataPipeline')
        get_data_pipeline('123e4567-e89b-12d3-a456-426614174000', 'SalesDataPipeline')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    data_pipeline_id = resolve_data_pipeline(workspace_id, data_pipeline)
    if not data_pipeline_id:
        return None

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/dataPipelines/{data_pipeline_id}'
    )

    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


@df
def update_data_pipeline(
    workspace: str,
    data_pipeline: str,
    display_name: str = None,
    description: str = None,
    *,
    df: bool = False,
) -> dict | pandas.DataFrame:
    """
    Updates the properties of the specified data pipeline.

    Args:
        workspace (str): The workspace name or ID.
        data_pipeline (str): The name or ID of the data_pipeline to update.
        display_name (str, optional): The new display name for the data_pipeline.
        description (str, optional): The new description for the data_pipeline.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or None): The updated data pipeline details if successful, otherwise None.

    Examples:
        ```python
        update_data_pipeline('MyProjectWorkspace', 'SalesDataModel', display_name='UpdatedSalesDataModel')
        update_data_pipeline('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', description='Updated description')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    data_pipeline_id = resolve_data_pipeline(workspace_id, data_pipeline)
    if not data_pipeline_id:
        return None

    data_pipeline_ = get_data_pipeline(workspace_id, data_pipeline_id)
    if not data_pipeline_:
        return None

    data_pipeline_description = data_pipeline_['description']
    data_pipeline_display_name = data_pipeline_['displayName']

    payload = {}

    if data_pipeline_display_name != display_name and display_name:
        payload['displayName'] = display_name

    if data_pipeline_description != description and description:
        payload['description'] = description

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/dataPipelines/{data_pipeline_id}',
        method='put',
        payload=payload,
    )

    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


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
    if not workspace_id:
        return None

    data_pipeline_id = resolve_data_pipeline(workspace_id, data_pipeline)
    if not data_pipeline_id:
        return None

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/dataPipelines/{data_pipeline_id}',
        method='delete',
        return_raw=True,
    )
    if not response.status_code == 200:
        logger.warning(f'{response.status_code}: {response.text}.')
        return False
    else:
        return True


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
    if not workspace_id:
        return None

    data_pipeline_id = resolve_data_pipeline(workspace_id, data_pipeline)
    if not data_pipeline_id:
        return None

    # Requesting
    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/dataPipelines/{data_pipeline_id}/getDefinition',
        method='post',
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    elif response.status_code == 202:
        # If the response is a long-running operation, handle it
        lro_response = lro_handler(response)
        if not lro_response.success:
            logger.warning(
                f'{lro_response.status_code}: {lro_response.error}.'
            )
            return None
        else:
            return lro_response.data
    elif response.status_code == 200:
        # If the response is successful, we can process it
        return response.data
    else:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None


def update_data_pipeline_definition(
    workspace: str, data_pipeline: str, path: str
):
    """
    Updates the definition of an existing data_pipeline in the specified workspace.
    If the data_pipeline does not exist, it returns None.

    Args:
        workspace (str): The workspace name or ID.
        data_pipeline (str): The name or ID of the data_pipeline to update.
        path (str): The path to the data_pipeline definition.

    Returns:
        (dict or None): The updated data_pipeline details if successful, otherwise None.

    Examples:
        ```python
        update_data_pipeline_definition('MyProjectWorkspace', 'SalesDataPipeline', './Project/workspace/SalesDataPipeline.DataPipeline')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    data_pipeline_id = resolve_data_pipeline(workspace_id, data_pipeline)
    if not data_pipeline_id:
        return None

    definition = pack_item_definition(path)

    params = {'updateMetadata': True}

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/dataPipelines/{data_pipeline_id}/updateDefinition',
        method='post',
        payload={'definition': definition},
        params=params,
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    elif response.status_code == 202:
        # If the response is a long-running operation, handle it
        lro_response = lro_handler(response)
        if not lro_response.success:
            logger.warning(
                f'{lro_response.status_code}: {lro_response.error}.'
            )
            return None
        else:
            return lro_response.data
    elif response.status_code == 200:
        # If the response is successful, we can process it
        return response.data
    else:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None


def create_data_pipeline(
    workspace: str,
    display_name: str,
    path: str,
    description: str = None,
    folder: str = None,
):
    """
    Creates a new data_pipeline in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name of the data_pipeline.
        description (str, optional): A description for the data_pipeline.
        folder (str, optional): The folder to create the data_pipeline in.
        path (str): The path to the data_pipeline definition file.

    Returns:
        (dict): The created data_pipeline details.

    Examples:
        ```python
        create_data_pipeline('MyProjectWorkspace', 'SalesDataPipeline', './Project/workspace/SalesDataPipeline.DataPipeline')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    definition = pack_item_definition(path)

    payload = {'displayName': display_name, 'definition': definition}

    if description:
        payload['description'] = description

    if folder:
        folder_id = resolve_folder(workspace_id, folder)
        if not folder_id:
            logger.warning(
                f"Folder '{folder}' not found in workspace {workspace_id}."
            )
        else:
            payload['folderId'] = folder_id

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/dataPipelines',
        method='post',
        payload=payload,
    )

    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    elif response.status_code == 202:
        # If the response is a long-running operation, handle it
        lro_response = lro_handler(response)
        if not lro_response.success:
            logger.warning(
                f'{lro_response.status_code}: {lro_response.error}.'
            )
            return None
        else:
            return lro_response.data
    elif response.status_code == 200:
        # If the response is successful, we can process it
        return response.data
    else:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None


def export_data_pipeline(
    workspace: str,
    data_pipeline: str,
    project_path: str,
    workspace_path: str = 'workspace',
    update_config: bool = True,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
):
    """
    Exports a data_pipeline definition to a specified folder structure.

    Args:
        workspace (str): The workspace name or ID.
        data_pipeline (str): The name of the data_pipeline to export.
        project_path (str): The root path of the project.
        workspace_path (str, optional): The path to the workspace folder. Defaults to "workspace".
        config_path (str): The path to the config file. Defaults to "config.json".
        branches_path (str): The path to the branches folder. Defaults to "branches".
        branch (str, optional): The branch name. Will be auto-detected if not provided.
        workspace_suffix (str, optional): The workspace suffix. Will be read from config if not provided.
        branches_path (str, optional): The path to the branches folder. Defaults to "branches".

    Returns:
        None

    Examples:
        ```python
        # Export a specific data_pipeline to the project structure with default config update
        export_data_pipeline(
            'MyProjectWorkspace',
            'SalesDataPipeline',
            './Project',
        )

        # Export a specific data_pipeline to the project structure without updating config
        export_data_pipeline(
            'MyProjectWorkspace',
            'SalesDataPipeline',
            './Project',
            workspace_path='other_workspace',
            update_config=False,
        )

        # Export a specific data_pipeline to the project structure with custom config path
        export_data_pipeline(
            'MyProjectWorkspace',
            'SalesDataPipeline',
            './Project',
            config_path='./Project/my_other_config.json'
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)
    workspace_name = get_workspace(workspace_id).get('displayName')
    if not workspace_id:
        return None

    data_pipeline_ = get_data_pipeline(workspace_id, data_pipeline)
    if not data_pipeline_:
        return None

    data_pipeline_id = data_pipeline_['id']
    folder_id = None
    if 'folderId' in data_pipeline_:
        folder_id = data_pipeline_['folderId']

    definition = get_data_pipeline_definition(workspace_id, data_pipeline_id)
    if not definition:
        return None

    if update_config:
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

        data_pipeline_id = data_pipeline_['id']
        data_pipeline_name = data_pipeline_['displayName']
        data_pipeline_descr = data_pipeline_.get('description', '')

        # Find the key in the folders dict whose value matches folder_id
        if folder_id:
            folders = config['folders']
            item_path = next(
                (k for k, v in folders.items() if v == folder_id), None
            )
            item_path = os.path.join(project_path, workspace_path, item_path)
        else:
            item_path = os.path.join(project_path, workspace_path)

        unpack_item_definition(
            definition, f'{item_path}/{data_pipeline_name}.DataPipeline'
        )

        if 'data_pipelines' not in config:
            config['data_pipelines'] = {}
        if data_pipeline_name not in config['data_pipelines']:
            config['data_pipelines'][data_pipeline_name] = {}
        if 'id' not in config['data_pipelines'][data_pipeline_name]:
            config['data_pipelines'][data_pipeline_name][
                'id'
            ] = data_pipeline_id
        if 'description' not in config['data_pipelines'][data_pipeline_name]:
            config['data_pipelines'][data_pipeline_name][
                'description'
            ] = data_pipeline_descr

        if folder_id:
            if 'folder_id' not in config['data_pipelines'][data_pipeline_name]:
                config['data_pipelines'][data_pipeline_name][
                    'folder_id'
                ] = folder_id

        # Update the config with the data_pipeline details
        config['data_pipelines'][data_pipeline_name]['id'] = data_pipeline_id
        config['data_pipelines'][data_pipeline_name][
            'description'
        ] = data_pipeline_descr
        config['data_pipelines'][data_pipeline_name]['folder_id'] = folder_id

        # Saving the updated config back to the config file
        existing_config[branch][workspace_name_without_suffix] = config
        write_json(existing_config, config_path)

    else:
        unpack_item_definition(
            definition,
            f'{project_path}/{workspace_path}/{data_pipeline_name}.DataPipeline',
        )


def export_all_data_pipelines(
    workspace: str,
    project_path: str,
    workspace_path: str = 'workspace',
    update_config: bool = True,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
):
    """
    Exports all data_pipelines to the specified folder structure.

    Args:
        workspace (str): The workspace name or ID.
        path (str): The root path of the project.
        config_path (str): The path to the config file. Defaults to "config.json".
        branch (str, optional): The branch name. Will be auto-detected if not provided.
        workspace_suffix (str, optional): The workspace suffix. Will be read from config if not provided.
        branches_path (str, optional): The path to the branches folder. Defaults to "branches".

    Returns:
        None

    Examples:
        ```python
        # Export all data_pipelines to the project structure with default config update
        export_all_data_pipelines(
            workspace='MyProjectWorkspace',
            project_path='./Project',
        )

        # Export all data_pipelines to the project structure without updating config
        export_all_data_pipelines(
            workspace='MyProjectWorkspace',
            project_path='./Project',
            update_config=False
        )

        # Export all data_pipelines to the project structure with custom config path
        export_all_data_pipelines(
            workspace='MyProjectWorkspace',
            project_path='./Project',
            config_path='./Project/my_other_config.json'
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    data_pipelines = list_data_pipelines(workspace_id)
    if data_pipelines:
        for data_pipeline in data_pipelines:
            export_data_pipeline(
                workspace=workspace,
                data_pipeline=data_pipeline['displayName'],
                project_path=project_path,
                workspace_path=workspace_path,
                update_config=update_config,
                config_path=config_path,
                branch=branch,
                workspace_suffix=workspace_suffix,
                branches_path=branches_path,
            )


def deploy_data_pipeline(
    workspace: str,
    display_name: str,
    project_path: str,
    workspace_path: str = 'workspace',
    config_path: str = None,
    description: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
):
    """
    Deploy a data_pipeline in Fabric based on local folder structure.
    Automatically detects the folder_id based on where the data_pipeline is located locally.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name of the data_pipeline.
        project_path (str): The root path of the project.
        workspace_path (str): The workspace folder name. Defaults to "workspace".
        config_path (str): The path to the config file. Defaults to "config.json".
        description (str, optional): A description for the data_pipeline.
        branch (str, optional): The branch name. Will be auto-detected if not provided.
        workspace_suffix (str, optional): The workspace suffix. Will be read from config if not provided.
        branches_path (str, optional): The path to the branches folder. Defaults to "branches".

    Returns:
        None

    Examples:
        ```python
        # Deploy a specific data_pipeline to the workspace
        deploy_data_pipeline(
            'MyProjectWorkspace',
            'SalesDataPipeline',
            './Project/workspace/SalesDataPipeline.DataPipeline'
        )

        # Deploy a specific data_pipeline to the workspace with custom config path
        deploy_data_pipeline(
            'MyProjectWorkspace',
            'SalesDataPipeline',
            './Project/workspace/SalesDataPipeline.DataPipeline',
            config_path='./Project/my_other_config.json'
        )

        # Deploy a specific data_pipeline to the workspace with custom branch and workspace suffix
        deploy_data_pipeline(
            'MyProjectWorkspace',
            'SalesDataPipeline',
            './Project/workspace/SalesDataPipeline.DataPipeline',
            branch='feature-branch',
            workspace_suffix='-feature',
            branches_path='./Project/branches'
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    workspace_name = get_workspace(workspace_id).get('displayName')

    # Auto-detect branch and workspace suffix
    if not branch:
        branch = get_current_branch()

    if not workspace_suffix:
        workspace_suffix = get_workspace_suffix(branch, None, branches_path)

    workspace_name_without_suffix = workspace_name.split(workspace_suffix)[0]

    # Read config to get folder mappings
    if not config_path:
        config_path = os.path.join(project_path, 'config.json')

    try:
        config_file = read_json(config_path)
        config = config_file.get(branch, {}).get(
            workspace_name_without_suffix, {}
        )
        folders_mapping = config.get('folders', {})
    except:
        logger.warning(
            'No config file found. Cannot determine folder structure.'
        )
        folders_mapping = {}

    # Find where the data pipeline is located locally
    data_pipeline_folder_path = None
    data_pipeline_full_path = None

    # Check if data_pipeline exists in workspace root
    root_path = f'{project_path}/{workspace_path}/{display_name}.data_pipeline'
    if os.path.exists(root_path):
        data_pipeline_folder_path = workspace_path
        data_pipeline_full_path = root_path
        logger.debug(f'Found data_pipeline in workspace root: {root_path}')
    else:
        # Search for the data_pipeline in subfolders (only once)
        base_search_path = f'{project_path}/{workspace_path}'
        logger.debug(
            f'Searching for {display_name}.data_pipeline in: {base_search_path}'
        )

        for root, dirs, files in os.walk(base_search_path):
            if f'{display_name}.data_pipeline' in dirs:
                data_pipeline_full_path = os.path.join(
                    root, f'{display_name}.data_pipeline'
                )
                data_pipeline_folder_path = os.path.relpath(
                    root, project_path
                ).replace('\\', '/')
                logger.debug(
                    f'Found data_pipeline in: {data_pipeline_full_path}'
                )
                logger.debug(
                    f'Relative folder path: {data_pipeline_folder_path}'
                )
                break

    if not data_pipeline_folder_path or not data_pipeline_full_path:
        logger.debug(
            f'data_pipeline {display_name}.data_pipeline not found in local structure'
        )
        logger.debug(f'Searched in: {project_path}/{workspace_path}')
        return None

    # Determine folder_id based on local path
    folder_id = None

    # Para data_pipelines em subpastas, precisamos mapear o caminho da pasta pai
    if data_pipeline_folder_path != workspace_path:
        # O data_pipeline está em uma subpasta, precisamos encontrar o folder_id
        # Remover o "workspace/" do início do caminho para obter apenas a estrutura de pastas
        folder_relative_path = data_pipeline_folder_path.replace(
            f'{workspace_path}/', ''
        )

        logger.debug(
            f'data_pipeline located in subfolder: {folder_relative_path}'
        )

        # Procurar nos mapeamentos de pastas
        if folder_relative_path in folders_mapping:
            folder_id = folders_mapping[folder_relative_path]
            logger.debug(
                f'Found folder mapping: {folder_relative_path} -> {folder_id}'
            )
        else:
            logger.debug(
                f'No folder mapping found for: {folder_relative_path}'
            )
            logger.debug(
                f'Available folder mappings: {list(folders_mapping.keys())}'
            )
    else:
        logger.debug(f'data_pipeline will be created in workspace root')

    # Create the definition
    definition = pack_item_definition(data_pipeline_full_path)

    # Check if data_pipeline already exists (check only once)
    data_pipeline_id = resolve_data_pipeline(
        workspace_id, display_name, silent=True
    )

    if data_pipeline_id:
        logger.info(
            f"data_pipeline '{display_name}' already exists, updating..."
        )
        # Update existing data_pipeline
        payload = {'definition': definition}
        if description:
            payload['description'] = description

        response = api_core_request(
            endpoint=f'/workspaces/{workspace_id}/dataPipelines/{data_pipeline_id}/updateDefinition',
            method='post',
            payload=payload,
            params={'updateMetadata': True},
        )
        if response and response.error:
            logger.warning(
                f"Failed to update data_pipeline '{display_name}': {response.error}"
            )
            return None

        logger.info(f"Successfully updated data_pipeline '{display_name}'")
        return get_data_pipeline(workspace_id, data_pipeline_id)

    else:
        logger.info(f'Creating new data_pipeline: {display_name}')
        # Create new data_pipeline
        payload = {'displayName': display_name, 'definition': definition}
        if description:
            payload['description'] = description
        if folder_id:
            payload['folderId'] = folder_id

        response = api_core_request(
            endpoint=f'/workspaces/{workspace_id}/dataPipelines',
            method='post',
            payload=payload,
        )
        if response and response.error:
            logger.warning(
                f"Failed to create data_pipeline '{display_name}': {response.error}"
            )
            return None

        logger.info(f"Successfully created data_pipeline '{display_name}'")
        return get_data_pipeline(workspace_id, display_name)


def deploy_all_data_pipelines(
    workspace: str,
    project_path: str,
    workspace_path: str = 'workspace',
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
):
    """
    Deploy all data pipelines from a project path.
    Searches recursively through all folders to find .DataPipeline directories.

    Args:
        workspace (str): The workspace name or ID.
        project_path (str): The root path of the project.
        workspace_path (str): The workspace folder name. Defaults to "workspace".
        config_path (str): The path to the config file. Defaults to "config.json".
        branch (str, optional): The branch name. Will be auto-detected if not provided.
        workspace_suffix (str, optional): The workspace suffix. Will be read from config if not provided.
        branches_path (str, optional): The path to the branches folder. Defaults to "branches".

    Returns:
        None

    Examples:
        ```python
        # Deploy all data_pipelines to the workspace
        deploy_all_data_pipelines(
            'MyProjectWorkspace',
            './Project',
            workspace_path='workspace',
            config_path='./Project/config.json'
        )

        # Deploy all data_pipelines to the workspace with custom branch and workspace suffix
        deploy_all_data_pipelines(
            'MyProjectWorkspace',
            './Project',
            branch='feature-branch',
            workspace_suffix='-feature',
            branches_path='./Project/branches'
        )
        ```
    """
    base_path = f'{project_path}/{workspace_path}'

    if not os.path.exists(base_path):
        logger.error(f'Base path does not exist: {base_path}')
        return None

    # Find all data_pipeline folders recursively
    data_pipeline_folders = []
    for root, dirs, files in os.walk(base_path):
        for dir_name in dirs:
            if dir_name.endswith('.data_pipeline'):
                full_path = os.path.join(root, dir_name)
                # Extract just the data_pipeline name (without .data_pipeline suffix)
                data_pipeline_name = dir_name.replace('.data_pipeline', '')
                data_pipeline_folders.append(
                    {
                        'name': data_pipeline_name,
                        'path': full_path,
                        'relative_path': os.path.relpath(
                            full_path, project_path
                        ).replace('\\', '/'),
                    }
                )

    if not data_pipeline_folders:
        logger.warning(f'No data_pipeline folders found in {base_path}')
        return None

    logger.debug(
        f'Found {len(data_pipeline_folders)} data_pipelines to deploy:'
    )
    for data_pipeline in data_pipeline_folders:
        logger.debug(
            f"  - {data_pipeline['name']} at {data_pipeline['relative_path']}"
        )

    # Deploy each data_pipeline
    deployed_data_pipelines = []
    for data_pipeline_info in data_pipeline_folders:
        try:
            logger.debug(
                f"Deploying data_pipeline: {data_pipeline_info['name']}"
            )
            result = deploy_data_pipeline(
                workspace=workspace,
                display_name=data_pipeline_info['name'],
                project_path=project_path,
                workspace_path=workspace_path,
                config_path=config_path,
                branch=branch,
                workspace_suffix=workspace_suffix,
                branches_path=branches_path,
            )
            if result:
                deployed_data_pipelines.append(data_pipeline_info['name'])
                logger.debug(
                    f"Successfully deployed: {data_pipeline_info['name']}"
                )
            else:
                logger.debug(f"Failed to deploy: {data_pipeline_info['name']}")
        except Exception as e:
            logger.error(
                f"Error deploying {data_pipeline_info['name']}: {str(e)}"
            )

    logger.info(
        f'Deployment completed. Successfully deployed {len(deployed_data_pipelines)} data_pipelines.'
    )
    return deployed_data_pipelines
