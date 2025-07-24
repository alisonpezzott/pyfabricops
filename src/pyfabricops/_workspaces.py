from typing import Dict, Literal

import pandas

from ._decorators import df
from ._exceptions import OptionNotAvailableError
from ._generic_endpoints import (
    _post_generic,
    _delete_generic,
    _get_generic,
    _list_generic,
    _patch_generic
)
from ._logging import get_logger

logger = get_logger(__name__)


@df
def list_workspaces(df: bool = True) -> pandas.DataFrame | list[dict] | None:
    """
    Returns a list of workspaces.

    Args:
        df (bool): If True, returns a pandas DataFrame. Defaults to True.

    Returns:
        (pandas.DataFrame | list | None): A list of workspaces or a DataFrame if df is True.
    
    Examples:
        ```python
        list_workspaces() # Returns as DataFrame
        list_workspaces(df=False) # Returns as list
        ```
    """
    return _list_generic('workspaces')


@df
def get_workspace(
    workspace_id: str, df: bool = True
) -> pandas.DataFrame | list[dict] | None:
    """
    Returns the specified workspace.

    Args:
        workspace_id (str): The ID of the workspace to retrieve.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (pandas.DataFrame | list[dict] | None) The details of the workspace if found, otherwise None. If `df=True`, returns a DataFrame with flattened keys.

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
) -> pandas.DataFrame | Dict | None:
    """
    Create a new workspace with the specified name, capacity and description.

    Args:
        display_name (str): The name of the workspace to create.
        capacity_id (str, optional): The ID or name of the capacity to assign to the workspace. Defaults to None.
        description (str, optional): A description for the workspace. Defaults to None.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (pandas.DataFrame | Dict | None): The details of the created or updated workspace if successful, otherwise None. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        create_workspace(
            'MyProject', 
            capacity_id='85974fbf-2c3b-4d5e-8f6a-7b8c9d0e1f2g',     
            description='My new project workspace',
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
    *,
    display_name: str = None,
    description: str = None,
    df=True,
) -> pandas.DataFrame | dict | None:
    """
    Updates the properties of a workspace.

    Args:
        workspace_id (str): The workspace object to update.
        display_name (str, optional): The new name for the workspace.
        description (str, optional): The new description for the workspace.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (pandas.DataFrame | dict | None): The updated workspace details. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        update_workspace(
            '123e4567-e89b-12d3-a456-426614174000', 
            display_name='New Workspace Name',
        )
        
        update_workspace(
            '123e4567-e89b-12d3-a456-426614174000', 
            description='Updated description',
        )

        update_workspace(
            '123e4567-e89b-12d3-a456-426614174000', 
            display_name='New Workspace Name', 
            description='Updated description',
        )
        ```
    """
    if not display_name and not description:
        logger.warning(
            'No changes provided. Please specify at least one property to update.'
        )
        return None
    
    payload = {}
    if display_name:
        payload['displayName'] = display_name
    if description:
        payload['description'] = description

    return _patch_generic('workspaces', item_id=workspace_id, payload=payload)


def delete_workspace(workspace_id: str) -> None:
    """
    Delete a workspace.

    Args:
        workspace_id (str): The ID of the workspace to delete.

    Returns:
        None

    Raises:
        ResourceNotFoundError: If the specified workspace is not found.

    Examples:
        ```python
        delete_workspace('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    return _delete_generic('workspaces', item_id=workspace_id)


@df
def list_workspace_roles(
    workspace_id: str, *, df=True
) -> pandas.DataFrame | list[dict] | None:
    """
    Lists all roles for a workspace.

    Args:
        workspace_id (str): The ID of the workspace to list roles for.
        df (bool, optional): If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (pandas.DataFrame | list[dict] | None): A list of role assignments. If `df=True`, returns a DataFrame with flattened keys.


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
) -> pandas.DataFrame | dict | None:
    """
    Retrieves the role of a user in a workspace.

    Args:
        workspace (str): The workspace to check.
        user_uuid (str): The UUID of the user to check.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (pandas.DataFrame | dict | None): The role assignment if found, otherwise None.

    Examples:
        ```python
        get_workspace_role_assignment(
            '123e4567-e89b-12d3-a456-426614174000', 
            'FefEFewf-feF-1234-5678-9abcdef01234'
        )
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
) -> pandas.DataFrame | dict | None:
    """
    Adds a permission to a workspace for a user.

    Args:
        workspace_id (str): The ID of the workspace.
        user_uuid (str): The UUID of the user.
        user_type (str): The type of user (options: User, Group, ServicePrincipal, ServicePrincipalProfile).
        role (str): The role to assign (options: admin, member, contributor, viewer).
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (pandas.DataFrame | dict | None): The role assignment details if successful, otherwise None. If 'df=False', returns a dict with the role assignment details.

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


@df
def update_workspace_role_assignment(
    workspace_id: str, 
    user_uuid: str, 
    role: Literal['Admin', 'Contributor', 'Member', 'Viewer'] = 'Admin', 
    *,
    df: bool = True,
) -> pandas.DataFrame | dict | None:
    """
    Update a role to a existing workspace role assignment.

    Args: 
        workspace_id (str): The ID of the workspace.
        user_uuid (str): The UUID of the user.
        role (str): The new role to assign (options: admin, member, contributor, viewer).
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (pandas.DataFrame | dict | None): The updated role assignment details if successful, otherwise None. If 'df=True', returns a DataFrame with flattened keys.

    Raises:
        ResourceNotFoundError: If the specified workspace or user is not found.
        OptionNotAvailableError: If the role is invalid.

    Examples:
        ```python
        update_workspace_role_assignment(
            '123e4567-e89b-12d3-a456-426614174000', 
            'FefEFewf-feF-1234-5678-9abcdef01234', 
            role='Contributor'
        )
    """
    if role not in ['Admin', 'Contributor', 'Member', 'Viewer']:
        raise OptionNotAvailableError(
            f'Invalid role: {role}. Must be one of: Admin, Contributor, Member, Viewer'
        )
    
    payload = {'role': role}
    return _patch_generic('role_assignments', workspace_id=workspace_id, item_id=user_uuid, payload=payload)


def delete_workspace_role_assignment(
    workspace_id: str, user_uuid: str
) -> None:
    """
    Removes a permission from a workspace for a user.

    Args:
        workspace_id (str): The ID of the workspace.
        user_uuid (str): The ID of the user to remove.

    Returns:
        None: If the role assignment is successfully deleted.

    Examples:
    ```python
        delete_workspace_role_assignment(
            '123e4567-e89b-12d3-a456-426614174000', 
            'FefEFewf-feF-1234-5678-9abcdef01234',
        )
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
        None

    Examples:
        ```python
        assign_to_capacity(
            '123e4567-e89b-12d3-a456-426614174000', 
            'b7e2c1a4-8f3e-4c2a-9d2e-7b1e5f6a8c9d'
        )
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
        workspace_id (str): The ID of the workspace to unassign.

    Returns:
        None

    Examples:
        ```python
        unassign_from_capacity('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    response = _post_generic('unassign_from_capacity', workspace_id=workspace_id)
    if not response:
        logger.success(f'Workspace {workspace_id} unassigned from capacity successfully.')
    return response
