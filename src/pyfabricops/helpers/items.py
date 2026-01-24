import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

from pandas import DataFrame

from ..core.workspaces import resolve_workspace
from ..helpers.folders import (
    create_folders_from_path_string,
    resolve_folder_from_id_to_path,
)
from ..items.items import (
    create_item,
    get_item,
    get_item_definition,
    list_items,
    resolve_item,
    update_item_definition,
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


def export_item(
    workspace: str,
    item: str,
    path: str,
):
    """
    Exports a item definition to a specified folder structure.

    Args:
        workspace (str): The workspace name or ID.
        item (str): The name of the item to export.
        path (str): The root path of the project.

    Examples:
        ```python
        export_item('MyProjectWorkspace', 'SalesDataModel', '/path/to/project')
        export_item('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', '/path/to/project')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    item_ = get_item(workspace_id, item, df=False)
    if not item_:
        return None

    item_id = item_['id']
    definition = get_item_definition(workspace_id, item_id)
    if not definition:
        return None

    item_type = item_['type']
    item_name = item_['displayName']

    folder_id = None
    folder_path = None

    if 'folderId' in item_:
        folder_id = item_['folderId']
        try:
            folder_path = resolve_folder_from_id_to_path(
                workspace_id, folder_id
            )
        except:
            logger.info(f'{item_name}.{item_type} is not inside a folder.')
            folder_path = None

    if folder_path is None:
        item_path = Path(path) / f'{item_name}.{item_type}'
    else:
        item_path = Path(path) / folder_path / f'{item_name}.{item_type}'

    os.makedirs(item_path, exist_ok=True)

    unpack_item_definition(definition, item_path)

    logger.success(
        f'{item_name}.{item_type} was exported to {item_path} successfully.'
    )
    return None


def export_all_items(
    workspace: str,
    path: str,
) -> None:
    """
    Exports all items to the specified folder structure.

    Args:
        workspace (str): The workspace name or ID.
        path (str): The root path of the project.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    items = list_items(workspace_id, df=False)

    if items is None:
        return None

    items = [item for item in items if item['type'] != 'SQLEndpoint']

    for item in items:
        item_id = item['id']
        item_ = get_item(workspace_id, item_id, df=False)
        if not item_:
            return None

        item_id = item_['id']
        item_name = item_['displayName']
        item_type = item_['type']

        definition = get_item_definition(workspace_id, item_id)
        if not definition:
            return None

        folder_id = None
        folder_path = None

        if 'folderId' in item_:
            folder_id = item_['folderId']

            try:
                folder_path = resolve_folder_from_id_to_path(
                    workspace_id, folder_id
                )
            except:
                logger.info(
                    f'{item["displayName"]}.{item_type} is not inside a folder.'
                )
                folder_path = None

        if folder_path is None:
            item_path = Path(path) / f'{item_name}.{item_type}'
        else:
            item_path = Path(path) / folder_path / f'{item_name}.{item_type}'
        os.makedirs(item_path, exist_ok=True)

        unpack_item_definition(definition, item_path)

        logger.success(
            f'{item_name}.{item_type} was exported to {item_path} successfully.'
        )
    return None


@df
def deploy_item(
    workspace: str,
    path: str,
    start_path: Optional[str] = None,
    description: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Creates or updates a item in Fabric based on local folder structure.
    Automatically detects the folder_id based on where the item is located locally.

    Args:
        workspace (str): The workspace name or ID.
        path (str): The root path of the project.
        start_path (str, optional): The starting path for the item.
        description (str, optional): A description for the item.
        df (bool, optional): Whether to return a DataFrame. Defaults to True.
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    display_name = extract_display_name_from_platform(path)
    if display_name is None:
        return None

    item_id = resolve_item(workspace_id, display_name)

    folder_path_string = extract_middle_path(path, start_path=start_path)
    folder_id = create_folders_from_path_string(
        workspace_id, folder_path_string
    )

    item_definition = pack_item_definition(path)

    if item_id is None:
        return create_item(
            workspace_id,
            display_name=display_name,
            item_definition=item_definition,
            description=description,
            folder=folder_id,
            df=False,
        )

    else:
        return update_item_definition(
            workspace_id,
            item_id,
            item_definition=item_definition,
            df=False,
        )


def deploy_all_items(
    workspace: str,
    path: str,
    start_path: Optional[str] = None,
) -> None:
    """
    Deploy all items to workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        path (str): The path to the notebooks.
        start_path (Optional[str]): The starting path for folder creation.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    types = ['Notebook', 'DataPipeline', 'Dataflow', 'SemanticModel', 'Report']
    for type in types:
        item_paths = list_paths_of_type(path, type)

        for path_ in item_paths:

            display_name = extract_display_name_from_platform(path_)
            if display_name is None:
                return None

            item_id = resolve_item(workspace_id, display_name)

            folder_path_string = extract_middle_path(
                path_, start_path=start_path
            )
            folder_id = create_folders_from_path_string(
                workspace_id, folder_path_string
            )

            item_definition = pack_item_definition(path_)

            if item_id is None:
                create_item(
                    workspace_id,
                    display_name=display_name,
                    item_definition=item_definition,
                    folder=folder_id,
                    df=False,
                )

            else:
                update_item_definition(
                    workspace_id,
                    item_id,
                    item_definition=item_definition,
                    df=False,
                )

    logger.success(
        f'All items were deployed to workspace "{workspace}" successfully.'
    )
    return None
