import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from pandas import DataFrame

from pyfabricops.items import shortcuts

from ..core.workspaces import resolve_workspace
from ..helpers.folders import resolve_folder_from_id_to_path
from ..items.items import list_items
from ..items.lakehouses import get_lakehouse, list_lakehouses
from ..items.shortcuts import list_shortcuts
from ..utils.decorators import df
from ..utils.logging import get_logger
from ..utils.schemas import PLATFORM_SCHEMA, PLATFORM_VERSION

logger = get_logger(__name__)


def generate_lakehouse_platform(
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


def save_lakehouse_platform(
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


def save_lakehouse_metadata_json(path: str) -> None:
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
    lakehouse_properties = get_lakehouse(workspace, lakehouse, df=False)

    if lakehouse_properties is None:
        return None

    else:
        config = {}
        config = config[lakehouse_properties.get('displayName')] = {}

        config = {
            'id': lakehouse_properties['id'],
            'description': lakehouse_properties.get('description', ''),
            'folder_id': lakehouse_properties.get('folderId', ''),
            'sql_endpoint_connection_string': lakehouse_details_properties.get(
                'properties_sqlEndpointProperties_connectionString'
            ),
            'sql_endpoint_id': lakehouse_details_properties.get(
                'properties_sqlEndpointProperties_id'
            ),
        }

        return config


def get_lakehouses_config(workspace: str) -> Union[Dict[str, Any], None]:
    """
    Generate lakehouses config from a workspace.

    Args:
        workspace (str): The name or ID from the workspace.

    Returns:
        (Union[Dict[str, Any], None]): The dict config from the lakehouses of the workspace
    """
    lakehouses = list_valid_lakehouses(workspace)

    if lakehouses is None:
        return None

    config = {}
    config['lakehouses'] = {}

    for index, row in lakehouses.iterrows():

        lakehouse_details_properties = get_lakehouse(workspace, row['id'])

        config['lakehouses'][row['displayName']] = {
            'id': row['id'],
            'description': row.get('description', ''),
            'folder_id': row.get('folderId', ''),
            'sql_endpoint_connection_string': lakehouse_details_properties[
                'properties_sqlEndpointProperties_connectionString'
            ].loc[0],
            'sql_endpoint_id': lakehouse_details_properties[
                'properties_sqlEndpointProperties_id'
            ].loc[0],
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
    lakehouses = list_lakehouses(workspace)

    if lakehouses is None:
        return None

    return lakehouses[
        ~lakehouses['displayName'].str.contains(
            'staging', case=False, na=False
        )
    ].to_dict(orient='records')


def generate_lakehouse_shortcuts_metadata(
    workspace: str, lakehouse: str
) -> Union[Dict[str, Any], None]:
    """ """
    # Create shortcuts.metadata.json
    shortcuts_list = list_shortcuts(workspace, lakehouse, df=False)

    if shortcuts_list is None:
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


def export_all_lakehouses_from_workspace(
    workspace: str, path: Union[str, Path]
) -> None:
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
        except Exception as e:
            logger.error(
                f"Error resolving folder path for item {item['id']}: {e}"
            )
            folder_path = None

        if folder_path is None:
            item_path = Path(path) / (item['displayName'] + '.Lakehouse')
        else:
            item_path = (
                Path(path) / folder_path / (item['displayName'] + '.Lakehouse')
            )
        os.makedirs(item_path, exist_ok=True)

        platform = generate_lakehouse_platform(
            display_name=item['displayName'],
            description=item['description'],
        )

        save_lakehouse_platform(platform, item_path)

        save_lakehouse_metadata_json(item_path)

        shortcuts = generate_lakehouse_shortcuts_metadata(
            workspace_id, item['id']
        )

        save_lakehouse_shortcuts_metadata(shortcuts, item_path)

    logger.success(f'All lakehouses exported to {path} successfully.')
    return None
