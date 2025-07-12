import json
import logging
import os
import time
import uuid
from collections import OrderedDict

import pandas

from ._core import api_core_request, pagination_handler
from ._decorators import df
from ._folders import resolve_folder
from ._scopes import PLATFORM_SCHEMA, PLATFORM_VERSION
from ._utils import (
    get_current_branch,
    get_workspace_suffix,
    is_valid_uuid,
    read_json,
    write_json,
)
from ._warehouses_support import (
    WAREHOUSE_DEFAULT_SEMANTIC_MODEL_TXT,
    WAREHOUSE_SQL_PROJECT,
    WAREHOUSE_XMLA_JSON,
)
from ._workspaces import get_workspace, resolve_workspace

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


@df
def list_warehouses(
    workspace: str, excluded_starts: tuple = ('Staging'), *, df: bool = False
) -> list | pandas.DataFrame:
    """
    Returns a list of warehouses from the specified workspace.
    This API supports pagination.

    Args:
        workspace (str): The workspace name or ID.
        excluded_starts (tuple): A tuple of prefixes to exclude from the list.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (list|pandas.DataFrame): A list of warehouses, excluding those that start with the specified prefixes. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        list_warehouses('MyProjectWorkspace')
        list_warehouses('MyProjectWorkspace', excluded_starts=('Staging', 'ware'))
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/warehouses'
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        response = pagination_handler(response)
    warehouses = [
        item
        for item in response.data.get('value', [])
        if not item['displayName'].startswith(excluded_starts)
    ]
    if not warehouses:
        logger.warning(
            f"No valid warehouses found in workspace '{workspace}'."
        )
        return None
    else:
        return warehouses


def resolve_warehouse(
    workspace: str, warehouse: str, *, silent: bool = False
) -> str | None:
    """
    Resolves a warehouse name to its ID.

    Args:
        workspace (str): The ID of the workspace.
        warehouse (str): The name of the warehouse.

    Returns:
        str: The ID of the warehouse, or None if not found.

    Examples:
        ```python
        resolve_warehouse('MyProjectWorkspace', 'SalesDatawarehouse')
        ```
    """
    if is_valid_uuid(warehouse):
        return warehouse

    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    warehouses = list_warehouses(workspace, df=False)
    if not warehouses:
        return None

    for warehouse_ in warehouses:
        if warehouse_['displayName'] == warehouse:
            return warehouse_['id']
    if not silent:
        logger.warning(f"Warehouse '{warehouse}' not found.")
    return None


@df
def get_warehouse(
    workspace: str, warehouse: str, *, silent: bool = False, df: bool = False
) -> dict | pandas.DataFrame | None:
    """
    Retrieves a warehouse by its name or ID from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        warehouse (str): The name or ID of the warehouse.
        silent (bool, optional): If True, suppresses warnings. Defaults to False.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame): The warehouse details if found. If `df=True`, returns a DataFrame with flattened keys.

    Examples:```python

    get_warehouse('MyProjectWorkspace', 'SalesDatawarehouse')
    get_warehouse('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
    get_warehouse('123e4567-e89b-12d3-a456-426614174000', 'SalesDatawarehouse', df=True)
    ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None
    warehouse_id = resolve_warehouse(workspace_id, warehouse)
    if not warehouse_id:
        return None

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/warehouses/{warehouse_id}',
        method='get',
    )
    if not response.success and not silent:
        logger.warning(
            f'No warehouse found with ID: {warehouse_id} in workspace {workspace_id}.'
        )
        return None

    warehouse_sql_endpoint = response.data['properties']['connectionString']

    if warehouse_sql_endpoint:
        return response.data

    else:
        MAX_RETRIES = 10
        RETRY_INTERVAL = 10
        logger.info(f'Checking warehouse SQL endpoint...')
        for attempt in range(1, MAX_RETRIES + 1):
            response = api_core_request(
                endpoint=f'/workspaces/{workspace_id}/warehouses/{warehouse_id}',
                method='get',
            )
            if not response.success:
                logger.warning(
                    f'Failed to retrieve warehouse {warehouse_id} in workspace {workspace_id}.'
                )
                return None
            warehouse_sql_endpoint = response.data['properties'][
                'connectionString'
            ]
            if warehouse_sql_endpoint:
                logger.info('Warehouse SQL endpoint is now available.')
                break
            time.sleep(RETRY_INTERVAL)
        return response.data


@df
def create_warehouse(
    workspace: str,
    display_name: str,
    description: str = '',
    folder: str = '',
    enable_schemas: bool = False,
    *,
    df: bool = False,
) -> dict | pandas.DataFrame | None:
    """
    Create a warehouse in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name for the new warehouse.
        description (str, optional): A description for the new warehouse.
        folder (str, optional): The folder path where the warehouse should be created.
        enable_schemas (bool, optional): If True, enables schema creation for the warehouse.
        df (bool, optional): If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame | None): The created warehouse details if successful, otherwise None.

    Examples:
        ```python
        create_warehouse('MyProjectWorkspace', 'SalesDatawarehouse')
        create_warehouse('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
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
    warehouse_exists = get_warehouse(workspace_id, display_name)
    if warehouse_exists:
        logger.warning(f"Warehouse with name '{display_name}' already exists.")
        return warehouse_exists
    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/warehouses',
        method='post',
        payload=payload,
    )
    if not response.success:
        logger.warning(
            f"Failed to create warehouse '{display_name}' in workspace '{workspace}': {response.error}"
        )
        return None
    else:
        return response.data


@df
def update_warehouse(
    workspace: str,
    warehouse: str,
    display_name: str = None,
    description: str = None,
    *,
    df: bool = False,
) -> dict | pandas.DataFrame:
    """
    Updates the properties of the specified warehouse.

    Args:
        workspace (str): The workspace name or ID.
        warehouse (str): The name or ID of the warehouse to update.
        display_name (str, optional): The new display name for the warehouse.
        description (str, optional): The new description for the warehouse.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or None): The updated warehouse details if successful, otherwise None.

    Examples:
        ```python
        update_warehouse('MyProjectWorkspace', 'SalesDatawarehouse', display_name='UpdatedSalesDatawarehouse')
        update_warehouse('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', description='Updated description')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    warehouse_id = resolve_warehouse(workspace_id, warehouse)
    if not warehouse_id:
        return None

    warehouse_ = get_warehouse(workspace_id, warehouse_id)
    if not warehouse_:
        return None

    warehouse_description = warehouse_['description']
    warehouse_display_name = warehouse_['displayName']

    payload = {}

    if warehouse_display_name != display_name and display_name:
        payload['displayName'] = display_name

    if warehouse_description != description and description:
        payload['description'] = description

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/warehouses/{warehouse_id}',
        method='put',
        payload=payload,
    )

    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


def delete_warehouse(workspace: str, warehouse: str) -> None:
    """
    Delete a warehouse in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        warehouse (str): The name or ID of the warehouse to delete.

    Returns:
        None

    Examples:
        ```python
        delete_warehouse('MyProjectWorkspace', 'SalesDatawarehouse')
        delete_warehouse('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None
    warehouse_id = resolve_warehouse(workspace_id, warehouse)
    if not warehouse_id:
        return None

    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/warehouses/{warehouse_id}',
        method='delete',
        return_raw=True,
    )
    if not response.status_code == 200:
        logger.warning(f'{response.status_code}: {response.text}.')
        return False
    else:
        return True


def export_warehouse(
    workspace: str,
    warehouse: str,
    project_path: str = None,
    workspace_path: str = 'workspace',
    update_config: bool = True,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
) -> None:
    """
    Exports a warehouse from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        warehouse (str): The name or ID of the warehouse to export.
        project_path (str, optional): The path to the project directory. Defaults to None.
        workspace_path (str, optional): The path to the workspace directory. Defaults to 'workspace'.
        update_config (bool, optional): Whether to update the config file. Defaults to True.
        config_path (str, optional): The path to the config file. Defaults to None.
        branch (str, optional): The branch to use. Defaults to None.
        workspace_suffix (str, optional): The workspace suffix to use. Defaults to None.
        branches_path (str, optional): The path to the branches directory. Defaults to None.

    Returns:
        None

    Examples:
        ```python
        export_warehouse('MyProjectWorkspace', 'SalesDatawarehouse')
        export_warehouse('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    workspace_name = get_workspace(workspace_id).get('displayName')

    warehouse_ = get_warehouse(workspace_id, warehouse)
    if not warehouse_:
        return None

    warehouse_id = warehouse_['id']
    folder_id = None
    if 'folderId' in warehouse_:
        folder_id = warehouse_['folderId']

    warehouse_display_name = warehouse_['displayName']
    warehouse_description = warehouse_['description']
    platform = {
        'metadata': {
            'type': 'Warehouse',
            'displayName': warehouse_display_name,
            'description': warehouse_description,
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
            f'{item_path}/{warehouse_display_name}.Warehouse/.platform'
        )
        write_json(platform, definition_path_full)

        warehouse_name = warehouse_['displayName']
        warehouse_sql_str = warehouse_['properties']['connectionString']

        if 'description' not in warehouse_:
            warehouse_descr = ''
        else:
            warehouse_descr = warehouse_['description']

        if 'warehouses' not in config:
            config['warehouses'] = {}
        if warehouse_name not in config['warehouses']:
            config['warehouses'][warehouse_name] = {}
        if 'id' not in config['warehouses'][warehouse_name]:
            config['warehouses'][warehouse_name]['id'] = warehouse_id
        if 'description' not in config['warehouses'][warehouse_name]:
            config['warehouses'][warehouse_name][
                'description'
            ] = warehouse_descr

        if folder_id:
            if 'folder_id' not in config['warehouses'][warehouse_name]:
                config['warehouses'][warehouse_name]['folder_id'] = folder_id

        if (
            'sql_endpoint_connection_string'
            not in config['warehouses'][warehouse_name]
        ):
            config['warehouses'][warehouse_name][
                'sql_endpoint_connection_string'
            ] = warehouse_sql_str

        # Saving the updated config back to the config file
        existing_config[branch][workspace_name_without_suffix] = config
        write_json(existing_config, config_path)

    else:
        definition_path_full = f'{project_path}/{workspace_path}/{warehouse_display_name}.Warehouse/.platform'
        write_json(platform, definition_path_full)

    # Creating aditional fields in .platform
    with open(
        f'{item_path}/{warehouse_display_name}.Warehouse/.platform', 'r'
    ) as f:
        platform_content = json.load(f)

    if 'config' not in platform_content:
        platform_content['config'] = {}

        # Generate a unique ID
        logical_id = str(uuid.uuid4())

        platform_config = {
            'version': PLATFORM_VERSION,
            'logicalId': logical_id,
        }
        platform_content['config'] = platform_config

    if '$schema' not in platform_content:
        platform_content['$schema'] = ''
        platform_content['$schema'] = PLATFORM_SCHEMA

    sorted_platform = OrderedDict()
    sorted_platform['$schema'] = platform_content['$schema']
    sorted_platform['metadata'] = platform_content['metadata']
    sorted_platform['config'] = platform_content['config']

    with open(
        f'{item_path}/{warehouse_display_name}.Warehouse/.platform', 'w'
    ) as f:
        json.dump(sorted_platform, f, indent=2)

    # Creating a dummy sqlproj if not exists
    try:
        with open(
            f'{item_path}/{warehouse_display_name}.Warehouse/{warehouse_display_name}.sqlproj',
            'r',
        ) as f:
            sql_project = f.read()
    except:
        sql_project = WAREHOUSE_SQL_PROJECT.format(
            warehouse_display_name=warehouse_display_name
        )

    with open(
        f'{item_path}/{warehouse_display_name}.Warehouse/{warehouse_display_name}.sqlproj',
        'w',
    ) as f:
        f.write(sql_project)

    # Creating a dummy DefaultSemanticModel.txt
    try:
        with open(
            f'{item_path}/{warehouse_display_name}.Warehouse/DefaultSemanticModel.txt',
            'r',
        ) as f:
            default_semantic_model_txt = f.read()
    except:
        default_semantic_model_txt = WAREHOUSE_DEFAULT_SEMANTIC_MODEL_TXT

    with open(
        f'{item_path}/{warehouse_display_name}.Warehouse/DefaultSemanticModel.txt',
        'w',
    ) as f:
        f.write(default_semantic_model_txt)

    # Creating a dummy xmla.json
    try:
        with open(
            f'{item_path}/{warehouse_display_name}.Warehouse/xmla.json', 'r'
        ) as f:
            xmla_json = json.load(f)
    except:
        xmla_json = WAREHOUSE_XMLA_JSON

    with open(
        f'{item_path}/{warehouse_display_name}.Warehouse/xmla.json', 'w'
    ) as f:
        json.dump(xmla_json, f, indent=2)


def export_all_warehouses(
    workspace: str,
    project_path: str,
    workspace_path: str = 'workspace',
    update_config: bool = True,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
    excluded_starts: tuple = ('Staging',),
) -> None:
    """
    Exports all warehouses from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        project_path (str): The path to the project directory.
        workspace_path (str): The path to the workspace directory.
        update_config (bool): Whether to update the config file.
        config_path (str): The path to the config file.
        branch (str): The branch to use.
        workspace_suffix (str): The workspace suffix to use.
        branches_path (str): The path to the branches directory.
        excluded_starts (tuple): A tuple of folder names to exclude from the export.

    Returns:
        None

    Examples:
        ```python
        export_all_warehouses('MyProjectWorkspace')
        export_all_warehouses('MyProjectWorkspace', 'C:/path/to/project')
        export_all_warehouses('MyProjectWorkspace', 'C:/path/to/project', 'C:/path/to/workspace')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    warehouses = list_warehouses(
        workspace_id, excluded_starts=excluded_starts, df=False
    )

    if not warehouses:
        logger.warning(
            f"No valid warehouses found in workspace '{workspace}'."
        )
        return None
    else:
        for warehouse in warehouses:
            export_warehouse(
                workspace=workspace,
                warehouse=warehouse['displayName'],
                project_path=project_path,
                workspace_path=workspace_path,
                update_config=update_config,
                config_path=config_path,
                branch=branch,
                workspace_suffix=workspace_suffix,
                branches_path=branches_path,
            )
