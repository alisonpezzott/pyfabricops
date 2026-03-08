import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from pandas import DataFrame

from ..core.workspaces import resolve_workspace
from ..helpers.folders import resolve_folder_from_id_to_path
from ..items.items import list_items
from ..items.lakehouses import get_lakehouse, list_lakehouses
from ..items.shortcuts import list_shortcuts
from ..utils.decorators import df
from ..utils.logging import get_logger
from ..utils.schemas import PLATFORM_SCHEMA, PLATFORM_VERSION

logger = get_logger(__name__)


def _generate_lakehouse_platform(
    display_name: str,
    description: Optional[str] = '',
) -> Dict[str, Any]:
    """
    Generate the lakehouse .platform file

    Args:
        display_name (str): The lakehouse display name.
        description (str): The lakehouse's description.

    Returns:
        (Dict[str, Any]): The .platform dict.
    """
    return {
        '$schema': PLATFORM_SCHEMA,
        'metadata': {
            'type': 'Lakehouse',
            'displayName': display_name,
            'description': description,
        },
        'config': {
            'version': PLATFORM_VERSION,
            'logicalId': '00000000-0000-0000-0000-000000000000',
        },
    }


def _save_lakehouse_platform(
    platform: Dict[str, Any],
    path: str,
) -> None:
    """
    Save the lakehouses's .platform in path

    Args:
        platform (Dict[str, Any]): The .platform dict.
        path (str): The lakehouse directory path to save to.
    """
    with open(Path(path) / '.platform', 'w') as f:
        json.dump(platform, f, indent=2)


def _save_lakehouse_metadata_json(path: str) -> None:
    """
    Save metadata.json to lakehouse's path

    Args:
        path (str): The lakehouse's path
    """
    with open(Path(path) / 'metadata.json', 'w') as f:
        json.dump({}, f, indent=2)


def get_lakehouse_config(
    workspace: str, lakehouse: str
) -> Union[Dict[str, Any], None]:
    """
    Get a specific lakehouse config from a workspace.

    Args:
        workspace (str): The name or ID from the workspace.
        lakehouse (str): The name or ID from the lakehouse.

    Returns:
        (Union[Dict[str, Any], None]): The dict config from the lakehouse
    """
    item = lakehouse
    item_data = get_lakehouse(workspace, item, df=False)

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
            'sql_endpoint_connection_string': item_data.get(
                'properties_sqlEndpointProperties_connectionString'
            ),
            'sql_endpoint_id': item_data.get(
                'properties_sqlEndpointProperties_id'
            ),
        }

        return config


def get_all_lakehouses_config(workspace: str) -> Union[Dict[str, Any], None]:
    """
    Generate lakehouses config from a workspace.

    Args:
        workspace (str): The name or ID from the workspace.

    Returns:
        (Union[Dict[str, Any], None]): The dict config from the lakehouses of the workspace
    """
    items = list_valid_lakehouses(workspace, df=False)

    if items is None:
        return None

    config = {}

    for item in items:

        item_data = get_lakehouse(workspace, item['id'], df=False)

        config[item['displayName']] = {
            'id': item['id'],
            'description': item.get('description', None),
            'folder_id': ''
            if item.get('folderId') is None or pd.isna(item.get('folderId'))
            else item['folderId'],
            'sql_endpoint_connection_string': item_data['properties'][
                'sqlEndpointProperties'
            ]['connectionString'],
            'sql_endpoint_id': item_data['properties'][
                'sqlEndpointProperties'
            ]['id'],
        }

    return config


@df
def list_valid_lakehouses(
    workspace: str,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Generate a list of valid lakehouses from a workspace.

    Args:
        workspace (str): The name or ID from the workspace.

    Returns:
        (Union[Dict[str, Any], None]): The list of valids lakehouses of the workspace
    """
    items = list_lakehouses(workspace)

    if items is None:
        return None

    return items[
        ~items['displayName'].str.contains('staging', case=False, na=False)
    ].to_dict(orient='records')


def generate_lakehouse_shortcuts_metadata(
    workspace: str, lakehouse: str
) -> Union[Dict[str, Any], None]:
    """ """
    # Create shortcuts.metadata.json
    shortcuts_list = list_shortcuts(workspace, lakehouse, df=False)

    if len(shortcuts_list) == 0:
        return None

    # Init a empty list for shortcuts
    shortcuts_list_new = []

    for shortcut_dict in shortcuts_list:
        shortcut_target = shortcut_dict['target']
        shortcut_target_type = (
            shortcut_target['type'][0].lower() + shortcut_target['type'][1:]
        )
        shortcut_target_workspace_id = shortcut_target[shortcut_target_type][
            'workspaceId'
        ]
        shortcut_target_item_id = shortcut_target[shortcut_target_type][
            'itemId'
        ]

        workspace_items = list_items(shortcut_target_workspace_id, df=False)
        for item in workspace_items:
            if item['id'] == shortcut_target_item_id:
                shortcut_target_item_type = item['type']
                break

    # Check if the workspace_id is equal shortcut_target_workspace_id then uuid zero
    if shortcut_target_workspace_id == resolve_workspace(workspace):
        shortcut_target_workspace_id = '00000000-0000-0000-0000-000000000000'

    # Create item type if not exists
    if 'artifactType' not in shortcut_dict['target'][shortcut_target_type]:
        shortcut_dict['target'][shortcut_target_type]['artifactType'] = ''
    if 'workspaceId' not in shortcut_dict['target'][shortcut_target_type]:
        shortcut_dict['target'][shortcut_target_type]['workspaceId'] = ''

    # Update if exists
    shortcut_dict['target']['oneLake'][
        'artifactType'
    ] = shortcut_target_item_type
    shortcut_dict['target']['oneLake'][
        'workspaceId'
    ] = shortcut_target_workspace_id

    shortcuts_list_new.append(shortcut_dict)

    return shortcuts_list_new


def save_lakehouse_shortcuts_metadata(
    shortcuts_metadata: Dict[str, Any], path: str
) -> None:
    """ """
    with open(Path(path) / 'shortcuts.metadata.json', 'w') as f:
        json.dump(shortcuts_metadata, f, indent=2)


def export_lakehouse(
    workspace: str,
    lakehouse: str,
    path: Union[str, Path],
) -> None:
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    item = get_lakehouse(workspace_id, lakehouse, df=False)
    if item is None:
        return None

    try:
        folder_path = resolve_folder_from_id_to_path(
            workspace_id, item['folderId']
        )
    except:
        logger.info(f'{item["displayName"]}.Lakehouse is not inside a folder.')
        folder_path = None

    if folder_path is None:
        item_path = Path(path) / (item['displayName'] + '.Lakehouse')
    else:
        item_path = (
            Path(path) / folder_path / (item['displayName'] + '.Lakehouse')
        )
    os.makedirs(item_path, exist_ok=True)

    platform = _generate_lakehouse_platform(
        display_name=item['displayName'],
        description=item['description'],
    )

    _save_lakehouse_platform(platform, item_path)

    _save_lakehouse_metadata_json(item_path)

    shortcuts = generate_lakehouse_shortcuts_metadata(workspace_id, item['id'])

    save_lakehouse_shortcuts_metadata(shortcuts, item_path)

    logger.success(
        f'Lakehouse `{lakehouse}` from workspace `{workspace}` was exported to `{path}` successfully.'
    )
    return None


def export_all_lakehouses(workspace: str, path: Union[str, Path]) -> None:
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    items = list_valid_lakehouses(workspace_id, df=False)
    if items is None:
        return None

    for item in items:
        try:
            folder_path = resolve_folder_from_id_to_path(
                workspace_id, item['folderId']
            )
        except:
            logger.info(
                f'{item["displayName"]}.Lakehouse is not inside a folder.'
            )
            folder_path = None

        if folder_path is None:
            item_path = Path(path) / (item['displayName'] + '.Lakehouse')
        else:
            item_path = (
                Path(path) / folder_path / (item['displayName'] + '.Lakehouse')
            )
        os.makedirs(item_path, exist_ok=True)

        platform = _generate_lakehouse_platform(
            display_name=item['displayName'],
            description=item['description'],
        )

        _save_lakehouse_platform(platform, item_path)

        _save_lakehouse_metadata_json(item_path)

        shortcuts = generate_lakehouse_shortcuts_metadata(
            workspace_id, item['id']
        )

        save_lakehouse_shortcuts_metadata(shortcuts, item_path)

    logger.success(f'All lakehouses exported to {path} successfully.')
    return None
