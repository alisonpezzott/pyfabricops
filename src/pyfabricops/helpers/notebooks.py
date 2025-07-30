import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

import pandas as pd
from pandas import DataFrame

from ..core.workspaces import resolve_workspace
from ..helpers.folders import (
    create_folders_from_path_string,
    resolve_folder_from_id_to_path,
)
from ..items.notebooks import (
    create_notebook,
    get_notebook,
    get_notebook_definition,
    list_notebooks,
    resolve_notebook,
    update_notebook_definition,
)
from ..utils.decorators import df
from ..utils.logging import get_logger
from ..utils.utils import (
    extract_display_name_from_platform,
    extract_middle_path,
    list_paths_of_type,
    pack_item_definition,
    unpack_item_definition,
)

logger = get_logger(__name__)


def get_notebook_config(
    workspace: str, notebook: str
) -> Union[Dict[str, Any], None]:
    """
    Get a specific notebook config from a workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        notebook (str): The name or ID of the notebook.

    Returns:
        (Union[Dict[str, Any], None]): The dict config from the notebook.
    """
    item = notebook
    item_data = get_notebook(workspace, item, df=False)

    if item_data is None:
        return None

    else:
        config = {}
        config = config[item_data.get('displayName')] = {}

        config = {
            'id': item_data['id'],
            'description': item_data.get('description', None),
            'folder_id': ''
            if item_data.get('folderId') is None
            or pd.isna(item_data.get('folderId'))
            else item_data['folderId'],
        }

        return config


def get_all_notebooks_config(
    workspace: str,
) -> Union[Dict[str, Any], None]:
    """
    Get notebooks config from a workspace.

    Args:
        workspace (str): The name or ID from the workspace.

    Returns:
        (Union[Dict[str, Any], None]): The dict config of all notebooks in the workspace
    """
    items = list_notebooks(workspace, df=False)

    if items is None:
        return None

    config = {}

    for item in items:

        item_data = get_notebook(workspace, item['id'], df=False)

        config[item['displayName']] = {
            'id': item['id'],
            'description': item.get('description', None),
            'folder_id': ''
            if item.get('folderId') is None or pd.isna(item.get('folderId'))
            else item['folderId'],
        }

    return config


def export_notebook(
    workspace: str,
    notebook: str,
    path: Union[str, Path],
) -> None:
    """
    Export a notebook to path.

    Args:
        workspace (str): The name or ID of the workspace.
        notebook (str): The name or ID of the notebook.
        path (Union[str, Path]): The path to export to.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    item = get_notebook(workspace_id, notebook, df=False)
    try:
        folder_path = resolve_folder_from_id_to_path(
            workspace_id, item['folderId']
        )
    except:
        logger.info(f'{item["displayName"]}.Notebook is not inside a folder.')
        folder_path = None

    if folder_path is None:
        item_path = Path(path) / (item['displayName'] + '.Notebook')
    else:
        item_path = (
            Path(path) / folder_path / (item['displayName'] + '.Notebook')
        )
    os.makedirs(item_path, exist_ok=True)

    definition = get_notebook_definition(workspace_id, item['id'])
    if definition is None:
        return None

    unpack_item_definition(definition, item_path)

    logger.success(
        f'`{item["displayName"]}.Notebook` was exported to {item_path} successfully.'
    )
    return None


def export_all_notebooks(
    workspace: str,
    path: Union[str, Path],
) -> None:
    """
    Export a notebook to path.

    Args:
        workspace (str): The name or ID of the workspace.
        notebook (str): The name or ID of the notebook.
        path (Union[str, Path]): The path to export to.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    items = list_notebooks(workspace_id, df=False)
    if items is None:
        return None

    for item in items:
        try:
            folder_path = resolve_folder_from_id_to_path(
                workspace_id, item['folderId']
            )
        except:
            logger.info(
                f'{item["displayName"]}.Notebook is not inside a folder.'
            )
            folder_path = None

        if folder_path is None:
            item_path = Path(path) / (item['displayName'] + '.Notebook')
        else:
            item_path = (
                Path(path) / folder_path / (item['displayName'] + '.Notebook')
            )
        os.makedirs(item_path, exist_ok=True)

        definition = get_notebook_definition(workspace_id, item['id'])
        if definition is None:
            return None

        unpack_item_definition(definition, item_path)

    logger.success(f'All notebooks were exported to {path} successfully.')
    return None


@df
def deploy_notebook(
    workspace: str,
    path: str,
    start_path: Optional[str] = None,
    description: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Deploy a notebook to workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        path (str): The path to the notebook.
        start_path (Optional[str]): The starting path for folder creation.
        description (Optional[str]): Description for the notebook.
        df (Optional[bool]): If True, returns a DataFrame, otherwise returns a dictionary.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The deployed notebook or None if deployment fails.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    display_name = extract_display_name_from_platform(path)
    if display_name is None:
        return None

    item_id = resolve_notebook(workspace_id, display_name)

    folder_path_string = extract_middle_path(path, start_path=start_path)
    folder_id = create_folders_from_path_string(
        workspace_id, folder_path_string
    )

    item_definition = pack_item_definition(path)

    if item_id is None:
        return create_notebook(
            workspace_id,
            display_name=display_name,
            item_definition=item_definition,
            description=description,
            folder=folder_id,
        )

    else:
        return update_notebook_definition(
            workspace_id,
            item_id,
            item_definition=item_definition,
        )


def deploy_all_notebooks(
    workspace: str,
    path: str,
    start_path: Optional[str] = None,
) -> None:
    """
    Deploy all notebooks to workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        path (str): The path to the notebooks.
        start_path (Optional[str]): The starting path for folder creation.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    notebooks_paths = list_paths_of_type(path, 'Notebook')

    for path_ in notebooks_paths:

        display_name = extract_display_name_from_platform(path_)
        if display_name is None:
            return None

        item_id = resolve_notebook(workspace_id, display_name)

        folder_path_string = extract_middle_path(path_, start_path=start_path)
        folder_id = create_folders_from_path_string(
            workspace_id, folder_path_string
        )

        item_definition = pack_item_definition(path_)

        if item_id is None:
            create_notebook(
                workspace_id,
                display_name=display_name,
                item_definition=item_definition,
                folder=folder_id,
            )

        else:
            update_notebook_definition(
                workspace_id,
                item_id,
                item_definition=item_definition,
            )

    logger.success(
        f'All notebooks were deployed to workspace "{workspace}" successfully.'
    )
    return None
