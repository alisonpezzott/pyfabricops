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
def list_notebooks(
    workspace: str, *, df: bool = False
) -> list | pandas.DataFrame | None:
    """
    Lists all notebooks in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (list | pandas.DataFrame | None): A list of notebooks, a DataFrame with flattened keys, or None if not found.

    Examples:
        ```python
        list_notebooks('MyProjectWorkspace')
        list_notebooks('MyProjectWorkspace', df=True)
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None
    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/notebooks'
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        response = pagination_handler(response)
        return response.data.get('value')


def resolve_notebook(
    workspace: str, notebook: str, *, silent: bool = False
) -> str | None:
    """
    Resolves a notebook name to its ID.

    Args:
        workspace (str): The ID of the workspace.
        notebook (str): The name of the notebook.
        silent (bool): If True, suppresses warnings. Defaults to False.

    Returns:
        str | None: The ID of the notebook, or None if not found.

    Examples:
        ```python
        resolve_notebook('MyProjectWorkspace', 'SalesDataNotebook')
        ```
    """
    if is_valid_uuid(notebook):
        return notebook

    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    notebooks = list_notebooks(workspace, df=False)
    if not notebooks:
        return None

    for notebook_ in notebooks:
        if notebook_['displayName'] == notebook:
            return notebook_['id']
    if not silent:
        logger.warning(f"Notebook '{notebook}' not found.")
    return None


@df
def get_notebook(
    workspace: str, notebook: str, *, df: bool = False
) -> dict | pandas.DataFrame | None:
    """
    Retrieves a notebook by its name or ID from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        notebook (str): The name or ID of the notebook.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame): The notebook details if found. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        get_notebook('MyProjectWorkspace', 'SalesDataNotebook')
        get_notebook('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', df=True)
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    notebook_id = resolve_notebook(workspace_id, notebook)
    if not notebook_id:
        return None

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/notebooks/{notebook_id}'
    )

    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


@df
def update_notebook(
    workspace: str,
    notebook: str,
    display_name: str = None,
    description: str = None,
    *,
    df: bool = False,
) -> dict | pandas.DataFrame:
    """
    Updates the properties of the specified notebook.

    Args:
        workspace (str): The workspace name or ID.
        notebook (str): The name or ID of the notebook to update.
        display_name (str, optional): The new display name for the notebook.
        description (str, optional): The new description for the notebook.

    Returns:
        (dict or None): The updated notebook details if successful, otherwise None.

    Examples:
        ```python
        update_notebook('MyProjectWorkspace', 'SalesDataModel', display_name='UpdatedSalesDataModel')
        update_notebook('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', description='Updated description')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    notebook_id = resolve_notebook(workspace_id, notebook)
    if not notebook_id:
        return None

    notebook_ = get_notebook(workspace_id, notebook_id)
    if not notebook_:
        return None

    notebook_description = notebook_['description']
    notebook_display_name = notebook_['displayName']

    payload = {}

    if notebook_display_name != display_name and display_name:
        payload['displayName'] = display_name

    if notebook_description != description and description:
        payload['description'] = description

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/notebooks/{notebook_id}',
        method='put',
        payload=payload,
    )

    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


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
    if not workspace_id:
        return None

    notebook_id = resolve_notebook(workspace_id, notebook)
    if not notebook_id:
        return None

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/notebooks/{notebook_id}',
        method='delete',
        return_raw=True,
    )
    if not response.status_code == 200:
        logger.warning(f'{response.status_code}: {response.text}.')
        return False
    else:
        return True


def get_notebook_definition(workspace: str, notebook: str) -> dict:
    """
    Retrieves the definition of a notebook by its name or ID from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        notebook (str): The name or ID of the notebook.

    Returns:
        (dict): The notebook definition if found, otherwise None.

    Examples:
        ```python
        get_notebook_definition('MyProjectWorkspace', 'Salesnotebook')
        get_notebook_definition('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    # Resolving IDs
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    notebook_id = resolve_notebook(workspace_id, notebook)
    if not notebook_id:
        return None

    # Requesting
    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/notebooks/{notebook_id}/getDefinition',
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


def update_notebook_definition(
    workspace: str, notebook: str, path: str
) -> dict | None:
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
    if not workspace_id:
        return None

    notebook_id = resolve_notebook(workspace_id, notebook)
    if not notebook_id:
        return None

    definition = pack_item_definition(path)

    params = {'updateMetadata': True}

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/notebooks/{notebook_id}/updateDefinition',
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


def create_notebook(
    workspace: str,
    display_name: str,
    path: str,
    description: str = None,
    folder: str = None,
) -> dict | None:
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
        endpoint=f'/workspaces/{workspace_id}/notebooks',
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


def export_notebook(
    workspace: str,
    notebook: str,
    project_path: str,
    workspace_path: str = 'workspace',
    update_config: bool = True,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
) -> None:
    """
    Exports a notebook definition to a specified folder structure.

    Args:
        workspace (str): The workspace name or ID.
        notebook (str): The name of the notebook to export.
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
        export_notebook('MyProjectWorkspace', 'SalesDataModel', 'path/to/project')
        export_notebook('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', 'path/to/project')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    workspace_name = get_workspace(workspace_id).get('displayName')
    if not workspace_id:
        return None

    notebook_ = get_notebook(workspace_id, notebook)
    if not notebook_:
        return None

    notebook_id = notebook_['id']
    folder_id = None
    if 'folderId' in notebook_:
        folder_id = notebook_['folderId']

    definition = get_notebook_definition(workspace_id, notebook_id)
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

        notebook_id = notebook_['id']
        notebook_name = notebook_['displayName']
        notebook_descr = notebook_.get('description', '')

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
            definition, f'{item_path}/{notebook_name}.Notebook'
        )

        if 'notebooks' not in config:
            config['notebooks'] = {}
        if notebook_name not in config['notebooks']:
            config['notebooks'][notebook_name] = {}
        if 'id' not in config['notebooks'][notebook_name]:
            config['notebooks'][notebook_name]['id'] = notebook_id
        if 'description' not in config['notebooks'][notebook_name]:
            config['notebooks'][notebook_name]['description'] = notebook_descr

        if folder_id:
            if 'folder_id' not in config['notebooks'][notebook_name]:
                config['notebooks'][notebook_name]['folder_id'] = folder_id

        # Update the config with the notebook details
        config['notebooks'][notebook_name]['id'] = notebook_id
        config['notebooks'][notebook_name]['description'] = notebook_descr
        config['notebooks'][notebook_name]['folder_id'] = folder_id

        # Saving the updated config back to the config file
        existing_config[branch][workspace_name_without_suffix] = config
        write_json(existing_config, config_path)

    else:
        unpack_item_definition(
            definition,
            f'{project_path}/{workspace_path}/{notebook_name}.Notebook',
        )


def export_all_notebooks(
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
    Exports all notebooks to the specified folder structure.

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
        export_all_notebooks('MyProjectWorkspace', 'path/to/project')
        export_all_notebooks('MyProjectWorkspace', 'path/to/project', branch='main')
        export_all_notebooks('MyProjectWorkspace', 'path/to/project', workspace_suffix='Workspace')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    notebooks = list_notebooks(workspace_id)
    if notebooks:
        for notebook in notebooks:
            export_notebook(
                workspace=workspace,
                notebook=notebook['displayName'],
                project_path=project_path,
                workspace_path=workspace_path,
                update_config=update_config,
                config_path=config_path,
                branch=branch,
                workspace_suffix=workspace_suffix,
                branches_path=branches_path,
            )


def deploy_notebook(
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
    Creates or updates a notebook in Fabric based on local folder structure.
    Automatically detects the folder_id based on where the notebook is located locally.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name of the notebook.
        project_path (str): The root path of the project.
        workspace_path (str): The workspace folder name. Defaults to "workspace".
        config_path (str): The path to the config file. Defaults to "config.json".
        description (str, optional): A description for the notebook.
        branch (str, optional): The branch name. Will be auto-detected if not provided.
        workspace_suffix (str, optional): The workspace suffix. Will be read from config if not provided.

    Examples:
        ```python
        deploy_notebook('MyProjectWorkspace', 'SalesDataModel', 'path/to/project')
        deploy_notebook('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', 'path/to/project')
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

    # Find where the notebook is located locally
    notebook_folder_path = None
    notebook_full_path = None

    # Check if notebook exists in workspace root
    root_path = f'{project_path}/{workspace_path}/{display_name}.notebook'
    if os.path.exists(root_path):
        notebook_folder_path = workspace_path
        notebook_full_path = root_path
        logger.debug(f'Found notebook in workspace root: {root_path}')
    else:
        # Search for the notebook in subfolders (only once)
        base_search_path = f'{project_path}/{workspace_path}'
        logger.debug(
            f'Searching for {display_name}.notebook in: {base_search_path}'
        )

        for root, dirs, files in os.walk(base_search_path):
            if f'{display_name}.notebook' in dirs:
                notebook_full_path = os.path.join(
                    root, f'{display_name}.notebook'
                )
                notebook_folder_path = os.path.relpath(
                    root, project_path
                ).replace('\\', '/')
                logger.debug(f'Found notebook in: {notebook_full_path}')
                logger.debug(f'Relative folder path: {notebook_folder_path}')
                break

    if not notebook_folder_path or not notebook_full_path:
        logger.debug(
            f'notebook {display_name}.notebook not found in local structure'
        )
        logger.debug(f'Searched in: {project_path}/{workspace_path}')
        return None

    # Determine folder_id based on local path
    folder_id = None

    # Para notebooks em subpastas, precisamos mapear o caminho da pasta pai
    if notebook_folder_path != workspace_path:
        # O notebook está em uma subpasta, precisamos encontrar o folder_id
        # Remover o "workspace/" do início do caminho para obter apenas a estrutura de pastas
        folder_relative_path = notebook_folder_path.replace(
            f'{workspace_path}/', ''
        )

        logger.debug(f'notebook located in subfolder: {folder_relative_path}')

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
        logger.debug(f'notebook will be created in workspace root')

    # Create the definition
    definition = pack_item_definition(notebook_full_path)

    # Check if notebook already exists (check only once)
    notebook_id = resolve_notebook(workspace_id, display_name, silent=True)

    if notebook_id:
        logger.info(f"notebook '{display_name}' already exists, updating...")
        # Update existing notebook
        payload = {'definition': definition}
        if description:
            payload['description'] = description

        response = api_core_request(
            endpoint=f'/workspaces/{workspace_id}/notebooks/{notebook_id}/updateDefinition',
            method='post',
            payload=payload,
            params={'updateMetadata': True},
        )
        if response and response.error:
            logger.warning(
                f"Failed to update notebook '{display_name}': {response.error}"
            )
            return None

        logger.info(f"Successfully updated notebook '{display_name}'")
        return get_notebook(workspace_id, notebook_id)

    else:
        logger.info(f'Creating new notebook: {display_name}')
        # Create new notebook
        payload = {'displayName': display_name, 'definition': definition}
        if description:
            payload['description'] = description
        if folder_id:
            payload['folderId'] = folder_id

        response = api_core_request(
            endpoint=f'/workspaces/{workspace_id}/notebooks',
            method='post',
            payload=payload,
        )
        if response and response.error:
            logger.warning(
                f"Failed to create notebook '{display_name}': {response.error}"
            )
            return None

        logger.info(f"Successfully created notebook '{display_name}'")
        return get_notebook(workspace_id, display_name)


def deploy_all_notebooks(
    workspace: str,
    project_path: str,
    workspace_path: str = 'workspace',
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
) -> list[str] | None:
    """
    Deploy all notebooks from a project path.
    Searches recursively through all folders to find .Notebook directories.

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
        deploy_all_notebooks('MyProjectWorkspace', 'path/to/project')
        deploy_all_notebooks('MyProjectWorkspace', 'path/to/project', branch='main')
        deploy_all_notebooks('MyProjectWorkspace', 'path/to/project', workspace_suffix='Workspace')
        ```
    """
    base_path = f'{project_path}/{workspace_path}'

    if not os.path.exists(base_path):
        logger.error(f'Base path does not exist: {base_path}')
        return None

    # Find all notebook folders recursively
    notebook_folders = []
    for root, dirs, files in os.walk(base_path):
        for dir_name in dirs:
            if dir_name.endswith('.notebook'):
                full_path = os.path.join(root, dir_name)
                # Extract just the notebook name (without .notebook suffix)
                notebook_name = dir_name.replace('.notebook', '')
                notebook_folders.append(
                    {
                        'name': notebook_name,
                        'path': full_path,
                        'relative_path': os.path.relpath(
                            full_path, project_path
                        ).replace('\\', '/'),
                    }
                )

    if not notebook_folders:
        logger.warning(f'No notebook folders found in {base_path}')
        return None

    logger.debug(f'Found {len(notebook_folders)} notebooks to deploy:')
    for notebook in notebook_folders:
        logger.debug(f"  - {notebook['name']} at {notebook['relative_path']}")

    # Deploy each notebook
    deployed_notebooks = []
    for notebook_info in notebook_folders:
        try:
            logger.debug(f"Deploying notebook: {notebook_info['name']}")
            result = deploy_notebook(
                workspace=workspace,
                display_name=notebook_info['name'],
                project_path=project_path,
                workspace_path=workspace_path,
                config_path=config_path,
                branch=branch,
                workspace_suffix=workspace_suffix,
                branches_path=branches_path,
            )
            if result:
                deployed_notebooks.append(notebook_info['name'])
                logger.debug(f"Successfully deployed: {notebook_info['name']}")
            else:
                logger.debug(f"Failed to deploy: {notebook_info['name']}")
        except Exception as e:
            logger.error(f"Error deploying {notebook_info['name']}: {str(e)}")

    logger.info(
        f'Deployment completed. Successfully deployed {len(deployed_notebooks)} notebooks.'
    )
    return deployed_notebooks
