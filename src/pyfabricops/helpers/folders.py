import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas
from pandas import DataFrame

from ..core.folders import list_folders
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
    def build_full_path(folder_id: str) -> str:
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
        return build_full_path(parent) + '/' + name

    # Apply the function by each dataframe row
    df['folder_path'] = df['id'].apply(lambda x: build_full_path(x))

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
        os.makedirs(Path(path) / folder['folder_path'], exist_ok=True)
    logger.success(f'All folders exported to {path} successfully.')


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
