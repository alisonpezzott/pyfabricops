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
def list_dataflows(
    workspace: str, *, df: bool = False
) -> list | pandas.DataFrame | None:
    """
    Lists all dataflows in a workspace.

    Args:
        workspace (str): The workspace name or ID.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        list | pandas.DataFrame | None: A list of dataflows if successful, otherwise None.
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None
    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/dataflows'
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        response = pagination_handler(response)
        return response.data.get('value')


def resolve_dataflow(
    workspace: str, dataflow: str, *, silent: bool = False
) -> str | None:
    """
    Resolves a dataflow name to its ID.

    Args:
        workspace (str): The ID of the workspace.
        dataflow (str): The name of the dataflow.
        silent (bool, optional): If True, suppresses warnings. Defaults to False.

    Returns:
        str|None: The ID of the dataflow, or None if not found.

    Examples:
        ```python
        resolve_dataflow('MyProjectWorkspace', 'SalesDataflow')
        resolve_dataflow('123e4567-e89b-12d3-a456-426614174000', 'SalesDataflow')
        ```
    """
    if is_valid_uuid(dataflow):
        return dataflow

    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    dataflows = list_dataflows(workspace, df=False)
    if not dataflows:
        return None

    for dataflow_ in dataflows:
        if dataflow_['displayName'] == dataflow:
            return dataflow_['id']
    if not silent:
        logger.warning(f"Dataflow '{dataflow}' not found.")
    return None


@df
def get_dataflow(
    workspace: str, dataflow: str, *, df: bool = False
) -> dict | pandas.DataFrame | None:
    """
    Gets a dataflow by its name or ID.

    Args:
        workspace (str): The workspace name or ID.
        dataflow (str): The name or ID of the dataflow.
        df (bool, optional): If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        dict | pandas.DataFrame | None: The dataflow details if found, otherwise None.

    Examples:
        ```python
        get_dataflow('MyProjectWorkspace', 'SalesDataflow')
        get_dataflow('123e4567-e89b-12d3-a456-426614174000', 'SalesDataflow')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    dataflow_id = resolve_dataflow(workspace_id, dataflow)
    if not dataflow_id:
        return None

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/dataflows/{dataflow_id}'
    )

    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


@df
def update_dataflow(
    workspace: str,
    dataflow: str,
    display_name: str = None,
    description: str = None,
    *,
    df: bool = False,
) -> dict | pandas.DataFrame:
    """
    Updates the properties of the specified dataflow.

    Args:
        workspace (str): The workspace name or ID.
        dataflow (str): The name or ID of the dataflow to update.
        display_name (str, optional): The new display name for the dataflow.
        description (str, optional): The new description for the dataflow.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or None): The updated dataflow details if successful, otherwise None.

    Examples:
        ```python
        update_dataflow('MyProjectWorkspace', 'SalesDataModel', display_name='UpdatedSalesDataModel')
        update_dataflow('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', description='Updated description')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    dataflow_id = resolve_dataflow(workspace_id, dataflow)
    if not dataflow_id:
        return None

    dataflow_ = get_dataflow(workspace_id, dataflow_id)
    if not dataflow_:
        return None

    dataflow_description = dataflow_['description']
    dataflow_display_name = dataflow_['displayName']

    payload = {}

    if dataflow_display_name != display_name and display_name:
        payload['displayName'] = display_name

    if dataflow_description != description and description:
        payload['description'] = description

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/dataflows/{dataflow_id}',
        method='put',
        payload=payload,
    )

    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


def delete_dataflow(workspace: str, dataflow: str) -> None:
    """
    Delete a dataflow from the specified workspace.

    Args:
        workspace (str): The name or ID of the workspace to delete.
        dataflow (str): The name or ID of the dataflow to delete.

    Returns:
        None: If the dataflow is successfully deleted.

    Raises:
        ResourceNotFoundError: If the specified workspace is not found.

    Examples:
        ```python
        delete_dataflow('MyProjectWorkspace', 'SalesDataflow')
        delete_dataflow('123e4567-e89b-12d3-a456-426614174000', 'SalesDataflow')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    dataflow_id = resolve_dataflow(workspace_id, dataflow)
    if not dataflow_id:
        return None

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/dataflows/{dataflow_id}',
        method='delete',
        return_raw=True,
    )
    if not response.status_code == 200:
        logger.warning(f'{response.status_code}: {response.text}.')
        return False
    else:
        return True


def get_dataflow_definition(workspace: str, dataflow: str) -> dict:
    """
    Retrieves the definition of a dataflow by its name or ID from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        dataflow (str): The name or ID of the dataflow.

    Returns:
        (dict): The dataflow definition if found, otherwise None.

    Examples:
        ```python
        get_dataflow_definition('MyProjectWorkspace', 'Salesdataflow')
        get_dataflow_definition('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    # Resolving IDs
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    dataflow_id = resolve_dataflow(workspace_id, dataflow)
    if not dataflow_id:
        return None

    # Requesting
    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/dataflows/{dataflow_id}/getDefinition',
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


def update_dataflow_definition(
    workspace: str, dataflow: str, path: str
) -> dict | None:
    """
    Updates the definition of an existing dataflow in the specified workspace.
    If the dataflow does not exist, it returns None.

    Args:
        workspace (str): The workspace name or ID.
        dataflow (str): The name or ID of the dataflow to update.
        path (str): The path to the dataflow definition.

    Returns:
        (dict or None): The updated dataflow details if successful, otherwise None.

    Examples:
        ```python
        update_dataflow('MyProjectWorkspace', 'SalesDataModel', display_name='UpdatedSalesDataModel')
        update_dataflow('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', description='Updated description')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    dataflow_id = resolve_dataflow(workspace_id, dataflow)
    if not dataflow_id:
        return None

    definition = pack_item_definition(path)

    params = {'updateMetadata': True}

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/dataflows/{dataflow_id}/updateDefinition',
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


def create_dataflow(
    workspace: str,
    display_name: str,
    path: str,
    description: str = None,
    folder: str = None,
) -> dict | None:
    """
    Creates a new dataflow in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name of the dataflow.
        description (str, optional): A description for the dataflow.
        folder (str, optional): The folder to create the dataflow in.
        path (str): The path to the dataflow definition file.

    Returns:
        (dict): The created dataflow details.

    Examples:
        ```python
        create_dataflow('MyProjectWorkspace', 'SalesDataModel', 'path/to/definition.json')
        create_dataflow('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', 'path/to/definition.json', description='Sales data model')
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
        endpoint=f'/workspaces/{workspace_id}/dataflows',
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


def export_dataflow(
    workspace: str,
    dataflow: str,
    project_path: str,
    workspace_path: str = 'workspace',
    update_config: bool = True,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
) -> None:
    """
    Exports a dataflow definition to a specified folder structure.

    Args:
        workspace (str): The workspace name or ID.
        dataflow (str): The name of the dataflow to export.
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
        export_dataflow('MyProjectWorkspace', 'SalesDataModel', 'path/to/project')
        export_dataflow('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', 'path/to/project', branch='feature-branch')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    workspace_name = get_workspace(workspace_id).get('displayName')
    if not workspace_id:
        return None

    dataflow_ = get_dataflow(workspace_id, dataflow)
    if not dataflow_:
        return None

    dataflow_id = dataflow_['id']
    folder_id = None
    if 'folderId' in dataflow_:
        folder_id = dataflow_['folderId']

    definition = get_dataflow_definition(workspace_id, dataflow_id)
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

        dataflow_id = dataflow_['id']
        dataflow_name = dataflow_['displayName']
        dataflow_descr = dataflow_.get('description', '')

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
            definition, f'{item_path}/{dataflow_name}.Dataflow'
        )

        if 'dataflows' not in config:
            config['dataflows'] = {}
        if dataflow_name not in config['dataflows']:
            config['dataflows'][dataflow_name] = {}
        if 'id' not in config['dataflows'][dataflow_name]:
            config['dataflows'][dataflow_name]['id'] = dataflow_id
        if 'description' not in config['dataflows'][dataflow_name]:
            config['dataflows'][dataflow_name]['description'] = dataflow_descr

        if folder_id:
            if 'folder_id' not in config['dataflows'][dataflow_name]:
                config['dataflows'][dataflow_name]['folder_id'] = folder_id

        # Update the config with the dataflow details
        config['dataflows'][dataflow_name]['id'] = dataflow_id
        config['dataflows'][dataflow_name]['description'] = dataflow_descr
        config['dataflows'][dataflow_name]['folder_id'] = folder_id

        # Saving the updated config back to the config file
        existing_config[branch][workspace_name_without_suffix] = config
        write_json(existing_config, config_path)

    else:
        unpack_item_definition(
            definition,
            f'{project_path}/{workspace_path}/{dataflow_name}.Dataflow',
        )


def export_all_dataflows(
    workspace: str,
    project_path: str,
    workspace_path: str = 'workspace',
    update_config: bool = True,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
) -> None:
    """
    Exports all dataflows to the specified folder structure.

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
        export_all_dataflows('MyProjectWorkspace', 'path/to/project')
        export_all_dataflows('MyProjectWorkspace', 'path/to/project', branch='feature-branch')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    dataflows = list_dataflows(workspace_id)
    if dataflows:
        for dataflow in dataflows:
            export_dataflow(
                workspace=workspace,
                dataflow=dataflow['displayName'],
                project_path=project_path,
                workspace_path=workspace_path,
                update_config=update_config,
                config_path=config_path,
                branch=branch,
                workspace_suffix=workspace_suffix,
                branches_path=branches_path,
            )


def deploy_dataflow(
    workspace: str,
    display_name: str,
    project_path: str,
    workspace_path: str = 'workspace',
    config_path: str = None,
    description: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
) -> None:
    """
    Creates or updates a dataflow in Fabric based on local folder structure.
    Automatically detects the folder_id based on where the dataflow is located locally.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name of the dataflow.
        project_path (str): The root path of the project.
        workspace_path (str): The workspace folder name. Defaults to "workspace".
        config_path (str): The path to the config file. Defaults to "config.json".
        description (str, optional): A description for the dataflow.
        branch (str, optional): The branch name. Will be auto-detected if not provided.
        workspace_suffix (str, optional): The workspace suffix. Will be read from config if not provided.

    Returns:
        None

    Examples:
        ```python
        deploy_dataflow('MyProjectWorkspace', 'SalesDataModel', 'path/to/project')
        deploy_dataflow('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', 'path/to/project', description='Sales data model')
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

    # Find where the dataflow is located locally
    dataflow_folder_path = None
    dataflow_full_path = None

    # Check if dataflow exists in workspace root
    root_path = f'{project_path}/{workspace_path}/{display_name}.dataflow'
    if os.path.exists(root_path):
        dataflow_folder_path = workspace_path
        dataflow_full_path = root_path
        logger.debug(f'Found dataflow in workspace root: {root_path}')
    else:
        # Search for the dataflow in subfolders (only once)
        base_search_path = f'{project_path}/{workspace_path}'
        logger.debug(
            f'Searching for {display_name}.dataflow in: {base_search_path}'
        )

        for root, dirs, files in os.walk(base_search_path):
            if f'{display_name}.dataflow' in dirs:
                dataflow_full_path = os.path.join(
                    root, f'{display_name}.dataflow'
                )
                dataflow_folder_path = os.path.relpath(
                    root, project_path
                ).replace('\\', '/')
                logger.debug(f'Found dataflow in: {dataflow_full_path}')
                logger.debug(f'Relative folder path: {dataflow_folder_path}')
                break

    if not dataflow_folder_path or not dataflow_full_path:
        logger.debug(
            f'dataflow {display_name}.dataflow not found in local structure'
        )
        logger.debug(f'Searched in: {project_path}/{workspace_path}')
        return None

    # Determine folder_id based on local path
    folder_id = None

    # Para dataflows em subpastas, precisamos mapear o caminho da pasta pai
    if dataflow_folder_path != workspace_path:
        # O dataflow está em uma subpasta, precisamos encontrar o folder_id
        # Remover o "workspace/" do início do caminho para obter apenas a estrutura de pastas
        folder_relative_path = dataflow_folder_path.replace(
            f'{workspace_path}/', ''
        )

        logger.debug(f'dataflow located in subfolder: {folder_relative_path}')

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
        logger.debug(f'dataflow will be created in workspace root')

    # Create the definition
    definition = pack_item_definition(dataflow_full_path)

    # Check if dataflow already exists (check only once)
    dataflow_id = resolve_dataflow(workspace_id, display_name, silent=True)

    if dataflow_id:
        logger.info(f"dataflow '{display_name}' already exists, updating...")
        # Update existing dataflow
        payload = {'definition': definition}
        if description:
            payload['description'] = description

        response = api_core_request(
            endpoint=f'/workspaces/{workspace_id}/dataflows/{dataflow_id}/updateDefinition',
            method='post',
            payload=payload,
            params={'updateMetadata': True},
        )
        if response and response.error:
            logger.warning(
                f"Failed to update dataflow '{display_name}': {response.error}"
            )
            return None

        logger.info(f"Successfully updated dataflow '{display_name}'")
        return get_dataflow(workspace_id, dataflow_id)

    else:
        logger.info(f'Creating new dataflow: {display_name}')
        # Create new dataflow
        payload = {'displayName': display_name, 'definition': definition}
        if description:
            payload['description'] = description
        if folder_id:
            payload['folderId'] = folder_id

        response = api_core_request(
            endpoint=f'/workspaces/{workspace_id}/dataflows',
            method='post',
            payload=payload,
        )
        if response and response.error:
            logger.warning(
                f"Failed to create dataflow '{display_name}': {response.error}"
            )
            return None

        logger.info(f"Successfully created dataflow '{display_name}'")
        return get_dataflow(workspace_id, display_name)


def deploy_all_dataflows(
    workspace: str,
    project_path: str,
    workspace_path: str = 'workspace',
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
) -> None:
    """
    Deploy all dataflows from a project path.
    Searches recursively through all folders to find .Dataflow directories.

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
        deploy_all_dataflows('MyProjectWorkspace', 'path/to/project')
        deploy_all_dataflows('MyProjectWorkspace', 'path/to/project', branch='feature-branch')
        ```
    """
    base_path = f'{project_path}/{workspace_path}'

    if not os.path.exists(base_path):
        logger.error(f'Base path does not exist: {base_path}')
        return None

    # Find all dataflow folders recursively
    dataflow_folders = []
    for root, dirs, files in os.walk(base_path):
        for dir_name in dirs:
            if dir_name.endswith('.dataflow'):
                full_path = os.path.join(root, dir_name)
                # Extract just the dataflow name (without .dataflow suffix)
                dataflow_name = dir_name.replace('.dataflow', '')
                dataflow_folders.append(
                    {
                        'name': dataflow_name,
                        'path': full_path,
                        'relative_path': os.path.relpath(
                            full_path, project_path
                        ).replace('\\', '/'),
                    }
                )

    if not dataflow_folders:
        logger.warning(f'No dataflow folders found in {base_path}')
        return None

    logger.debug(f'Found {len(dataflow_folders)} dataflows to deploy:')
    for dataflow in dataflow_folders:
        logger.debug(f"  - {dataflow['name']} at {dataflow['relative_path']}")

    # Deploy each dataflow
    deployed_dataflows = []
    for dataflow_info in dataflow_folders:
        try:
            logger.debug(f"Deploying dataflow: {dataflow_info['name']}")
            result = deploy_dataflow(
                workspace=workspace,
                display_name=dataflow_info['name'],
                project_path=project_path,
                workspace_path=workspace_path,
                config_path=config_path,
                branch=branch,
                workspace_suffix=workspace_suffix,
                branches_path=branches_path,
            )
            if result:
                deployed_dataflows.append(dataflow_info['name'])
                logger.debug(f"Successfully deployed: {dataflow_info['name']}")
            else:
                logger.debug(f"Failed to deploy: {dataflow_info['name']}")
        except Exception as e:
            logger.error(f"Error deploying {dataflow_info['name']}: {str(e)}")

    logger.info(
        f'Deployment completed. Successfully deployed {len(deployed_dataflows)} dataflows.'
    )
    return deployed_dataflows
