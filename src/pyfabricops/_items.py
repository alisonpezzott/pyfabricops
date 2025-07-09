import logging
import os

import pandas

from ._core import api_core_request, lro_handler, pagination_handler
from ._decorators import df
from ._fabric_items import _FABRIC_ITEMS
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
def list_items(
    workspace: str, excluded_starts: tuple = ('Staging'), *, df: bool = False
) -> list | pandas.DataFrame:
    """
    Returns a list of items from the specified workspace.
    This API supports pagination.

    Args:
        workspace (str): The workspace name or ID.
        excluded_starts (tuple): A tuple of prefixes to exclude from the list.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (list|pandas.DataFrame): A list of items, excluding those that start with the specified prefixes. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        list_items('MyProjectWorkspace')
        list_items('MyProjectWorkspace', excluded_starts=('Staging', 'ware'))
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    response = api_core_request(endpoint=f'/workspaces/{workspace_id}/items')
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        response = pagination_handler(response)
    items = [
        item
        for item in response.data.get('value', [])
        if not item['displayName'].startswith(excluded_starts)
    ]
    if not items:
        logger.warning(f"No valid items found in workspace '{workspace}'.")
        return None
    else:
        return items


def resolve_item(
    workspace: str, item: str, *, silent: bool = False
) -> str | None:
    """
    Resolves a item name to its ID.

    Args:
        workspace (str): The ID of the workspace.
        item (str): The name of the item.
        silent (bool): If True, suppresses warnings. Defaults to False.

    Returns:
        str|None: The ID of the item, or None if not found.

    Examples:
        ```python
        resolve_item('MyProjectWorkspace', 'SalesDataModel')
        resolve_item('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    if is_valid_uuid(item):
        return item

    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    items = list_items(workspace, df=False)
    if not items:
        return None

    name = item.split('.')[0]
    type = item.split('.')[-1]
    if not name or not type:
        if not silent:
            logger.warning(
                f"Invalid item format '{item}'. Expected 'Name.Type'."
            )
        return None

    valid_types = _FABRIC_ITEMS.keys()
    if type not in valid_types:
        if not silent:
            logger.warning(
                f"Invalid item type '{type}'. Valid types are: {', '.join(valid_types)}."
            )
        return None

    for item_ in items:
        name_ = item_.get('displayName')
        type_ = item_.get('type')
        if name_ == name and type_ == type_:
            return item_['id']
    if not silent:
        logger.warning(f"Item '{item}' not found.")
    return None


@df
def get_item(
    workspace: str,
    item: str,
    *,
    df: bool = False,
) -> dict | pandas.DataFrame | None:
    """
    Retrieves a specific item from the workspace.

    Args:
        workspace (str): The workspace name or ID.
        item (str): The name or ID of the item to retrieve.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict | pandas.DataFrame | None): The item details as a dictionary or DataFrame, or None if not found.

    Examples:
        ```python
        get_item('MyProjectWorkspace', 'SalesDataModel')
        get_item('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', df=True)
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    item_id = resolve_item(workspace_id, item)
    if not item_id:
        return None

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/items/{item_id}'
    )

    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


@df
def update_item(
    workspace: str,
    item: str,
    display_name: str = None,
    description: str = None,
    *,
    df: bool = False,
) -> dict | pandas.DataFrame:
    """
    Updates the properties of the specified semantic model.

    Args:
        workspace (str): The workspace name or ID.
        item (str): The name or ID of the item to update.
        display_name (str, optional): The new display name for the item.
        description (str, optional): The new description for the item.

    Returns:
        (dict or None): The updated semantic model details if successful, otherwise None.

    Examples:
        ```python
        update_item('MyProjectWorkspace', 'SalesDataModel', display_name='UpdatedSalesDataModel')
        update_item('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', description='Updated description')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    item_id = resolve_item(workspace_id, item)
    if not item_id:
        return None

    item_ = get_item(workspace_id, item_id)
    if not item_:
        return None

    item_description = item_['description']
    item_display_name = item_['displayName']

    payload = {}

    if item_display_name != display_name and display_name:
        payload['displayName'] = display_name

    if item_description != description and description:
        payload['description'] = description

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/items/{item_id}',
        method='put',
        payload=payload,
    )

    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


def delete_item(workspace: str, item: str) -> None:
    """
    Delete a item from the specified workspace.

    Args:
        workspace (str): The name or ID of the workspace to delete.
        item (str): The name or ID of the item to delete.

    Returns:
        None: If the item is successfully deleted.

    Raises:
        ResourceNotFoundError: If the specified workspace is not found.

    Examples:
        ```python
        delete_item('MyProjectWorkspace', 'Salesitem')
        delete_item('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    item_id = resolve_item(workspace_id, item)
    if not item_id:
        return None

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/items/{item_id}',
        method='delete',
        return_raw=True,
    )
    if not response.status_code == 200:
        logger.warning(f'{response.status_code}: {response.text}.')
        return False
    else:
        return True


def get_item_definition(workspace: str, item: str) -> dict:
    """
    Retrieves the definition of a item by its name or ID from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        item (str): The name or ID of the item.

    Returns:
        (dict): The item definition if found, otherwise None.

    Examples:
        ```python
        get_item_definition('MyProjectWorkspace', 'Salesitem')
        get_item_definition('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    # Resolving IDs
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    item_id = resolve_item(workspace_id, item)
    if not item_id:
        return None

    # Requesting
    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/items/{item_id}/getDefinition',
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


def update_item_definition(workspace: str, item: str, path: str) -> dict:
    """
    Updates the definition of an existing item in the specified workspace.
    If the item does not exist, it returns None.

    Args:
        workspace (str): The workspace name or ID.
        item (str): The name or ID of the item to update.
        path (str): The path to the item definition.

    Returns:
        (dict or None): The updated item details if successful, otherwise None.

    Examples:
        ```python
        update_item_definition('MyProjectWorkspace', 'SalesDataModel', '/path/to/updated/definition.json')
        update_item_definition('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', '/path/to/updated/definition.json')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    item_id = resolve_item(workspace_id, item)
    if not item_id:
        return None

    definition = pack_item_definition(path)

    params = {'updateMetadata': True}

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/items/{item_id}/updateDefinition',
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


def create_item(
    workspace: str,
    display_name: str,
    path: str,
    description: str = None,
    folder: str = None,
):
    """
    Creates a new item in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name of the item.
        description (str, optional): A description for the item.
        folder (str, optional): The folder to create the item in.
        path (str): The path to the item definition file.

    Returns:
        (dict): The created item details.

    Examples:
        ```python
        create_item('MyProjectWorkspace', 'SalesDataModel', '/path/to/definition.json')
        create_item('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', '/path/to/definition.json')
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
        endpoint=f'/workspaces/{workspace_id}/items',
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


def export_item(
    workspace: str,
    item: str,
    project_path: str,
    workspace_path: str = 'workspace',
    update_config: bool = True,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
):
    """
    Exports a item definition to a specified folder structure.

    Args:
        workspace (str): The workspace name or ID.
        item (str): The name of the item to export.
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
        export_item('MyProjectWorkspace', 'SalesDataModel', '/path/to/project')
        export_item('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', '/path/to/project')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    workspace_name = get_workspace(workspace_id).get('displayName')
    if not workspace_id:
        return None

    item_ = get_item(workspace_id, item)
    if not item_:
        return None

    item_id = item_['id']
    item_type = item_['type']
    folder_id = None
    if 'folderId' in item_:
        folder_id = item_['folderId']

    definition = get_item_definition(workspace_id, item_id)
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

        item_id = item_['id']
        item_name = item_['displayName']
        item_descr = item_.get('description', '')

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
            definition, f'{item_path}/{item_name}.{item_type}'
        )

        for k, v in _FABRIC_ITEMS.items():
            if item_type == k:
                items_config_type = v
                break

        if items_config_type not in config:
            config[items_config_type] = {}
        if item_name not in config[items_config_type]:
            config[items_config_type][item_name] = {}
        if 'id' not in config[items_config_type][item_name]:
            config[items_config_type][item_name]['id'] = item_id
        if 'description' not in config[items_config_type][item_name]:
            config[items_config_type][item_name]['description'] = item_descr

        if folder_id:
            if 'folder_id' not in config[items_config_type][item_name]:
                config[items_config_type][item_name]['folder_id'] = folder_id

        # Update the config with the item details
        config[items_config_type][item_name]['id'] = item_id
        config[items_config_type][item_name]['description'] = item_descr
        config[items_config_type][item_name]['folder_id'] = folder_id

        # Saving the updated config back to the config file
        existing_config[branch][workspace_name_without_suffix] = config
        write_json(existing_config, config_path)

    else:
        unpack_item_definition(
            definition,
            f'{project_path}/{workspace_path}/{item_name}.{item_type}',
        )


def export_all_items(
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
    Exports all items to the specified folder structure.

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
        export_all_items('MyProjectWorkspace', '/path/to/project')
        export_all_items('MyProjectWorkspace', '/path/to/project', branch='main')
        export_all_items('MyProjectWorkspace', '/path/to/project', workspace_suffix='Workspace')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    items = list_items(workspace_id)
    if items:
        for item in items:
            export_item(
                workspace=workspace,
                item=item['displayName'] + '.' + item['type'],
                project_path=project_path,
                workspace_path=workspace_path,
                update_config=update_config,
                config_path=config_path,
                branch=branch,
                workspace_suffix=workspace_suffix,
                branches_path=branches_path,
            )


def deploy_item(
    workspace: str,
    item_name_dot_type: str,
    project_path: str,
    workspace_path: str = 'workspace',
    config_path: str = None,
    description: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
):
    """
    Creates or updates a item in Fabric based on local folder structure.
    Automatically detects the folder_id based on where the item is located locally.

    Args:
        workspace (str): The workspace name or ID.
        item_name_dot_type (str): The name and type of the item, formatted as "name.type".
        project_path (str): The root path of the project.
        workspace_path (str): The workspace folder name. Defaults to "workspace".
        config_path (str): The path to the config file. Defaults to "config.json".
        description (str, optional): A description for the item.
        branch (str, optional): The branch name. Will be auto-detected if not provided.
        workspace_suffix (str, optional): The workspace suffix. Will be read from config if not provided.

    Examples:
        ```python
        deploy_item('MyProjectWorkspace', 'SalesDataModel', '/path/to/project')
        deploy_item('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', '/path/to/project')
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

    # Check if item exists in workspace root
    root_path = f'{project_path}/{workspace_path}/{item_name_dot_type}'
    if os.path.exists(root_path):
        item_folder_path = workspace_path
        item_full_path = root_path
        logger.debug(f'Found item in workspace root: {root_path}')
    else:
        # Search for the item in subfolders (only once)
        base_search_path = f'{project_path}/{workspace_path}'
        logger.debug(
            f'Searching for {item_name_dot_type}.item in: {base_search_path}'
        )

        for root, dirs, files in os.walk(base_search_path):
            if f'{item_name_dot_type}' in dirs:
                item_full_path = os.path.join(root, f'{item_name_dot_type}')
                item_folder_path = os.path.relpath(root, project_path).replace(
                    '\\', '/'
                )
                logger.debug(f'Found item in: {item_full_path}')
                logger.debug(f'Relative folder path: {item_folder_path}')
                break

    if not item_folder_path or not item_full_path:
        logger.debug(f'item {item_name_dot_type} not found in local structure')
        logger.debug(f'Searched in: {project_path}/{workspace_path}')
        return None

    # Determine folder_id based on local path
    folder_id = None

    # Para items em subpastas, precisamos mapear o caminho da pasta pai
    if item_folder_path != workspace_path:
        # O item está em uma subpasta, precisamos encontrar o folder_id
        # Remover o "workspace/" do início do caminho para obter apenas a estrutura de pastas
        folder_relative_path = item_folder_path.replace(
            f'{workspace_path}/', ''
        )

        logger.debug(f'item located in subfolder: {folder_relative_path}')

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
        logger.debug(f'item will be created in workspace root')

    # Create the definition
    definition = pack_item_definition(item_full_path)

    # Check if item already exists (check only once)
    item_id = resolve_item(workspace_id, item_name_dot_type, silent=True)

    if item_id:
        logger.info(f"item '{item_name_dot_type}' already exists, updating...")
        # Update existing item
        payload = {'definition': definition}
        if description:
            payload['description'] = description

        response = api_core_request(
            endpoint=f'/workspaces/{workspace_id}/items/{item_id}/updateDefinition',
            method='post',
            payload=payload,
            params={'updateMetadata': True},
        )
        if response and response.error:
            logger.warning(
                f"Failed to update item '{item_name_dot_type}': {response.error}"
            )
            return None

        logger.info(f"Successfully updated item '{item_name_dot_type}'")
        return get_item(workspace_id, item_id)

    else:
        logger.info(f'Creating new item: {item_name_dot_type}')
        display_name = item_name_dot_type.split('.')[0]
        # Create new item
        payload = {'displayName': display_name, 'definition': definition}
        if description:
            payload['description'] = description
        if folder_id:
            payload['folderId'] = folder_id

        response = api_core_request(
            endpoint=f'/workspaces/{workspace_id}/items',
            method='post',
            payload=payload,
        )
        if response and response.error:
            logger.warning(
                f"Failed to create item '{item_name_dot_type}': {response.error}"
            )
            return None

        logger.info(f"Successfully created item '{item_name_dot_type}'")
        return get_item(workspace_id, item_name_dot_type)


def deploy_all_items(
    workspace: str,
    project_path: str,
    workspace_path: str = 'workspace',
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
):
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
        deploy_all_items('MyProjectWorkspace', '/path/to/project')
        deploy_all_items('MyProjectWorkspace', '/path/to/project', branch='main')
        deploy_all_items('MyProjectWorkspace', '/path/to/project', workspace_suffix='Workspace')
        ```
    """
    base_path = f'{project_path}/{workspace_path}'

    if not os.path.exists(base_path):
        logger.error(f'Base path does not exist: {base_path}')
        return None

    # Find all item folders recursively
    item_folders = []
    for root, dirs, files in os.walk(base_path):
        for dir_name in dirs:
            if dir_name.endswith('.item'):
                full_path = os.path.join(root, dir_name)
                # Extract just the item name (without .item suffix)
                item_name = dir_name.replace('.item', '')
                item_folders.append(
                    {
                        'name': item_name,
                        'path': full_path,
                        'relative_path': os.path.relpath(
                            full_path, project_path
                        ).replace('\\', '/'),
                    }
                )

    if not item_folders:
        logger.warning(f'No item folders found in {base_path}')
        return None

    logger.debug(f'Found {len(item_folders)} items to deploy:')
    for item in item_folders:
        logger.debug(f"  - {item['name']} at {item['relative_path']}")

    # Deploy each item
    deployed_items = []
    for item_info in item_folders:
        try:
            logger.debug(f"Deploying item: {item_info['name']}")
            result = deploy_item(
                workspace=workspace,
                display_name=item_info['name'],
                project_path=project_path,
                workspace_path=workspace_path,
                config_path=config_path,
                branch=branch,
                workspace_suffix=workspace_suffix,
                branches_path=branches_path,
            )
            if result:
                deployed_items.append(item_info['name'])
                logger.debug(f"Successfully deployed: {item_info['name']}")
            else:
                logger.debug(f"Failed to deploy: {item_info['name']}")
        except Exception as e:
            logger.error(f"Error deploying {item_info['name']}: {str(e)}")

    logger.info(
        f'Deployment completed. Successfully deployed {len(deployed_items)} items.'
    )
    return deployed_items
