import logging
import os
from logging import config
from re import sub
from typing import Literal

import pandas

from ._core import api_core_request, pagination_handler
from ._decorators import df
from ._utils import (
    get_current_branch,
    get_workspace_suffix,
    is_valid_uuid,
    read_json,
    write_json,
)
from ._workspaces import get_workspace, resolve_workspace

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


@df
def list_folders(
    workspace: str, *, df: bool = False
) -> list | pandas.DataFrame | None:
    """
    List folders in a workspace

    Args:
        workspace (str): The workspace to list folders from.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (list or pandas.DataFrame or None): A list of folders in the workspace. df=True returns a DataFrame.

    Examples:
        ```python
        list_folders('my_workspace')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    response = api_core_request(endpoint=f'/workspaces/{workspace_id}/folders')
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        response = pagination_handler(response)
        return response.data.get('value')


def resolve_folder(workspace: str, folder: str) -> str | None:
    """
    Resolves a folder name to its ID.

    Args:
        workspace (str): The ID of the workspace.
        folder (str): The name of the folder.

    Returns:
        str|None: The ID of the folder, or None if not found.

    Examples:
        ```python
        resolve_folder('MyProjectWorkspace', 'SalesFolder')
        resolve_folder('123e4567-e89b-12d3-a456-426614174000', 'SalesFolder')
        ```
    """
    if is_valid_uuid(folder):
        return folder
    folders = list_folders(workspace, df=False)
    for f in folders:
        if f['displayName'] == folder:
            return f['id']
    # If we get here, folder was not found
    logger.warning(f"Folder name '{folder}' not found.")
    return None


@df
def get_folder(
    workspace: str, folder: str, *, df: bool = False
) -> dict | pandas.DataFrame | None:
    """
    Get a folder in a workspace.

    Args:
        workspace (str): The workspace to get the folder from.
        folder (str): The folder to get.

    Returns:
        (dict or pandas.DataFrame): The folder details if found, otherwise None.

    Examples:
        ```python
        get_folder('MyProjectWorkspace', 'SalesFolder')
        get_folder('123e4567-e89b-12d3-a456-426614174000', 'SalesFolder')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    folder_id = resolve_folder(workspace_id, folder)
    if not folder_id:
        return None

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/folders/{folder_id}'
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


@df
def create_folder(
    workspace: str, folder: str, parent_folder: str = None, *, df: bool = False
) -> dict | pandas.DataFrame | None:
    """
    Create a new folder in the specified workspace.

    Args:
        workspace_id (str): The workspace where the folder will be created.
        folder (str): The name of the folder to create.
        parent_folder (str): The name or ID of the parent folder.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame or None): The created folder details if successful, otherwise None.

    Examples:
        ```python
        create_folder('MyProjectWorkspace', 'NewFolder', 'ParentFolder')
        create_folder('123e4567-e89b-12d3-a456-426614174000', 'NewFolder', 'ParentFolder')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    payload = {'displayName': folder}

    parent_folder_id = None
    if parent_folder:
        parent_folder_id = resolve_folder(workspace_id, parent_folder)

    if parent_folder_id:
        payload['parentFolderId'] = parent_folder_id

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/folders',
        payload=payload,
        method='post',
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


def delete_folder(workspace: str, folder: str) -> bool | None:
    """
    Delete a folder in a workspace

    Args:
        workspace (str): The workspace to delete the folder from.
        folder (str): The folder to delete.

    Returns:
        (bool | None): True if the folder was deleted successfully, False if not found, None if workspace is invalid.

    Examples:
        ```python
        delete_folder('MyProjectWorkspace', 'SalesFolder')
        delete_folder('123e4567-e89b-12d3-a456-426614174000', 'SalesFolder')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    folder_id = resolve_folder(workspace_id, folder)
    if not folder_id:
        return None

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/folders/{folder_id}',
        method='delete',
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return response.success
    else:
        return response.success


@df
def update_folder(
    workspace: str, folder: str, display_name: str, *, df: bool = False
) -> dict | pandas.DataFrame | None:
    """
    Update a existing folder in the specified workspace.

    Args:
        workspace (str): The workspace where the folder will be updated.
        folder (str): The folder to update.
        display_name (str): The name of the folder to update.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame | None): The updated folder details if successful, otherwise None.

    Examples:
        ```python
        update_folder('MyProjectWorkspace', 'OldFolderName', 'NewFolderName')
        update_folder('123e4567-e89b-12d3-a456-426614174000', 'OldFolderName', 'NewFolderName')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None
    folder_id = resolve_folder(workspace_id, folder)
    if not folder_id:
        return None
    payload = {'displayName': display_name}
    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/folders/{folder_id}',
        payload=payload,
        method='patch',
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


@df
def move_folder(
    workspace: str, folder: str, target_folder: str, *, df: bool = False
) -> dict | pandas.DataFrame | None:
    """
    Move a existing folder into other or root folder.

    Args:
        workspace (str): The workspace where the folder will be updated.
        folder (str): The folder to be moved.
        target_folder (str): The name of the parent folder will receive the moved folder.

    Returns:
        (dict | pandas.DataFrame | None): The moved folder details if successful, otherwise None.

    Examples:
        ```python
        move_folder('MyProjectWorkspace', 'SalesFolder', 'Archive')
        move_folder('123e4567-e89b-12d3-a456-426614174000', 'SalesFolder', 'Archive')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None
    folder_id = resolve_folder(workspace_id, folder)
    if not folder_id:
        return None
    target_folder_id = resolve_folder(workspace_id, target_folder)
    if not target_folder_id:
        return None
    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/folders/{folder_id}/move',
        payload={'targetFolderId': target_folder_id},
        method='post',
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


def _get_folders_config(
    workspace: str,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
):
    """
    Retrieves the folders configuration for a given workspace, branch, and optional suffix.

    Args:
        workspace (str): The ID or name of the workspace to retrieve configuration for.
        branch (str, optional): The branch name to use for the configuration. If not provided, the current branch is used.
        workspace_suffix (str, optional): The suffix to append to the workspace name. If not provided, it will be determined from branches.json.
        branches_path (str, optional): The path to branches.json. If not provided, it defaults to the root path.

    Returns:
        dict: A dictionary containing the workspace configuration details, including workspace ID, name, description, capacity ID, region, and roles.

    Examples:
        ```python
        get_workspace_config_flow('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    # Workspace details
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None
    workspace_name = get_workspace(workspace_id, df=False)['displayName']

    # Extract list of folders from the workspace
    folders_df = list_folders(workspace, df=True)

    # Sort by parentFolderId to ensure parent folders are created first
    if 'parentFolderId' not in folders_df.columns:
        folders_df['parentFolderId'] = None
    folders_sorted = folders_df.sort_values(
        ['parentFolderId'], na_position='first'
    )

    # Dictionary to map folder_id to full path
    folder_paths = {}

    for _, folder in folders_sorted.iterrows():
        folder_id = folder['id']
        folder_name = folder['displayName']
        parent_id = folder.get('parentFolderId')

        # If no parent, it's the root folder
        if pandas.isna(parent_id) or parent_id is None:
            folder_path = folder_name
        else:
            # Get the parent's path and add this folder
            parent_path = folder_paths.get(parent_id, '')
            folder_path = os.path.join(parent_path, folder_name)

        folder_paths[folder_id] = folder_path.replace('\\', '/')

    # Create the config dictionary
    config = {}
    config['folders'] = {}

    # Invert the dictionary: path -> id instead of id -> path
    for folder_id, folder_path in folder_paths.items():
        config['folders'][folder_path] = folder_id

    folders_config = config
    if not folders_config:
        return None

    # Get branch
    branch = get_current_branch(branch)

    # Get the workspace suffix and treating the name
    workspace_suffix = get_workspace_suffix(
        branch, workspace_suffix, branches_path
    )
    workspace_name_without_suffix = workspace_name.split(workspace_suffix)[0]

    # Build the config
    config = {}
    config[branch] = {}
    config[branch][workspace_name_without_suffix] = folders_config

    return config


def export_folders(
    workspace: str,
    project_path: str,
    workspace_path: str = 'workspace',
    update_config: bool = True,
    config_path: str = None,
    merge_mode: Literal['update', 'replace', 'preserve'] = 'update',
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
):
    """
    Creates the folder structure of Fabric Workspace into project path

    Args:
        workspace (str): The name or ID of the workspace.
        project_path (str): The path to the project directory.
        workspace_path (str, optional): The path to the workspace directory within the project. Defaults to 'workspace'.
        update_config (bool, optional): Whether to update the configuration file after exporting folders. Defaults to True.
        config_path (str, optional): The path to the configuration file. If not provided, defaults to 'config.json' in the project directory.
        merge_mode (Literal['update', 'replace', 'preserve'], optional): The merge mode to use when updating the configuration file. Defaults to 'update'.
        branch (str, optional): The branch name to use for the configuration. If not provided, the current branch is used.
        workspace_suffix (str, optional): The suffix to append to the workspace name. If not provided, it will be determined from branches.json.
        branches_path (str, optional): The path to branches.json. If not provided, it defaults to the root path.

    Returns:
        None

    Examples:
        ```python
        export_folders('MyProjectWorkspace', '/path/to/project')
        export_folders('123e4567-e89b-12d3-a456-426614174000', '/path/to/project')
        ```
    """
    path = os.path.join(project_path, workspace_path)

    os.makedirs(path, exist_ok=True)

    # Extract list of folders from the workspace
    folders_df = list_folders(workspace, df=True)

    # Sort by parentFolderId to ensure parent folders are created first
    # Only sort if parentFolderId column exists (i.e., there are subfolders)
    if 'parentFolderId' in folders_df.columns:
        folders_sorted = folders_df.sort_values(
            ['parentFolderId'], na_position='first'
        )
    else:
        # If no parentFolderId column, all folders are root level
        folders_sorted = folders_df

    # Dictionary to map folder_id to full path
    folder_paths = {}

    for _, folder in folders_sorted.iterrows():
        folder_id = folder['id']
        folder_name = folder['displayName']
        # Safely get parentFolderId - it may not exist if there are no subfolders
        parent_id = (
            folder.get('parentFolderId')
            if 'parentFolderId' in folder.index
            else None
        )

        # If no parent, it's the root folder
        if pandas.isna(parent_id) or parent_id is None:
            folder_path = os.path.join(path, folder_name)
        else:
            # Get the parent's path and add this folder
            parent_path = folder_paths.get(parent_id, path)
            folder_path = os.path.join(parent_path, folder_name)

        # Create the folder
        os.makedirs(folder_path, exist_ok=True)

        # Create a dummy README.md in each folder
        readme_path = os.path.join(folder_path, 'README.md')
        if not os.path.exists(readme_path):
            with open(readme_path, 'w', encoding='utf-8') as f:
                f.write(
                    f'# {folder_name}\n\nThis folder corresponds to the Fabric workspace folder: **{folder_name}**\n\nFolder ID: `{folder_id}`\n'
                )

        folder_paths[folder_id] = folder_path

    # Fix f-string backslash issue
    normalized_path = path.replace('\\', '/')
    logger.info(f'Folder structure created at {normalized_path}')

    if update_config:
        # Get the new config for this workspace
        new_config = _get_folders_config(
            workspace, branch, workspace_suffix, branches_path
        )
        if not new_config:
            logger.warning(
                f'No configuration found for workspace {workspace}.'
            )
            return None

        if not config_path:
            config_path = os.path.join(project_path, 'config.json')

        # Create path if not exists
        if not os.path.exists(os.path.dirname(config_path)):
            os.makedirs(os.path.dirname(config_path), exist_ok=True)

        # Try to read existing config.json
        try:
            existing_config = read_json(config_path)
        except FileNotFoundError:
            logger.warning(
                f'No existing config found at {config_path}, creating a new one.'
            )
            existing_config = {}

        # Process each branch in new config
        for branch_name, workspaces in new_config.items():
            # Ensure branch exists in existing config
            if branch_name not in existing_config:
                existing_config[branch_name] = {}

            # Process each workspace
            for workspace_name, folders_config in workspaces.items():
                # Ensure workspace exists in existing config
                if workspace_name not in existing_config[branch_name]:
                    existing_config[branch_name][workspace_name] = {}

                # Merge folders config with existing workspace config
                if merge_mode == 'replace':
                    # Replace all folders config
                    existing_config[branch_name][workspace_name][
                        'folders'
                    ] = folders_config['folders']
                    logger.info(
                        f'Replaced folders config for workspace "{workspace_name}" in branch "{branch_name}"'
                    )
                elif (
                    merge_mode == 'preserve'
                    and 'folders'
                    in existing_config[branch_name][workspace_name]
                ):
                    logger.info(
                        f'Folders config already exists for workspace "{workspace_name}" in branch "{branch_name}". Preserving existing config.'
                    )
                    continue
                else:
                    # Update mode (default): merge folders config
                    existing_config[branch_name][workspace_name][
                        'folders'
                    ] = folders_config['folders']
                    logger.info(
                        f'Updated folders config for workspace "{workspace_name}" in branch "{branch_name}"'
                    )

        # Write the updated configuration to the file
        write_json(existing_config, config_path)
        logger.info(
            f'Folders configuration successfully written to {config_path}.'
        )


def deploy_folders(
    workspace: str,
    project_path: str,
    workspace_path: str = 'workspace',
    update_config: bool = True,
    config_path: str = None,
    merge_mode: Literal['update', 'replace', 'preserve'] = 'update',
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
):
    """
    Creates folders in Fabric workspace based on local folder structure

    Args:
        workspace (str): The name or ID of the workspace.
        project_path (str): The path to the project directory.
        workspace_path (str, optional): The path to the workspace directory within the project. Defaults to 'workspace'.
        update_config (bool, optional): Whether to update the configuration file after exporting folders. Defaults to True.
        config_path (str, optional): The path to the configuration file. If not provided, defaults to 'config.json' in the project directory.
        merge_mode (Literal['update', 'replace', 'preserve'], optional): The merge mode to use when updating the configuration file. Defaults to 'update'.
        branch (str, optional): The branch name to use for the configuration. If not provided, the current branch is used.
        workspace_suffix (str, optional): The suffix to append to the workspace name. If not provided, it will be determined from branches.json.
        branches_path (str, optional): The path to branches.json. If not provided, it defaults to the root path.

    Returns:
        None

    Examples:
        ```python
        export_folders('MyProjectWorkspace', '/path/to/project')
        export_folders('123e4567-e89b-12d3-a456-426614174000', '/path/to/project')
        ```
    """
    path = os.path.join(project_path, workspace_path)

    if not os.path.exists(path):
        logger.error(f'Path {path} does not exist.')
        return None

    # Resolve workspace ID
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    # Get all local folders that contain Fabric artifacts
    fabric_artifacts = [
        '.SemanticModel',
        '.Report',
        '.Dataflow',
        '.Lakehouse',
        '.Warehouse',
        '.Notebook',
        '.DataPipeline',
    ]

    def _has_fabric_artifacts(path):
        """Check if folder or any subfolder contains Fabric artifacts"""
        for root, dirs, files in os.walk(path):
            for dir_name in dirs:
                if any(
                    dir_name.endswith(artifact)
                    for artifact in fabric_artifacts
                ):
                    return True
        return False

    # First pass: identify folders with artifacts and their parent folders
    folders_with_artifacts = set()

    for root, dirs, files in os.walk(path):
        for dir_name in dirs:
            full_path = os.path.join(root, dir_name)

            # Check if this folder has Fabric artifacts
            if _has_fabric_artifacts(full_path):
                relative_path = os.path.relpath(full_path, path).replace(
                    '\\', '/'
                )
                folders_with_artifacts.add(relative_path)

                # Also mark all parent folders as needed
                parent_path = os.path.dirname(relative_path).replace('\\', '/')
                while (
                    parent_path != path
                    and parent_path != '.'
                    and parent_path != ''
                ):
                    folders_with_artifacts.add(parent_path)
                    parent_path = os.path.dirname(parent_path).replace(
                        '\\', '/'
                    )

    # Second pass: build folder list only for folders with artifacts
    local_folders = []
    for root, dirs, files in os.walk(path):
        for dir_name in dirs:
            full_path = os.path.join(root, dir_name)
            relative_path = os.path.relpath(full_path, path).replace('\\', '/')

            # Only include folders that contain artifacts or are parents of folders with artifacts
            if relative_path in folders_with_artifacts:
                # Calculate depth for proper ordering (parents before children)
                depth = relative_path.count('/')

                # Get parent folder name (not full path)
                parent_relative_path = os.path.dirname(relative_path).replace(
                    '\\', '/'
                )
                parent_folder_name = None
                if (
                    parent_relative_path
                    and parent_relative_path != '.'
                    and parent_relative_path != ''
                ):
                    parent_folder_name = os.path.basename(parent_relative_path)

                local_folders.append(
                    {
                        'path': relative_path,
                        'name': dir_name,
                        'full_path': full_path,
                        'depth': depth,
                        'parent_path': parent_relative_path,
                        'parent_name': parent_folder_name,
                    }
                )

    # Sort by depth to ensure parent folders are created first
    local_folders.sort(key=lambda x: x['depth'])

    logger.info(
        f'Found {len(local_folders)} folders containing Fabric artifacts'
    )

    # Keep track of created folders by path -> folder_id
    created_folders = {}

    for folder_info in local_folders:
        folder_name = folder_info['name']
        parent_path = folder_info['parent_path']
        parent_name = folder_info['parent_name']

        # Determine parent folder ID from previously created folders
        parent_folder_id = None
        if parent_path and parent_path in created_folders:
            parent_folder_id = created_folders[parent_path]

        # Create folder in Fabric
        if parent_folder_id:
            create_folder(workspace, folder_name, parent_folder_id)
        elif parent_name:
            create_folder(workspace, folder_name, parent_name)
        else:
            create_folder(workspace, folder_name)

    logger.info(f'Created folders for workspace {workspace}.')

    if update_config:
        # Get the new config for this workspace
        new_config = _get_folders_config(
            workspace, branch, workspace_suffix, branches_path
        )
        if not new_config:
            logger.warning(
                f'No configuration found for workspace {workspace}.'
            )
            return None

        if not config_path:
            config_path = os.path.join(project_path, 'config.json')

        # Create path if not exists
        if not os.path.exists(os.path.dirname(config_path)):
            os.makedirs(os.path.dirname(config_path), exist_ok=True)

        # Try to read existing config.json
        try:
            existing_config = read_json(config_path)
        except FileNotFoundError:
            logger.warning(
                f'No existing config found at {config_path}, creating a new one.'
            )
            existing_config = {}

        # Process each branch in new config
        for branch_name, workspaces in new_config.items():
            # Ensure branch exists in existing config
            if branch_name not in existing_config:
                existing_config[branch_name] = {}

            # Process each workspace
            for workspace_name, folders_config in workspaces.items():
                # Ensure workspace exists in existing config
                if workspace_name not in existing_config[branch_name]:
                    existing_config[branch_name][workspace_name] = {}

                # Merge folders config with existing workspace config
                if merge_mode == 'replace':
                    # Replace all folders config
                    existing_config[branch_name][workspace_name][
                        'folders'
                    ] = folders_config['folders']
                    logger.info(
                        f'Replaced folders config for workspace "{workspace_name}" in branch "{branch_name}"'
                    )
                elif (
                    merge_mode == 'preserve'
                    and 'folders'
                    in existing_config[branch_name][workspace_name]
                ):
                    logger.info(
                        f'Folders config already exists for workspace "{workspace_name}" in branch "{branch_name}". Preserving existing config.'
                    )
                    continue
                else:
                    # Update mode (default): merge folders config
                    existing_config[branch_name][workspace_name][
                        'folders'
                    ] = folders_config['folders']
                    logger.info(
                        f'Updated folders config for workspace "{workspace_name}" in branch "{branch_name}"'
                    )

        # Write the updated configuration to the file
        write_json(existing_config, config_path)
        logger.info(
            f'Folders configuration successfully written to {config_path}.'
        )
