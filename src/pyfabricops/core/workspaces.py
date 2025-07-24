from typing import Dict, List, Literal, Optional, Union

from pandas import DataFrame

from ..api.api import (
    _delete_request,
    _get_request,
    _list_request,
    _patch_request,
    _post_request,
)
from ..core.capacities import resolve_capacity
from ..utils.decorators import df
from ..utils.exceptions import OptionNotAvailableError
from ..utils.logging import get_logger
from ..utils.utils import is_valid_uuid

logger = get_logger(__name__)


@df
def list_workspaces(
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, str]], None]:
    """
    Returns a list of workspaces.

    Args:
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (DataFrame | list | None): A list of workspaces or a DataFrame if df is True.

    Examples:
        ```python
        list_workspaces() # Returns as DataFrame
        list_workspaces(df=False) # Returns as list
        ```
    """
    return _list_request('workspaces')


@df
def _get_workspace(
    workspace_id: str, df: Optional[bool] = True
) -> Union[DataFrame, List[Dict[str, str]], None]:
    """
    Returns the specified workspace.

    Args:
        workspace_id (str): The ID of the workspace to retrieve.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
                If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, str]], None]) The details of the workspace if found, otherwise None. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        get_workspace('123e4567-e89b-12d3-a456-426614174000')
        get_workspace('MyProjectWorkspace')
        get_workspace('MyProjectWorkspace', df=False) # Returns as list
        ```
    """
    return _get_request('workspaces', item_id=workspace_id)


@df
def create_workspace(
    display_name: str,
    *,
    capacity: Optional[str] = None,
    description: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, str], None]:
    """
    Create a new workspace with the specified name, capacity and description.

    Args:
        display_name (str): The name of the workspace to create.
        capacity (str, optional): The ID or name of the capacity to assign to the workspace. Defaults to None.
        description (str, optional): A description for the workspace. Defaults to None.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, str], None]): The details of the created or updated workspace if successful, otherwise None.

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

    if capacity:
        payload['capacityId'] = resolve_capacity(capacity)

    if description:
        payload['description'] = description

    return _post_request('workspaces', payload=payload)


@df
def update_workspace(
    workspace: str,
    *,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, str], None]:
    """
    Updates the properties of a workspace.

    Args:
        workspace (str): The workspace name or ID to update.
        display_name (str, optional): The new name for the workspace.
        description (str, optional): The new description for the workspace.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (DataFrame | dict | None): The updated workspace details. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        update_workspace(
            '123e4567-e89b-12d3-a456-426614174000',
            display_name='New Workspace Name',
        )

        update_workspace(
            'MyProjectWorkspace',
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

    return _patch_request(
        'workspaces', item_id=resolve_workspace(workspace), payload=payload
    )


def delete_workspace(workspace: str) -> None:
    """
    Delete a workspace.

    Args:
        workspace (str): The name or ID of the workspace to delete.

    Returns:
        None

    Raises:
        ResourceNotFoundError: If the specified workspace is not found.

    Examples:
        ```python
        delete_workspace('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    return _delete_request('workspaces', item_id=resolve_workspace(workspace))


@df
def list_workspace_role_assignments(
    workspace: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, str]], None]:
    """
    Lists all role assignments for a workspace.

    Args:
        workspace (str): The name or ID of the workspace to list role assignments for.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, str]], None]): A list of role assignments.


    Examples:
        ```python
        list_workspace_role_assignments('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    return _list_request(
        'workspaces',
        workspace_id=resolve_workspace(workspace),
        endpoint_suffix='roleAssignments',
    )


@df
def get_workspace_role_assignment(
    workspace: str,
    user_uuid: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, str], None]:
    """
    Retrieves the role of a user in a workspace.

    Args:
        workspace (str): The name or id of the workspace to get role assignment for.
        user_uuid (str): The UUID of the user to check.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, str], None]): The role assignment if found, otherwise None.

    Examples:
        ```python
        get_workspace_role_assignment(
            '123e4567-e89b-12d3-a456-426614174000',
            'FefEFewf-feF-1234-5678-9abcdef01234'
        )
        ```
    """
    return _get_request(
        'workspaces',
        workspace_id=resolve_workspace(workspace),
        item_id=user_uuid,
        endpoint_suffix='roleAssignments',
    )


@df
def add_workspace_role_assignment(
    workspace: str,
    user_uuid: str,
    user_type: Literal[
        'User', 'Group', 'ServicePrincipal', 'ServicePrincipalProfile'
    ] = 'User',
    role: Literal['Admin', 'Contributor', 'Member', 'Viewer'] = 'Admin',
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, str], None]:
    """
    Adds a permission to a workspace for a user.

    Args:
        workspace (str): The ID or name of the workspace.
        user_uuid (str): The UUID of the user.
        user_type (str): The type of user (options: User, Group, ServicePrincipal, ServicePrincipalProfile).
        role (str): The role to assign (options: admin, member, contributor, viewer).
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, str], None]): The role assignment details if successful.

    Raises:
        ResourceNotFoundError: If the specified workspace is not found.
        OptionNotAvailableError: If the user type or role is invalid.

    Examples:
        ```python
        add_workspace_role_assignment(
            '123e4567-e89b-12d3-a456-426614174000',
            'FefEFewf-feF-1234-5678-9abcdef01234', user_type='User', role='Admin'
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

    return _post_request(
        'workspaces',
        workspace_id=resolve_workspace(workspace),
        payload=payload,
        endpoint_suffix='roleAssignments',
    )


@df
def update_workspace_role_assignment(
    workspace: str,
    user_uuid: str,
    role: Literal['Admin', 'Contributor', 'Member', 'Viewer'] = 'Admin',
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, str], None]:
    """
    Update a role to a existing workspace role assignment.

    Args:
        workspace (str): The ID or name of the workspace.
        user_uuid (str): The UUID of the user.
        role (str): The new role to assign (options: admin, member, contributor, viewer).
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, str], None]): The updated role assignment details if successful, otherwise None.

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

    workspace_id = resolve_workspace(workspace)

    return _patch_request(
        'workspaces',
        workspace_id=workspace_id,
        item_id=user_uuid,
        payload=payload,
        endpoint_suffix='roleAssignments',
    )


def delete_workspace_role_assignment(
    workspace: str,
    user_uuid: str,
) -> None:
    """
    Removes a permission from a workspace for a user.

    Args:
        workspace (str): The ID or name of the workspace.
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
    return _delete_request(
        'workspaces',
        workspace_id=resolve_workspace(workspace),
        item_id=user_uuid,
        endpoint_suffix='roleAssignments',
    )


def assign_to_capacity(workspace: str, capacity: str) -> None:
    """
    Assigns a workspace to a capacity.

    Args:
        workspace (str): The ID or name of the workspace to assign.
        capacity (str): The ID or name of the capacity to assign the workspace to.

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
    payload = {'capacityId': resolve_capacity(capacity)}
    response = _post_request(
        'workspaces',
        workspace_id=resolve_workspace(workspace),
        payload=payload,
        endpoint_suffix='assignToCapacity',
    )
    if not response:
        logger.success(
            f'Workspace {workspace} assigned to capacity {capacity} successfully.'
        )
    return response


def unassign_from_capacity(workspace: str) -> None:
    """
    Unassigns a workspace from its current capacity.

    Args:
        workspace (str): The ID or name of the workspace to unassign.

    Returns:
        None

    Examples:
        ```python
        unassign_from_capacity('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    response = _post_request(
        'workspaces',
        workspace_id=resolve_workspace(workspace),
        endpoint_suffix='unassignFromCapacity',
    )
    if not response:
        logger.success(
            f'Workspace {workspace} unassigned from capacity successfully.'
        )
    return response


def get_workspace_id(workspace: str) -> Union[str, None]:
    """
    Retrieves the ID of a workspace by its name.

    Args:
        workspace (str): The name of the workspace.

    Returns:
        str | None: The ID of the workspace if found, otherwise None.
    """
    workspaces = list_workspaces(df=False)
    for _workspace in workspaces:
        if _workspace['displayName'] == workspace:
            return _workspace['id']
        logger.warning(f"Workspace '{workspace}' not found.")
    return None


def resolve_workspace(workspace: str) -> Union[str, None]:
    """
    Resolves a workspace name to its ID.

    Args:
        workspace (str): The name of the workspace.

    Returns:
        str | None: The ID of the workspace if found, otherwise None.
    """
    if is_valid_uuid(workspace):
        return workspace
    else:
        return get_workspace_id(workspace)


@df
def get_workspace(
    workspace: str, df: Optional[bool] = True
) -> Union[DataFrame, List[Dict[str, str]], None]:
    """
    Returns the specified workspace.

    Args:
        workspace (str): The name or ID of the workspace to retrieve.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
                If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, str]], None]) The details of the workspace if found, otherwise None. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        get_workspace('123e4567-e89b-12d3-a456-426614174000')
        get_workspace('MyProjectWorkspace')
        get_workspace('MyProjectWorkspace', df=False) # Returns as list
        ```
    """
    workspace_id = resolve_workspace(workspace)
    return _get_request('workspaces', item_id=workspace_id)
