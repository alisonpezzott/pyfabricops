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
from ..items.dataflows_gen2 import (
    create_dataflow_gen2,
    get_dataflow_gen2,
    get_dataflow_gen2_definition,
    list_dataflows_gen2,
    resolve_dataflow_gen2,
    update_dataflow_gen2_definition,
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


def get_dataflow_gen2_config(
    workspace: str, dataflow_gen2: str
) -> Union[Dict[str, Any], None]:
    """
    Get a specific dataflow_gen2 config from a workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        dataflow_gen2 (str): The name or ID of the dataflow_gen2.

    Returns:
        (Union[Dict[str, Any], None]): The dict config from the dataflow_gen2.
    """
    item = dataflow_gen2
    item_data = get_dataflow_gen2(workspace, item, df=False)

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


def get_all_dataflows_gen2_config(
    workspace: str,
) -> Union[Dict[str, Any], None]:
    """
    Get dataflows_gen2 config from a workspace.

    Args:
        workspace (str): The name or ID from the workspace.

    Returns:
        (Union[Dict[str, Any], None]): The dict config of all dataflows_gen2 in the workspace
    """
    items = list_dataflows_gen2(workspace, df=False)

    if items is None:
        return None

    config = {}

    for item in items:

        item_data = get_dataflow_gen2(workspace, item['id'], df=False)

        config[item['displayName']] = {
            'id': item['id'],
            'description': item.get('description', None),
            'folder_id': ''
            if item.get('folderId') is None or pd.isna(item.get('folderId'))
            else item['folderId'],
        }

    return config


def export_dataflow_gen2(
    workspace: str,
    dataflow_gen2: str,
    path: Union[str, Path],
) -> None:
    """
    Export a dataflow_gen2 to path.

    Args:
        workspace (str): The name or ID of the workspace.
        dataflow_gen2 (str): The name or ID of the dataflow_gen2.
        path (Union[str, Path]): The path to export to.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    item = get_dataflow_gen2(workspace_id, dataflow_gen2, df=False)
    try:
        folder_path = resolve_folder_from_id_to_path(
            workspace_id, item['folderId']
        )
    except:
        logger.info(f'{item["displayName"]}.Dataflow is not inside a folder.')
        folder_path = None

    if folder_path is None:
        item_path = Path(path) / (item['displayName'] + '.Dataflow')
    else:
        item_path = (
            Path(path) / folder_path / (item['displayName'] + '.Dataflow')
        )
    os.makedirs(item_path, exist_ok=True)

    definition = get_dataflow_gen2_definition(workspace_id, item['id'])
    if definition is None:
        return None

    unpack_item_definition(definition, item_path)

    logger.success(
        f'`{item["displayName"]}.Dataflow` was exported to {item_path} successfully.'
    )
    return None


def export_all_dataflows_gen2(
    workspace: str,
    path: Union[str, Path],
) -> None:
    """
    Export a dataflow_gen2 to path.

    Args:
        workspace (str): The name or ID of the workspace.
        dataflow_gen2 (str): The name or ID of the dataflow_gen2.
        path (Union[str, Path]): The path to export to.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    items = list_dataflows_gen2(workspace_id, df=False)
    if items is None:
        return None

    for item in items:
        try:
            folder_path = resolve_folder_from_id_to_path(
                workspace_id, item['folderId']
            )
        except:
            logger.info(
                f'{item["displayName"]}.Dataflow is not inside a folder.'
            )
            folder_path = None

        if folder_path is None:
            item_path = Path(path) / (item['displayName'] + '.Dataflow')
        else:
            item_path = (
                Path(path) / folder_path / (item['displayName'] + '.Dataflow')
            )
        os.makedirs(item_path, exist_ok=True)

        definition = get_dataflow_gen2_definition(workspace_id, item['id'])
        if definition is None:
            return None

        unpack_item_definition(definition, item_path)

    logger.success(f'All dataflows_gen2 were exported to {path} successfully.')
    return None


@df
def deploy_dataflow_gen2(
    workspace: str,
    path: str,
    start_path: Optional[str] = None,
    description: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Deploy a dataflow_gen2 to workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        path (str): The path to the dataflow_gen2.
        start_path (Optional[str]): The starting path for folder creation.
        description (Optional[str]): Description for the dataflow_gen2.
        df (Optional[bool]): If True, returns a DataFrame, otherwise returns a dictionary.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The deployed dataflow_gen2 or None if deployment fails.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    display_name = extract_display_name_from_platform(path)
    if display_name is None:
        return None

    item_id = resolve_dataflow_gen2(workspace_id, display_name)

    folder_path_string = extract_middle_path(path, start_path=start_path)
    folder_id = create_folders_from_path_string(
        workspace_id, folder_path_string
    )

    item_definition = pack_item_definition(path)

    if item_id is None:
        return create_dataflow_gen2(
            workspace_id,
            display_name=display_name,
            item_definition=item_definition,
            description=description,
            folder=folder_id,
        )

    else:
        return update_dataflow_gen2_definition(
            workspace_id,
            item_id,
            item_definition=item_definition,
        )


def deploy_all_dataflows_gen2(
    workspace: str,
    path: str,
    start_path: Optional[str] = None,
) -> None:
    """
    Deploy all dataflows_gen2 to workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        path (str): The path to the dataflows_gen2.
        start_path (Optional[str]): The starting path for folder creation.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    dataflows_gen2_paths = list_paths_of_type(path, 'Dataflow')

    for path_ in dataflows_gen2_paths:

        display_name = extract_display_name_from_platform(path_)
        if display_name is None:
            return None

        item_id = resolve_dataflow_gen2(workspace_id, display_name)

        folder_path_string = extract_middle_path(path_, start_path=start_path)
        folder_id = create_folders_from_path_string(
            workspace_id, folder_path_string
        )

        item_definition = pack_item_definition(path_)

        if item_id is None:
            create_dataflow_gen2(
                workspace_id,
                display_name=display_name,
                item_definition=item_definition,
                folder=folder_id,
            )

        else:
            update_dataflow_gen2_definition(
                workspace_id,
                item_id,
                item_definition=item_definition,
            )

    logger.success(
        f'All dataflows_gen2 were deployed to workspace "{workspace}" successfully.'
    )
    return None
