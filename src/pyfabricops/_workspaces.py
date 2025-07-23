import os
from typing import Dict, List, Literal

import pandas

from ._capacities import get_capacity
from ._core import api_core_request, pagination_handler
from ._decorators import df
from ._exceptions import OptionNotAvailableError, ResourceNotFoundError
from ._generic_endpoints import (
    _post_generic,
    _delete_generic,
    _get_generic,
    _list_generic,
    _patch_generic
)
from ._logging import get_logger
from ._utils import (
    get_current_branch,
    get_workspace_suffix,
    is_valid_uuid,
    read_json,
    write_json,
)

logger = get_logger(__name__)


@df
def list_workspaces(df: bool = True) -> list | pandas.DataFrame | None:
    """
    Returns a list of workspaces.

    Args:
        df (bool): If True, returns a pandas DataFrame. Defaults to True.
        **kwargs: Additional keyword arguments for the API request.

    Returns:
        list | pandas.DataFrame | None: A list of workspaces or a DataFrame if df is True.
    """
    return _list_generic('workspaces')


@df
def get_workspace(
    workspace_id: str, df: bool = True
) -> list | pandas.DataFrame | None:
    """
    Returns the specified workspace.

    Args:
        workspace (str): The ID of the workspace to retrieve.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame) The details of the workspace if found, otherwise None. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        get_workspace('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    return _get_generic('workspaces', item_id=workspace_id)


@df
def create_workspace(
    display_name: str,
    *,
    capacity_id: str = None,
    description: str = None,
    df=True,
) -> Dict | None:
    """
    Create a new workspace with the specified name, capacity and description.

    Args:
        workspace_name (str): The name of the workspace to create.
        capacity (str, optional): The ID or name of the capacity to assign to the workspace. Defaults to None.
        description (str, optional): A description for the workspace. Defaults to None.
        roles (List[Dict[str, str]], optional): A list of roles to assign to the workspace. Defaults to None.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame): The details of the created or updated workspace if successful, otherwise None. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        # Create a Fabric Workspace with role assignment
        create_workspace(
            'MyNewWorkspace',
            capacity='cap-1234',
            description='This is a new workspace.',
            roles=[{
                'user_uuid': 'FefEFewf-feF-1234-5678-9abcdef01234',
                'user_type': 'User',
                'role': 'Admin'
            }]
        )

        # Create a Power BI Pro Workspace and return as dataframe
        create_workspace(
            'MyProject',
            description='This is my Power BI Pro Workspace.',
            df=True
        )
        ```
    """
    payload = {'displayName': display_name}

    if capacity_id:
        payload['capacityId'] = capacity_id

    if description:
        payload['description'] = description

    return _post_generic('workspaces', payload=payload)


@df
def update_workspace(
    workspace_id: str,
    display_name: str,
    *,
    description: str = None,
    df=True,
) -> dict | pandas.DataFrame:
    """
    Updates the properties of a workspace.

    Args:
        workspace (str): The workspace object to update.
        display_name (str, optional): The new name for the workspace.
        description (str, optional): The new description for the workspace.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame): The updated workspace details. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        update_workspace('123e4567-e89b-12d3-a456-426614174000', display_name='New Workspace Name')
        update_workspace('MyProject', description='Updated description')
        ```
    """
    payload = {'displayName': display_name}

    if description:
        payload['description'] = description

    return _patch_generic('workspaces', item_id=workspace_id, payload=payload)


def delete_workspace(workspace_id: str) -> None:
    """
    Delete a workspace by name or ID.

    Args:
        workspace (str): The name or ID of the workspace to delete.

    Returns:
        None: If the workspace is successfully deleted.

    Raises:
        ResourceNotFoundError: If the specified workspace is not found.

    Examples:
        ```python
        delete_workspace('123e4567-e89b-12d3-a456-426614174000')
        delete_workspace('MyProject')
        ```
    """
    return _delete_generic('workspaces', item_id=workspace_id)


@df
def list_workspace_roles(
    workspace_id: str, *, df=True
) -> dict | pandas.DataFrame:
    """
    Lists all roles for a workspace.

    Args:
        workspace (str): The ID of the workspace to list roles for.
        df (bool, optional): If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame): A list of role assignments. If `df=True`, returns a DataFrame with flattened keys.


    Examples:
        ```python
        list_workspace_roles('123e4567-e89b-12d3-a456-426614174000')
        list_workspace_roles('MyProject', df=True) # returns a DataFrame with flattened keys
        ```
    """
    return _list_generic('role_assignments', workspace_id=workspace_id)  


@df
def get_workspace_role_assignment(
    workspace_id: str, user_uuid: str, *, df=True
) -> dict | pandas.DataFrame:
    """
    Retrieves the role of a user in a workspace.

    Args:
        workspace (str): The workspace to check.
        user_uuid (str): The UUID of the user to check.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame): The role assignment if found, otherwise None. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        get_workspace_role('123e4567-e89b-12d3-a456-426614174000', 'FefEFewf-feF-1234-5678-9abcdef01234')
        get_workspace_role('MyProject', 'FefEFewf-feF-1234-5678-9abcdef01234')
        ```
    """
    return _get_generic('role_assignments', workspace_id=workspace_id, item_id=user_uuid)


@df
def add_workspace_role_assignment(
    workspace_id: str,
    user_uuid: str,
    user_type: Literal[
        'User', 'Group', 'ServicePrincipal', 'ServicePrincipalProfile'
    ] = 'User',
    role: Literal['Admin', 'Contributor', 'Member', 'Viewer'] = 'Admin',
    *,
    df=True,
) -> dict | pandas.DataFrame:
    """
    Adds a permission to a workspace for a user.

    Args:
        workspace (str): The ID of the workspace.
        user_uuid (str): The UUID of the user.
        user_type (str): The type of user (options: User, Group, ServicePrincipal, ServicePrincipalProfile).
        role (str): The role to assign (options: admin, member, contributor, viewer).
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame): The role assignment details if successful, otherwise None. If `df=True`, returns a DataFrame with flattened keys.

    Raises:
        ResourceNotFoundError: If the specified workspace is not found.
        OptionNotAvailableError: If the user type or role is invalid.

    Examples:
        ```python
        add_workspace_role_assignment(
            '123e4567-e89b-12d3-a456-426614174000',
            'FefEFewf-feF-1234-5678-9abcdef01234', user_type='User', role='Admin'
        )

        add_workspace_role_assignment(
            'MyProject',
            'FefEFewf-feF-1234-5678-9abcdef01234', user_type='Group', role='Member',
            df=True
        )
        ```
    """
    if user_type not in [
        'User',
        'Group',
        'ServicePrincipal',
        'ServicePrincipalProfile',
    ]:
        raise OptionNotAvailableError(
            f'Invalid user type: {user_type}. Must be one of: User, Group, ServicePrincipal, ServicePrincipalProfile'
        )
    if role not in ['Admin', 'Contributor', 'Member', 'Viewer']:
        raise OptionNotAvailableError(
            f'Invalid role: {role}. Must be one of: Admin, Contributor, Member, Viewer'
        )
    payload = {'principal': {'id': user_uuid, 'type': user_type}, 'role': role}
    return _post_generic('role_assignments', workspace_id=workspace_id, payload=payload)


def delete_workspace_role_assignment(
    workspace_id: str, user_uuid: str
):
    """
    Removes a permission from a workspace for a user.

    Args:
        workspace_id (str): The ID of the workspace.
        workspace_role_assignment_id (str): The ID of the role assignment to remove.

    Returns:
        None: If the role assignment is successfully deleted.

    Examples:
    ```python
        delete_workspace_role_assignment('123e4567-e89b-12d3-a456-426614174000', 'FefEFewf-feF-1234-5678-9abcdef01234')
        delete_workspace_role_assignment('MyProject', 'FefEFewf-feF-1234-5678-9abcdef01234')
    ```
    """
    return _delete_generic('role_assignments', workspace_id=workspace_id, item_id=user_uuid)


def assign_to_capacity(workspace_id: str, capacity_id: str) -> None:
    """
    Assigns a workspace to a capacity.

    Args:
        workspace_id (str): The ID of the workspace to assign.
        capacity_id (str): The ID of the capacity to assign the workspace to.

    Returns:
        None: If the assignment is successful.

    Examples:
        ```python
        assign_to_capacity('123e4567-e89b-12d3-a456-426614174000', 'cap-1234')
        assign_to_capacity('MyProject', 'cap-1234')
        assign_to_capacity('MyOtherProject', 'b7e2c1a4-8f3e-4c2a-9d2e-7b1e5f6a8c9d')
        ```
    """
    payload = {'capacityId': capacity_id}
    response = _post_generic('assign_to_capacity', workspace_id=workspace_id, payload=payload)
    if not response:
        logger.success(f'Workspace {workspace_id} assigned to capacity {capacity_id} successfully.')
    return response


def unassign_from_capacity(workspace_id: str) -> None:
    """
    Unassigns a workspace from its current capacity.

    Args:
        workspace (str): The ID of the workspace to unassign.

    Returns:
        None: If the unassignment is successful.

    Examples:
        ```python
        unassign_from_capacity('123e4567-e89b-12d3-a456-426614174000')
        unassign_from_capacity('MyProject')
        ```
    """
    response = _post_generic('unassign_from_capacity', workspace_id=workspace_id)
    if not response:
        logger.success(f'Workspace {workspace_id} unassigned from capacity successfully.')
    return response


def _get_workspace_config(
    workspace: str,
    *,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
):
    """
    Retrieves the workspace configuration for a given workspace, branch, and optional suffix.

    Args:
        workspace (str): The ID or name of the workspace to retrieve configuration for.
        branch (str, optional): The branch name to use for the configuration. If not provided, the current branch is used.
        workspace_suffix (str, optional): The suffix to append to the workspace name. If not provided, it will be determined from branches.json.
        branches_path (str, optional): The path to branches.json. If not provided, it defaults to the root path.

    Returns:
        dict: A dictionary containing the workspace configuration details, including workspace ID, name, description, capacity ID, region, and roles.

    Examples:
        ```python
        get_workspace_config_flow('123e4567-e89b-12d3-a456-426614174000')
        get_workspace_config_flow('MyProject', branch='main', workspace_suffix='-PRD')
        ```
    """
    # Retrieving details from the workspace
    workspace_details = get_workspace(workspace)
    if not workspace_details:
        raise ResourceNotFoundError(f'Workspace {workspace} not found.')

    workspace_name = workspace_details.get('displayName', '')
    workspace_id = workspace_details.get('id', '')
    workspace_description = workspace_details.get('description', '')
    capacity_id = workspace_details.get('capacityId', '')
    capacity_region = workspace_details.get('capacityRegion', '')

    # Retrieving workspace roles
    # Retrieve details
    roles_details = list_workspace_roles(workspace_id)

    # Init a empty list
    roles = []

    # Iterate for each role details
    for role in roles_details:
        principal_type = role['principal']['type']
        role_entry = {
            'user_uuid': role['id'],
            'user_type': principal_type,
            'role': role['role'],
            'display_name': role['principal'].get('displayName', ''),
        }

        if principal_type == 'Group':
            group_details = role['principal'].get('groupDetails', {})
            role_entry['group_type'] = group_details.get('groupType', '')
            role_entry['email'] = group_details.get('email', '')
        elif principal_type == 'User':
            user_details = role['principal'].get('userDetails', {})
            role_entry['user_principal_name'] = user_details.get(
                'userPrincipalName', ''
            )
        elif principal_type == 'ServicePrincipal':
            spn_details = role['principal'].get('servicePrincipalDetails', {})
            role_entry['app_id'] = spn_details.get('aadAppId', '')

        roles.append(role_entry)

    # Create a empty dict
    workspace_config = {}
    workspace_config['workspace_config'] = {}

    # Populate the dict
    workspace_config['workspace_config']['workspace_id'] = workspace_id
    workspace_config['workspace_config']['workspace_name'] = workspace_name
    workspace_config['workspace_config'][
        'workspace_description'
    ] = workspace_description
    workspace_config['workspace_config']['capacity_id'] = capacity_id
    workspace_config['workspace_config']['capacity_region'] = capacity_region
    workspace_config['workspace_config']['workspace_roles'] = roles

    if not workspace_config:
        return None

    # Get branch
    branch = get_current_branch(branch)

    # Get the workspace suffix and treating the name
    workspace_suffix = get_workspace_suffix(
        branch, workspace_suffix, branches_path
    )
    workspace_name_without_suffix = workspace_config['workspace_config'][
        'workspace_name'
    ].split(workspace_suffix)[0]

    # Build the config
    config = {}
    config[branch] = {}
    config[branch][workspace_name_without_suffix] = workspace_config

    return config


def export_workspace_config(
    workspace: str,
    project_path: str,
    *,
    config_path: str = None,
    merge_mode: Literal['update', 'replace', 'preserve'] = 'update',
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
):
    """
    Exports the workspace configuration to a JSON file, merging with existing configurations.

    Args:
        workspace (str): Workspace name or ID
        project_path (str): Path to the project directory
        merge_mode (str): How to handle existing data:
            - 'update': Update existing workspace config (default)
            - 'replace': Replace entire branch config
            - 'preserve': Only add if workspace doesn't exist
        branch (str, optional): Branch name
        workspace_suffix (str, optional): Workspace suffix
        branches_path (str, optional): Path to branches.json


    Returns:
        None: If the operation is successful, writes to the specified path.

    Examples:
        ```python
        # Export workspace configuration for a specific workspace with default configs.
        export_workspace_config('MyProject', project_path='/path/to/project')

        # Export workspace configuration for a specific workspace with custom branch and suffix.
        export_workspace_config('MyProject', project_path='/path/to/project', branch='dev', workspace_suffix='-DEV')

        # Export workspace configuration for a specific workspace with custom branches path.
        export_workspace_config('MyProject', project_path='/path/to/project', branches_path='/path/to/branches.json')
        ```
    """
    # Get the new config for this workspace
    new_config = _get_workspace_config(
        workspace,
        branch=branch,
        workspace_suffix=workspace_suffix,
        branches_path=branches_path,
    )

    if not config_path:
        config_path = os.path.join(project_path, 'config.json')

    # Create path if not exists
    if not os.path.exists(os.path.dirname(config_path)):
        os.makedirs(os.path.dirname(config_path), exist_ok=True)

    # Try to read existing config.json
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

    # Process each branch in new config
    for branch_name, workspaces in new_config.items():
        if merge_mode == 'replace':
            # Replace entire branch
            existing_config[branch_name] = workspaces
            logger.success(
                f'Replaced all workspaces in branch "{branch_name}"'
            )
        else:
            # Ensure branch exists in existing config
            if branch_name not in existing_config:
                existing_config[branch_name] = {}

            # Process each workspace
            for workspace_name, workspace_config in workspaces.items():

                workspace_name_without_suffix = workspace_name.split(
                    workspace_suffix
                )[0]

                if (
                    merge_mode == 'preserve'
                    and workspace_name_without_suffix
                    in existing_config[branch_name]
                ):
                    logger.info(
                        f'Workspace "{workspace_name}" already exists in branch "{branch_name}". Preserving existing config.'
                    )
                    continue

                # Ensure workspace exists in existing config
                if (
                    workspace_name_without_suffix
                    not in existing_config[branch_name]
                ):
                    existing_config[branch_name][
                        workspace_name_without_suffix
                    ] = {}

                # Merge workspace_config with existing data, preserving other keys like 'folders'
                if merge_mode == 'update':
                    # Update only the workspace_config, preserve other keys like 'folders'
                    existing_config[branch_name][
                        workspace_name_without_suffix
                    ]['workspace_config'] = workspace_config[
                        'workspace_config'
                    ]
                    logger.success(
                        f'Updated workspace_config for "{workspace_name}" in branch "{branch_name}"'
                    )
                else:
                    # For other modes, replace the entire workspace config
                    existing_config[branch_name][
                        workspace_name_without_suffix
                    ] = workspace_config
                    action = (
                        'Updated'
                        if workspace_name_without_suffix
                        in existing_config[branch_name]
                        else 'Added'
                    )
                    logger.info(
                        f'{action} workspace "{workspace_name}" in branch "{branch_name}"'
                    )

    # Write the updated configuration to the file
    write_json(existing_config, config_path)
    logger.success(
        f'Workspace configuration successfully written to {config_path}'
    )


def _resolve_workspace_path(
    workspace: str,
    project_path: str,
    *,
    workspace_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
) -> str | None:
    """Resolve workspace_name for export items"""
    workspace_name = get_workspace(workspace).get('displayName', '')
    if not workspace_name:
        logger.warning(f"Workspace '{workspace}' not found.")
        return None
    else:
        if not workspace_suffix:
            workspace_suffix = get_workspace_suffix(
                branch=branch,
                workspace_suffix=workspace_suffix,
                path=branches_path,
            )
        workspace_alias = workspace_name.split(workspace_suffix)[0]

    # Add the workspace path
    if not workspace_path:
        workspace_path = workspace_alias

    return workspace_path


def resolve_workspace(workspace: str, *, silent: bool = False) -> str:
    """
    Resolves a workspace name to its ID.

    Args:
        workspace (str): The name of the workspace.
        silent (bool, optional): If True, suppresses warnings. Defaults to False.

    Returns:
        str: The ID of the workspace, or None if not found.

    Examples:
        ```python
        resolve_workspace('123e4567-e89b-12d3-a456-426614174000')
        resolve_workspace('MyProject')
        ```
    """
    if is_valid_uuid(workspace):
        return workspace

    workspaces = list_workspaces(df=False)
    if not workspaces:
        raise ResourceNotFoundError(f'No workspaces found.')

    for _workspace in workspaces:
        if _workspace['displayName'] == workspace:
            return _workspace['id']

    # If we get here, workspace was not found
    if not silent:
        logger.warning(f"Workspace '{workspace}' not found.")
    return None
