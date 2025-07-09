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
    parse_tmdl_parameters,
    read_json,
    unpack_item_definition,
    write_json,
)
from ._workspaces import get_workspace, resolve_workspace

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


@df
def list_semantic_models(
    workspace: str,
    excluded_starts: tuple = ('Staging', 'Lake', 'Ware'),
    *,
    df: bool = False,
) -> list | pandas.DataFrame:
    """
    Returns a list of semantic models from the specified workspace.
    This API supports pagination.

    Args:
        workspace (str): The workspace name or ID.
        excluded_starts (tuple): A tuple of prefixes to exclude from the list.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (list|pandas.DataFrame): A list of semantic models, excluding those that start with the specified prefixes. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        list_semantic_models('MyProjectWorkspace')
        list_semantic_models('MyProjectWorkspace', excluded_starts=('Staging', 'Lake'))
        ```

    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None
    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/semanticModels'
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        response = pagination_handler(response)

    # Filter out semantic models that start with the excluded prefixes
    semantic_models = [
        sm
        for sm in response.data.get('value')
        if not sm['displayName'].startswith(excluded_starts)
    ]
    if not semantic_models:
        logger.warning(
            f"No valid semantic models found in workspace '{workspace}'."
        )
        return None
    else:
        return semantic_models


def resolve_semantic_model(
    workspace: str, semantic_model: str, *, silent: bool = False
) -> str | None:
    """
    Resolves a semantic model name to its ID.

    Args:
        workspace (str): The name or ID of the workspace.
        semantic_model (str): The name or ID of the semantic model.
        silent (bool, optional): If True, suppresses warnings. Defaults to False.

    Returns:
        str: The ID of the semantic model, or None if not found.

    Examples:
        ```python
        resolve_semantic_model('MyProjectWorkspace', 'SalesDataModel')
        ```
    """
    if is_valid_uuid(semantic_model):
        return semantic_model

    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    semantic_models = list_semantic_models(workspace, df=False)
    if not semantic_models:
        return None

    for semantic_model_ in semantic_models:
        if semantic_model_['displayName'] == semantic_model:
            return semantic_model_['id']
    if not silent:
        logger.warning(f"Semantic model '{semantic_model}' not found.")
    return None


@df
def get_semantic_model(
    workspace: str, semantic_model: str, *, df: bool = False
) -> dict | pandas.DataFrame:
    """
    Retrieves a semantic model by its name or ID from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        semantic_model (str): The name or ID of the semantic model.

    Returns:
        (dict or pandas.DataFrame): The semantic model details if found. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        get_semantic_model('MyProjectWorkspace', 'SalesDataModel')
        get_semantic_model('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        get_semantic_model('123e4567-e89b-12d3-a456-426614174000', 'SalesDataModel', df=True)
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None
    semantic_model_id = resolve_semantic_model(workspace_id, semantic_model)
    if not semantic_model_id:
        return None
    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/semanticModels/{semantic_model_id}'
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


@df
def update_semantic_model(
    workspace: str,
    semantic_model: str,
    display_name: str = None,
    description: str = None,
    *,
    df: bool = False,
) -> dict | pandas.DataFrame:
    """
    Updates the properties of the specified semantic model.

    Args:
        workspace (str): The workspace name or ID.
        semantic_model (str): The name or ID of the semantic model to update.
        display_name (str, optional): The new display name for the semantic model.
        description (str, optional): The new description for the semantic model.

    Returns:
        (dict or None): The updated semantic model details if successful, otherwise None.

    Examples:
        ```python
        update_semantic_model('MyProjectWorkspace', 'SalesDataModel', display_name='UpdatedSalesDataModel')
        update_semantic_model('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', description='Updated description')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    semantic_model_id = resolve_semantic_model(workspace_id, semantic_model)
    if not semantic_model_id:
        return None

    semantic_model_ = get_semantic_model(workspace_id, semantic_model_id)
    if not semantic_model_:
        return None

    semantic_model_description = semantic_model_['description']
    semantic_model_display_name = semantic_model_['displayName']

    payload = {}

    if semantic_model_display_name != display_name and display_name:
        payload['displayName'] = display_name

    if semantic_model_description != description and description:
        payload['description'] = description

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/semanticModels/{semantic_model_id}',
        method='put',
        payload=payload,
    )

    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


def delete_semantic_model(workspace: str, semantic_model: str) -> None:
    """
    Delete a semantic model from the specified workspace.

    Args:
        workspace (str): The name or ID of the workspace to delete.
        semantic_model (str): The name or ID of the semantic model to delete.

    Returns:
        None: If the semantic model is successfully deleted.

    Raises:
        ResourceNotFoundError: If the specified workspace is not found.

    Examples:
        ```python
        delete_semantic_model('MyProjectWorkspace', 'SalesDataModel')
        delete_semantic_model('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    semantic_model_id = resolve_semantic_model(workspace_id, semantic_model)
    if not semantic_model_id:
        return None

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/semanticModels/{semantic_model_id}',
        method='delete',
        return_raw=True,
    )
    if not response.status_code == 200:
        logger.warning(f'{response.status_code}: {response.text}.')
        return False
    else:
        return True


def get_semantic_model_definition(workspace: str, semantic_model: str) -> dict:
    """
    Retrieves the definition of a semantic model by its name or ID from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        semantic_model (str): The name or ID of the semantic model.

    Returns:
        (dict): The semantic model definition if found, otherwise None.

    Examples:
        ```python
        get_semantic_model_definition('MyProjectWorkspace', 'SalesDataModel')
        get_semantic_model_definition('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    # Resolving IDs
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    semantic_model_id = resolve_semantic_model(workspace_id, semantic_model)
    if not semantic_model_id:
        return None

    # Requesting
    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/semanticModels/{semantic_model_id}/getDefinition',
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


def update_semantic_model_definition(
    workspace: str, semantic_model: str, path: str
) -> None:
    """
    Updates the definition of an existing semantic model in the specified workspace.
    If the semantic model does not exist, it returns None.

    Args:
        workspace (str): The workspace name or ID.
        semantic_model (str): The name or ID of the semantic model to update.
        path (str): The path to the semantic model.

    Returns:
        (dict or None): The updated semantic model details if successful, otherwise None.

    Examples:
        ```python
        update_semantic_model('MyProjectWorkspace', 'SalesDataModel', display_name='UpdatedSalesDataModel')
        update_semantic_model('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', description='Updated description')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    semantic_model_id = resolve_semantic_model(workspace_id, semantic_model)
    if not semantic_model_id:
        return None

    definition = pack_item_definition(path)

    params = {'updateMetadata': True}

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/semanticModels/{semantic_model_id}/updateDefinition',
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


def create_semantic_model(
    workspace: str,
    display_name: str,
    path: str,
    description: str = None,
    folder: str = None,
) -> None:
    """
    Creates a new semantic model in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name of the semantic model.
        description (str, optional): A description for the semantic model.
        folder (str, optional): The folder to create the semantic model in.
        path (str): The path to the semantic model definition file.

    Returns:
        (dict): The created semantic model details.

    Examples:
        ```python
        create_semantic_model('MyProjectWorkspace', 'SalesDataModel', 'path/to/definition/file', description='Sales data model')
        create_semantic_model('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', 'path/to/definition/file', folder='Sales')
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
        endpoint=f'/workspaces/{workspace_id}/semanticModels',
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


def export_semantic_model(
    workspace: str,
    semantic_model: str,
    project_path: str,
    workspace_path: str = 'workspace',
    update_config: bool = True,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
) -> None:
    """
    Exports a semantic model definition to a specified folder structure.

    Args:
        workspace (str): The workspace name or ID.
        semantic_model (str): The name of the semantic model to export.
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
        export_semantic_model('MyProjectWorkspace', 'SalesDataModel', 'path/to/project', workspace_path='workspace', config_path='config.json', branches_path='branches', branch='main', workspace_suffix='dev')
        export_semantic_model('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', 'path/to/project', workspace_path='workspace', config_path='config.json', branches_path='branches', branch='main', workspace_suffix='dev')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    workspace_name = get_workspace(workspace_id).get('displayName')
    if not workspace_id:
        return None

    semantic_model_ = get_semantic_model(workspace_id, semantic_model)
    if not semantic_model_:
        return None

    semantic_model_id = semantic_model_['id']
    folder_id = None
    if 'folderId' in semantic_model_:
        folder_id = semantic_model_['folderId']

    definition = get_semantic_model_definition(workspace_id, semantic_model_id)
    if not definition:
        return None

    semantic_model_name = semantic_model_['displayName']

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

        semantic_model_descr = semantic_model_.get('description', '')

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
            definition, f'{item_path}/{semantic_model_name}.SemanticModel'
        )

        if 'semantic_models' not in config:
            config['semantic_models'] = {}
        if semantic_model_name not in config['semantic_models']:
            config['semantic_models'][semantic_model_name] = {}
        if 'id' not in config['semantic_models'][semantic_model_name]:
            config['semantic_models'][semantic_model_name][
                'id'
            ] = semantic_model_id
        if 'description' not in config['semantic_models'][semantic_model_name]:
            config['semantic_models'][semantic_model_name][
                'description'
            ] = semantic_model_descr

        if folder_id:
            if (
                'folder_id'
                not in config['semantic_models'][semantic_model_name]
            ):
                config['semantic_models'][semantic_model_name][
                    'folder_id'
                ] = folder_id

        expressions_path = f'{item_path}/{semantic_model_name}.SemanticModel/definition/expressions.tmdl'
        tmdl_parameters = parse_tmdl_parameters(expressions_path)

        if 'parameters' not in config['semantic_models'][semantic_model_name]:
            config['semantic_models'][semantic_model_name][
                'parameters'
            ] = tmdl_parameters['parameters']

        # Update the config with the semantic model details
        config['semantic_models'][semantic_model_name][
            'id'
        ] = semantic_model_id
        config['semantic_models'][semantic_model_name][
            'description'
        ] = semantic_model_descr
        config['semantic_models'][semantic_model_name]['folder_id'] = folder_id
        config['semantic_models'][semantic_model_name][
            'parameters'
        ] = tmdl_parameters['parameters']

        # Saving the updated config back to the config file
        existing_config[branch][workspace_name_without_suffix] = config
        write_json(existing_config, config_path)

    else:
        unpack_item_definition(
            definition,
            f'{project_path}/{workspace_path}/{semantic_model_name}.SemanticModel',
        )


def export_all_semantic_models(
    workspace: str,
    project_path: str,
    workspace_path: str = 'workspace',
    update_config: bool = True,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
    excluded_starts: tuple = ('Staging', 'Lake', 'Ware'),
) -> None:
    """
    Exports all semantic models to the specified folder structure.

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
        export_all_semantic_models('MyProjectWorkspace', 'path/to/project', workspace_path='workspace', config_path='config.json', branches_path='branches', branch='main', workspace_suffix='dev')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    semantic_models = list_semantic_models(
        workspace_id, excluded_starts=excluded_starts
    )
    if semantic_models:
        for semantic_model in semantic_models:
            export_semantic_model(
                workspace=workspace,
                semantic_model=semantic_model['displayName'],
                project_path=project_path,
                workspace_path=workspace_path,
                config_path=config_path,
                update_config=update_config,
                branch=branch,
                workspace_suffix=workspace_suffix,
                branches_path=branches_path,
            )


def deploy_semantic_model(
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
    Creates or updates a semantic model in Fabric based on local folder structure.
    Automatically detects the folder_id based on where the semantic model is located locally.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name of the semantic model.
        project_path (str): The root path of the project.
        workspace_path (str): The workspace folder name. Defaults to "workspace".
        config_path (str): The path to the config file. Defaults to "config.json".
        description (str, optional): A description for the semantic model.
        branch (str, optional): The branch name. Will be auto-detected if not provided.
        workspace_suffix (str, optional): The workspace suffix. Will be read from config if not provided.

    Returns:
        (dict or None): The updated semantic model details if successful, otherwise None.

    Examples:
        ```python
        update_semantic_model('MyProjectWorkspace', 'SalesDataModel', display_name='UpdatedSalesDataModel')
        update_semantic_model('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', description='Updated description')
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

    # Find where the semantic model is located locally
    semantic_model_folder_path = None
    semantic_model_full_path = None

    # Check if semantic model exists in workspace root
    root_path = f'{project_path}/{workspace_path}/{display_name}.SemanticModel'
    if os.path.exists(root_path):
        semantic_model_folder_path = workspace_path
        semantic_model_full_path = root_path
        logger.debug(f'Found semantic model in workspace root: {root_path}')
    else:
        # Search for the semantic model in subfolders (only once)
        base_search_path = f'{project_path}/{workspace_path}'
        logger.debug(
            f'Searching for {display_name}.SemanticModel in: {base_search_path}'
        )

        for root, dirs, files in os.walk(base_search_path):
            if f'{display_name}.SemanticModel' in dirs:
                semantic_model_full_path = os.path.join(
                    root, f'{display_name}.SemanticModel'
                )
                semantic_model_folder_path = os.path.relpath(
                    root, project_path
                ).replace('\\', '/')
                logger.debug(
                    f'Found semantic model in: {semantic_model_full_path}'
                )
                logger.debug(
                    f'Relative folder path: {semantic_model_folder_path}'
                )
                break

    if not semantic_model_folder_path or not semantic_model_full_path:
        logger.debug(
            f'Semantic model {display_name}.SemanticModel not found in local structure'
        )
        logger.debug(f'Searched in: {project_path}/{workspace_path}')
        return None

    # Determine folder_id based on local path
    folder_id = None

    # Para semantic models em subpastas, precisamos mapear o caminho da pasta pai
    if semantic_model_folder_path != workspace_path:
        # O semantic model está em uma subpasta, precisamos encontrar o folder_id
        # Remover o "workspace/" do início do caminho para obter apenas a estrutura de pastas
        folder_relative_path = semantic_model_folder_path.replace(
            f'{workspace_path}/', ''
        )

        logger.debug(
            f'Semantic model located in subfolder: {folder_relative_path}'
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
        logger.debug(f'Semantic model will be created in workspace root')

    # Create the definition
    definition = pack_item_definition(semantic_model_full_path)

    # Check if semantic model already exists (check only once)
    semantic_model_id = resolve_semantic_model(
        workspace_id, display_name, silent=True
    )

    if semantic_model_id:
        logger.info(
            f"Semantic model '{display_name}' already exists, updating..."
        )
        # Update existing semantic model
        payload = {'definition': definition}
        if description:
            payload['description'] = description

        response = api_core_request(
            endpoint=f'/workspaces/{workspace_id}/semanticModels/{semantic_model_id}/updateDefinition',
            method='post',
            payload=payload,
            params={'updateMetadata': True},
        )
        if response and response.error:
            logger.warning(
                f"Failed to update semantic model '{display_name}': {response.error}"
            )
            return None

        logger.info(f"Successfully updated semantic model '{display_name}'")
        return get_semantic_model(workspace_id, semantic_model_id)

    else:
        logger.info(f'Creating new semantic model: {display_name}')
        # Create new semantic model
        payload = {'displayName': display_name, 'definition': definition}
        if description:
            payload['description'] = description
        if folder_id:
            payload['folderId'] = folder_id

        response = api_core_request(
            endpoint=f'/workspaces/{workspace_id}/semanticModels',
            method='post',
            payload=payload,
        )
        if response and response.error:
            logger.warning(
                f"Failed to create semantic model '{display_name}': {response.error}"
            )
            return None

        logger.info(f"Successfully created semantic model '{display_name}'")
        return get_semantic_model(workspace_id, display_name)


def deploy_all_semantic_models(
    workspace: str,
    project_path: str,
    workspace_path: str = 'workspace',
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
) -> None:
    """
    Deploy all semantic models from a project path.
    Searches recursively through all folders to find .SemanticModel directories.

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
        deploy_all_semantic_models('MyProjectWorkspace', 'path/to/project', workspace_path='workspace', config_path='config.json', branches_path='branches', branch='main', workspace_suffix='dev')
        ```
    """
    base_path = f'{project_path}/{workspace_path}'

    if not os.path.exists(base_path):
        logger.error(f'Base path does not exist: {base_path}')
        return None

    # Find all semantic model folders recursively
    semantic_model_folders = []
    for root, dirs, files in os.walk(base_path):
        for dir_name in dirs:
            if dir_name.endswith('.SemanticModel'):
                full_path = os.path.join(root, dir_name)
                # Extract just the semantic model name (without .SemanticModel suffix)
                semantic_model_name = dir_name.replace('.SemanticModel', '')
                semantic_model_folders.append(
                    {
                        'name': semantic_model_name,
                        'path': full_path,
                        'relative_path': os.path.relpath(
                            full_path, project_path
                        ).replace('\\', '/'),
                    }
                )

    if not semantic_model_folders:
        logger.warning(f'No semantic model folders found in {base_path}')
        return None

    logger.debug(
        f'Found {len(semantic_model_folders)} semantic models to deploy:'
    )
    for sm in semantic_model_folders:
        logger.debug(f"  - {sm['name']} at {sm['relative_path']}")

    # Deploy each semantic model
    deployed_models = []
    for semantic_model_info in semantic_model_folders:
        try:
            logger.debug(
                f"Deploying semantic model: {semantic_model_info['name']}"
            )
            result = deploy_semantic_model(
                workspace=workspace,
                display_name=semantic_model_info['name'],
                project_path=project_path,
                workspace_path=workspace_path,
                config_path=config_path,
                branch=branch,
                workspace_suffix=workspace_suffix,
                branches_path=branches_path,
            )
            if result:
                deployed_models.append(semantic_model_info['name'])
                logger.debug(
                    f"Successfully deployed: {semantic_model_info['name']}"
                )
            else:
                logger.debug(
                    f"Failed to deploy: {semantic_model_info['name']}"
                )
        except Exception as e:
            logger.error(
                f"Error deploying {semantic_model_info['name']}: {str(e)}"
            )

    logger.info(
        f'Deployment completed. Successfully deployed {len(deployed_models)} semantic models.'
    )
    return deployed_models
