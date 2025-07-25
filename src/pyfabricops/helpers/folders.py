from functools import lru_cache
import pandas
from pandas import DataFrame

from ..core.folders import list_folders


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
