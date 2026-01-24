import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas
from pandas import DataFrame

from ..core.folders import create_folder, list_folders, resolve_folder
from ..core.workspaces import resolve_workspace
from ..utils.logging import get_logger

logger = get_logger(__name__)


def generate_folders_paths(
    folders_df: DataFrame,
) -> DataFrame:
    """
    Returns the full path for the folder `folder_id` recursively concatenating the names of its parents.

    Args:
        folders_df (DataFrame): The DataFrame containing folder information.

    Returns:
        DataFrame: The full folder paths.
    """

    df = folders_df

    # Create a dict to lookup: id → {displayName, parentFolderId}
    folder_map = df.set_index('id')[['displayName', 'parentFolderId']].to_dict(
        'index'
    )

    # Recursive function with cache to build the full path
    @lru_cache(maxsize=None)
    def _build_full_path(folder_id: str) -> str:
        """
        Returns the full path for the folder `folder_id`,
        recursively concatenating the names of its parents.
        """
        node = folder_map.get(folder_id)
        if node is None:
            return ''  # id not found
        name = node['displayName']
        parent = node['parentFolderId']
        # If without parent, is root
        if pandas.isna(parent) or parent == '':
            return name
        # Otherwise, joins the parent path with self name
        return _build_full_path(parent) + '/' + name

    # Apply the function by each dataframe row
    df['folder_path'] = df['id'].apply(lambda x: _build_full_path(x))

    df = df.rename(columns={'id': 'folder_id'})
    return df[['folder_id', 'folder_path']]


def get_folders_paths(workspace: str) -> DataFrame:
    """
    Get the full folder paths for all folders in the workspace.

    Args:
        workspace (str): The workspace name.

    Returns:
        DataFrame: A DataFrame with folder IDs and their full paths.
    """
    folders_df = list_folders(workspace)

    if folders_df is None or folders_df.empty:
        logger.debug(f'No folders found in workspace {workspace}.')
        return None

    if 'parentFolderId' not in folders_df.columns:
        folders_df['parentFolderId'] = ''

    return generate_folders_paths(folders_df)


def get_folders_config(workspace: str) -> Union[Dict[str, Any], None]:
    """
    Get the folder configuration for a specific workspace.

    Args:
        workspace (str): The workspace name or ID.

    Returns:
        (Union[Dict[str, Any], None]): The folder configuration or None if not found.
    """
    folders = get_folders_paths(workspace)
    if folders is None:
        return None

    return folders.to_dict(orient='records')


def export_folders(workspace: str, path: Union[str, Path]) -> None:
    """
    Export all folders from a workspace to a specified path
    """
    folders = get_folders_paths(workspace)
    folders_list = folders.to_dict(orient='records')
    for folder in folders_list:
        folder_path_ = Path(path) / folder['folder_path']
        os.makedirs(folder_path_, exist_ok=True)
        # Create a dummy README.md in each created folder
        with open(
            Path(folder_path_) / 'README.md', 'w', encoding='utf-8'
        ) as f:
            f.write(
                f'# {folder["folder_path"]}\n\nThis folder corresponds to the Fabric workspace folder: **{folder["folder_path"]}**\n'
            )
    logger.success(
        f'All folders from workspace {workspace} were exported to {path} successfully.'
    )


def resolve_folder_from_id_to_path(
    workspace: str, folder_id: str
) -> Union[str, None]:
    """
    Return the folder path to the folder_id given for a specified worspace.
    """
    folders = get_folders_paths(workspace)
    if folders is None:
        return None

    folder_path = folders[folders['folder_id'] == folder_id][
        'folder_path'
    ].iloc[0]

    if folder_path is None:
        logger.info(f'{folder_id} not found in the workspace {workspace}')
        return None

    return folder_path


def deploy_folders(
    workspace: str,
    path: Union[str, Path],
):
    """
    Creates folders in Fabric workspace based on local folder structure

    Args:
        workspace (str): The name or ID of the workspace.
        path (str): The path to the project directory.
    """
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
            create_folder(
                workspace, folder_name, parent_folder=parent_folder_id
            )
        elif parent_name:
            create_folder(workspace, folder_name, parente_folder=parent_name)
        else:
            create_folder(workspace, folder_name)

    logger.success(f'Created all folders in the workspace {workspace}.')


def create_folders_from_path_string(workspace: str, path: str) -> str:
    """
    Create recursively folders and subfolders from a path string.

    Args:
        workspace (str): The name or ID of the workspace.
        path (str): The name or ID of the folder.

    Returns:
        str: The ID of the final folder.
    """
    workspace_id = resolve_workspace(workspace)

    if path is None or '/' not in path:
        return None

    folders_tree = path.split('/')

    parent_folder_id = None

    for folder in folders_tree:

        # Get folder_id if folder exists
        folder_id = resolve_folder(workspace_id, folder)
        if folder_id is not None:
            logger.info(
                f'Folder `{folder}` already exists with ID `{folder_id}`.'
            )

        # If not, creates it.
        else:
            folder_id = create_folder(
                workspace_id,
                folder,
                parent_folder=parent_folder_id,
                df=False,
            ).get('id')
            logger.success(
                f'Folder `{folder}` created with ID `{folder_id}` successfully.'
            )

        parent_folder_id = folder_id

    return folder_id
