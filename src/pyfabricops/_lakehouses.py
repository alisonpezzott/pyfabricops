import logging
import os
import time

import pandas

from ._core import api_core_request, pagination_handler
from ._decorators import df
from ._folders import resolve_folder
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
def list_lakehouses(
    workspace: str, excluded_starts: tuple = ('Staging'), *, df: bool = False
) -> list | pandas.DataFrame:
    """
    Returns a list of lakehouses from the specified workspace.
    This API supports pagination.

    Args:
        workspace (str): The workspace name or ID.
        excluded_starts (tuple): A tuple of prefixes to exclude from the list.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (list|pandas.DataFrame): A list of lakehouses, excluding those that start with the specified prefixes. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        list_lakehouses('MyProjectWorkspace')
        list_lakehouses('MyProjectWorkspace', excluded_starts=('Staging', 'Lake'))
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/lakehouses'
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        response = pagination_handler(response)
    lakehouses = [
        lk
        for lk in response.data.get('value', [])
        if not lk['displayName'].startswith(excluded_starts)
    ]
    if not lakehouses:
        logger.warning(
            f"No valid lakehouses found in workspace '{workspace}'."
        )
        return None
    else:
        return lakehouses


def resolve_lakehouse(
    workspace: str, lakehouse: str, *, silent: bool = False
) -> str | None:
    """
    Resolves a lakehouse name to its ID.

    Args:
        workspace (str): The ID of the workspace.
        lakehouse (str): The name of the lakehouse.
        silent (bool): If True, suppresses warnings. Defaults to False.

    Returns:
        str: The ID of the lakehouse, or None if not found.

    Examples:
        ```python
        resolve_lakehouse('MyProjectWorkspace', 'SalesDataLakehouse')
        ```
    """
    if is_valid_uuid(lakehouse):
        return lakehouse

    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    lakehouses = list_lakehouses(workspace, df=False)
    if not lakehouses:
        return None

    for lakehouse_ in lakehouses:
        if lakehouse_['displayName'] == lakehouse:
            return lakehouse_['id']
    if not silent:
        logger.warning(f"Lakehouse '{lakehouse}' not found.")
    return None


@df
def get_lakehouse(
    workspace: str, lakehouse: str, *, df: bool = False, silent: bool = False
) -> dict | pandas.DataFrame | None:
    """
    Retrieves a lakehouse by its name or ID from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        lakehouse (str): The name or ID of the lakehouse.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame): The lakehouse details if found. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        get_lakehouse('MyProjectWorkspace', 'SalesDataLakehouse')
        get_lakehouse('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        get_lakehouse('123e4567-e89b-12d3-a456-426614174000', 'SalesDataLakehouse', df=True)
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None
    lakehouse_id = resolve_lakehouse(workspace_id, lakehouse)
    if not lakehouse_id:
        return None

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/lakehouses/{lakehouse_id}',
        method='get',
    )
    if not response.success and not silent:
        logger.warning(
            f'No lakehouse found with ID: {lakehouse_id} in workspace {workspace_id}.'
        )
        return None

    lakehouse_sql_endpoint_id = response.data['properties'][
        'sqlEndpointProperties'
    ]['id']

    if lakehouse_sql_endpoint_id:
        return response.data

    else:
        MAX_RETRIES = 10
        RETRY_INTERVAL = 10
        logger.info(f'Checking lakehouse SQL endpoint...')
        for attempt in range(1, MAX_RETRIES + 1):
            response = api_core_request(
                endpoint=f'/workspaces/{workspace_id}/lakehouses/{lakehouse_id}',
                method='get',
            )
            if not response.success:
                logger.warning(
                    f'Failed to retrieve lakehouse {lakehouse_id} in workspace {workspace_id}.'
                )
                return None
            lakehouse_sql_endpoint_id = response.data['properties'][
                'sqlEndpointProperties'
            ]['id']
            if lakehouse_sql_endpoint_id:
                logger.info('Lakehouse SQL endpoint is now available.')
                break
            time.sleep(RETRY_INTERVAL)
        return response.data


@df
def create_lakehouse(
    workspace: str,
    display_name: str,
    description: str = '',
    folder: str = '',
    enable_schemas: bool = False,
    *,
    df: bool = False,
):
    """
    Create a lakehouse in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name for the lakehouse.
        description (str, optional): The description for the lakehouse.
        folder (str, optional): The folder to create the lakehouse in.
        enable_schemas (bool, optional): Whether to enable schemas for the lakehouse.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict | pandas.DataFrame | None): The created lakehouse details if successful, otherwise None.

    Examples:
        ```python
        create_lakehouse('MyProjectWorkspace', 'SalesDataLakehouse')
        create_lakehouse('MyProjectWorkspace', 'SalesDataLakehouse', description='Sales data lakehouse')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None
    payload = {'displayName': display_name}
    if description:
        payload['description'] = description
    if folder:
        folder_id = resolve_folder(workspace_id, folder)
        if not folder_id:
            return None
        payload['folderId'] = folder_id
    if enable_schemas:
        payload['creationPayload'] = {'enableSchemas': True}
    lake_exists = get_lakehouse(workspace_id, display_name)
    if lake_exists:
        logger.warning(f"Lakehouse with name '{display_name}' already exists.")
        return lake_exists
    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/lakehouses',
        method='post',
        payload=payload,
    )
    if not response.success:
        logger.warning(
            f"Failed to create lakehouse '{display_name}' in workspace '{workspace}': {response.error}"
        )
        return None
    else:
        return response.data


@df
def update_lakehouse(
    workspace: str,
    lakehouse: str,
    display_name: str = None,
    description: str = None,
    *,
    df: bool = False,
) -> dict | pandas.DataFrame:
    """
    Updates the properties of the specified lakehouse.

    Args:
        workspace (str): The workspace name or ID.
        lakehouse (str): The name or ID of the lakehouse to update.
        display_name (str, optional): The new display name for the lakehouse.
        description (str, optional): The new description for the lakehouse.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or None): The updated lakehouse details if successful, otherwise None.

    Examples:
        ```python
        update_lakehouse('MyProjectWorkspace', 'SalesDataLakehouse', display_name='UpdatedSalesDataLakehouse')
        update_lakehouse('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', description='Updated description')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    lakehouse_id = resolve_lakehouse(workspace_id, lakehouse)
    if not lakehouse_id:
        return None

    lakehouse_ = get_lakehouse(workspace_id, lakehouse_id)
    if not lakehouse_:
        return None

    lakehouse_description = lakehouse_['description']
    lakehouse_display_name = lakehouse_['displayName']

    payload = {}

    if lakehouse_display_name != display_name and display_name:
        payload['displayName'] = display_name

    if lakehouse_description != description and description:
        payload['description'] = description

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/lakehouses/{lakehouse_id}',
        method='put',
        payload=payload,
    )

    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


def delete_lakehouse(workspace: str, lakehouse: str):
    """
    Delete a lakehouse in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        lakehouse (str): The name or ID of the lakehouse to delete.

    Returns:
        (bool): True if the lakehouse was deleted successfully, otherwise False.

    Examples:
        ```python
        delete_lakehouse('MyProjectWorkspace', 'SalesDataLakehouse')
        delete_lakehouse('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None
    lakehouse_id = resolve_lakehouse(workspace_id, lakehouse)
    if not lakehouse_id:
        return None

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/lakehouses/{lakehouse_id}',
        method='delete',
        return_raw=True,
    )
    if not response.status_code == 200:
        logger.warning(f'{response.status_code}: {response.text}.')
        return False
    else:
        return True


def export_lakehouse(
    workspace: str,
    lakehouse: str,
    project_path: str = None,
    workspace_path: str = 'workspace',
    update_config: bool = True,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
) -> bool:
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    workspace_name = get_workspace(workspace_id).get('displayName')

    lakehouse_ = get_lakehouse(workspace_id, lakehouse)
    if not lakehouse_:
        return None

    lakehouse_id = lakehouse_['id']
    folder_id = None
    if 'folderId' in lakehouse_:
        folder_id = lakehouse_['folderId']

    lakehouse_display_name = lakehouse_['displayName']
    lakehouse_description = lakehouse_['description']
    platform = {
        'metadata': {
            'type': 'Lakehouse',
            'displayName': lakehouse_display_name,
            'description': lakehouse_description,
        }
    }

    if update_config:

        # Get branch
        branch = get_current_branch(branch)

        # Get the workspace suffix and treating the name
        workspace_suffix = get_workspace_suffix(
            branch, workspace_suffix, branches_path
        )
        workspace_name_without_suffix = workspace_name.split(workspace_suffix)[
            0
        ]

        # Try to read existing config.json
        if not config_path:
            config_path = os.path.join(project_path, 'config.json')
        try:
            existing_config = read_json(config_path)
            logger.info(
                f'Found existing config file at {config_path}, merging workspace config...'
            )
        except FileNotFoundError:
            logger.warning(
                f'No existing config found at {config_path}, creating a new one.'
            )
            existing_config = {}

        config = existing_config[branch][workspace_name_without_suffix]

        # Find the key in the folders dict whose value matches folder_id

        if folder_id:
            folders = config['folders']
            item_path = next(
                (k for k, v in folders.items() if v == folder_id), None
            )
            item_path = os.path.join(project_path, workspace_path, item_path)
        else:
            item_path = workspace_path

        definition_path_full = (
            f'{item_path}/{lakehouse_display_name}.Lakehouse/.platform'
        )
        write_json(platform, definition_path_full)

        lk_id = lakehouse_['id']
        lakehouse_name = lakehouse_['displayName']
        lakehouse_sql_str = lakehouse_['properties']['sqlEndpointProperties'][
            'connectionString'
        ]
        lakehouse_sql_id = lakehouse_['properties']['sqlEndpointProperties'][
            'id'
        ]

        if 'description' not in lakehouse_:
            lakehouse_descr = ''
        else:
            lakehouse_descr = lakehouse_['description']

        if 'lakehouses' not in config:
            config['lakehouses'] = {}
        if lakehouse_name not in config['lakehouses']:
            config['lakehouses'][lakehouse_name] = {}
        if 'id' not in config['lakehouses'][lakehouse_name]:
            config['lakehouses'][lakehouse_name]['id'] = lakehouse_id
        if 'description' not in config['lakehouses'][lakehouse_name]:
            config['lakehouses'][lakehouse_name][
                'description'
            ] = lakehouse_descr

        if folder_id:
            if 'folder_id' not in config['lakehouses'][lakehouse_name]:
                config['lakehouses'][lakehouse_name]['folder_id'] = folder_id

        if 'sql_endpoint_id' not in config['lakehouses'][lakehouse_name]:
            config['lakehouses'][lakehouse_name][
                'sql_endpoint_id'
            ] = lakehouse_sql_id

        if (
            'sql_endpoint_connection_string'
            not in config['lakehouses'][lakehouse_name]
        ):
            config['lakehouses'][lakehouse_name][
                'sql_endpoint_connection_string'
            ] = lakehouse_sql_str

        # Saving the updated config back to the config file
        existing_config[branch][workspace_name_without_suffix] = config
        write_json(existing_config, config_path)

    else:
        definition_path_full = f'{project_path}/{workspace_path}/{lakehouse_display_name}.Lakehouse/.platform'
        write_json(platform, definition_path_full)


def export_all_lakehouses(
    workspace: str,
    project_path: str,
    workspace_path: str = 'workspace',
    update_config: bool = True,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
    excluded_starts: tuple = ('Staging',),
) -> bool:
    """
    Exports all lakehouses in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        project_path (str): The path to the project directory.
        workspace_path (str, optional): The path to the workspace directory. Defaults to 'workspace'.
        update_config (bool, optional): Whether to update the config file. Defaults to True.
        config_path (str, optional): The path to the config file. Defaults to None.
        branch (str, optional): The branch name. Defaults to None.
        workspace_suffix (str, optional): The workspace suffix. Defaults to None.
        branches_path (str, optional): The path to the branches directory. Defaults to None.
        excluded_starts (tuple, optional): A tuple of strings to exclude from the start of lakehouse names. Defaults to ('Staging',).

    Returns:
        bool: True if all lakehouses were exported successfully, otherwise False.

    Examples:
        ```python
        export_all_lakehouses('MyProjectWorkspace', '/path/to/project')
        export_all_lakehouses('MyProjectWorkspace', '/path/to/project', workspace_path='my_workspace')
        export_all_lakehouses('MyProjectWorkspace', '/path/to/project', update_config=False)
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    lakehouses = list_lakehouses(
        workspace_id, excluded_starts=excluded_starts, df=False
    )

    if not lakehouses:
        logger.warning(
            f"No valid lakehouses found in workspace '{workspace}'."
        )
        return None
    else:
        for lakehouse in lakehouses:
            export_lakehouse(
                workspace=workspace,
                lakehouse=lakehouse['displayName'],
                project_path=project_path,
                workspace_path=workspace_path,
                update_config=update_config,
                config_path=config_path,
                branch=branch,
                workspace_suffix=workspace_suffix,
                branches_path=branches_path,
            )
