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
from ..items.environments import (
    create_environment,
    get_environment,
    get_environment_definition,
    list_environments,
    resolve_environment,
    update_environment_definition,
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


def get_environment_config(
    workspace: str, environment: str
) -> Union[Dict[str, Any], None]:
    """
    Get a specific environment config from a workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        environment (str): The name or ID of the semantic.

    Returns:
        (Union[Dict[str, Any], None]): The dict config from the environment
    """
    item = environment
    item_data = get_environment(workspace, item, df=False)

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


def get_all_environments_config(
    workspace: str,
) -> Union[Dict[str, Any], None]:
    """
    Get environments config from a workspace.

    Args:
        workspace (str): The name or ID from the workspace.

    Returns:
        (Union[Dict[str, Any], None]): The dict config of all environments in the workspace
    """
    items = list_environments(workspace, df=False)

    if items is None:
        return None

    config = {}

    for item in items:

        item_data = get_environment(workspace, item['id'], df=False)

        config[item['displayName']] = {
            'id': item['id'],
            'description': item.get('description', None),
            'folder_id': ''
            if item.get('folderId') is None or pd.isna(item.get('folderId'))
            else item['folderId'],
        }

    return config


def export_environment(
    workspace: str,
    environment: str,
    path: Union[str, Path],
) -> None:
    """
    Export a environment to path.

    Args:
        workspace (str): The name or ID of the workspace.
        environment (str): The name or ID of the environment.
        path (Union[str, Path]): The path to export to.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    item = get_environment(workspace_id, environment, df=False)
    try:
        folder_path = resolve_folder_from_id_to_path(
            workspace_id, item['folderId']
        )
    except:
        logger.info(
            f'{item["displayName"]}.Environment is not inside a folder.'
        )
        folder_path = None

    if folder_path is None:
        item_path = Path(path) / (item['displayName'] + '.Environment')
    else:
        item_path = (
            Path(path) / folder_path / (item['displayName'] + '.Environment')
        )
    os.makedirs(item_path, exist_ok=True)

    definition = get_environment_definition(workspace_id, item['id'])
    if definition is None:
        return None

    unpack_item_definition(definition, item_path)

    logger.success(
        f'`{item["displayName"]}.Environment` was exported to {item_path} successfully.'
    )
    return None


def export_all_environments(
    workspace: str,
    path: Union[str, Path],
) -> None:
    """
    Export a environment to path.

    Args:
        workspace (str): The name or ID of the workspace.
        path (Union[str, Path]): The path to export to.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    items = list_environments(workspace_id, df=False)
    if items is None:
        return None

    for item in items:
        try:
            folder_path = resolve_folder_from_id_to_path(
                workspace_id, item['folderId']
            )
        except:
            logger.info(
                f'{item["displayName"]}.Environment is not inside a folder.'
            )
            folder_path = None

        if folder_path is None:
            item_path = Path(path) / (item['displayName'] + '.Environment')
        else:
            item_path = (
                Path(path)
                / folder_path
                / (item['displayName'] + '.Environment')
            )
        os.makedirs(item_path, exist_ok=True)

        definition = get_environment_definition(workspace_id, item['id'])
        if definition is None:
            return None

        unpack_item_definition(definition, item_path)

    logger.success(f'All environments were exported to {path} successfully.')
    return None


@df
def deploy_environment(
    workspace: str,
    path: str,
    start_path: Optional[str] = None,
    description: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Deploy a environment to workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        path (str): The path to the environment.
        start_path (Optional[str]): The starting path for folder creation.
        description (Optional[str]): Description for the environment.
        df (Optional[bool]): If True, returns a DataFrame, otherwise returns a dictionary.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The deployed environment or None if deployment fails.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    display_name = extract_display_name_from_platform(path)
    if display_name is None:
        return None

    environment_id = resolve_environment(workspace_id, display_name)

    folder_path_string = extract_middle_path(path, start_path=start_path)
    folder_id = create_folders_from_path_string(
        workspace_id, folder_path_string
    )

    item_definition = pack_item_definition(path)

    if environment_id is None:
        return create_environment(
            workspace_id,
            display_name=display_name,
            item_definition=item_definition,
            description=description,
            folder=folder_id,
            df=False,
        )

    else:
        return update_environment_definition(
            workspace_id,
            environment_id,
            item_definition=item_definition,
            df=False,
        )


def deploy_all_environments(
    workspace: str,
    path: str,
    start_path: Optional[str] = None,
) -> None:
    """
    Deploy all environments to workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        path (str): The path to the environments.
        start_path (Optional[str]): The starting path for folder creation.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    environments_paths = list_paths_of_type(path, 'Environment')

    for path_ in environments_paths:

        display_name = extract_display_name_from_platform(path_)
        if display_name is None:
            return None

        environment_id = resolve_environment(workspace_id, display_name)

        folder_path_string = extract_middle_path(path_, start_path=start_path)
        folder_id = create_folders_from_path_string(
            workspace_id, folder_path_string
        )

        item_definition = pack_item_definition(path_)

        if environment_id is None:
            create_environment(
                workspace_id,
                display_name=display_name,
                item_definition=item_definition,
                folder=folder_id,
                df=False,
            )

        else:
            update_environment_definition(
                workspace_id,
                environment_id,
                item_definition=item_definition,
                df=False,
            )

    logger.success(
        f'All environments were deployed to workspace "{workspace}" successfully.'
    )
    return None
