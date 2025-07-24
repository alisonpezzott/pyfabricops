from typing import Literal

import pandas

from ._decorators import df
from ._generic_endpoints import (
    _list_generic, 
    _get_generic, 
    _delete_generic,
    _patch_generic,
    _post_generic
)
from ._logging import get_logger


logger = get_logger(__name__)


@df
def list_connections(
    df: bool = True,
) -> pandas.DataFrame | list[dict] | None:
    """
    Returns the list of connections.

    Args:
        df (bool, optional): If True, returns a pandas DataFrame. Defaults to True.

    Returns:
        (pandas.DataFrame | list[dict] | None): A list of connections or a DataFrame if df is True.
    
    Examples:
        ```python
        list_connections()
        ```
    """
    return _list_generic('connections')  


@df
def get_connection(
    connection_id: str, 
    *, 
    df=True
) -> pandas.DataFrame | dict | None:
    """
    Retrieves the details of a connection.

    Args:
        connection_id (str): The ID of the connection to retrieve.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to True.

    Returns:
        (pandas.DataFrame | dict | None): The details of the specified connection, or None if not found.

    Examples:
        ```python
        get_connection("123e4567-e89b-12d3-a456-426614174000")
        ```
    """
    return _get_generic(
        'connections',
        item_id=connection_id,
    )


def delete_connection(connection_id: str) -> None:
    """
    Deletes a connection.

    Args:
        connection_id (str): The ID of the connection to delete.

    Returns:
        None

    Examples:
        ```python
        delete_connection("123e4567-e89b-12d3-a456-426614174000")
        ```
    """
    return _delete_generic(
        'connections',
        item_id=connection_id
    )


@df
def list_connection_role_assignments(
    connection_id: str, *, df=True
) -> pandas.DataFrame | list[dict] | None:
    """
    Lists all role assignments for a connection.

    Args:
        connection_id (str): The ID of the connection.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (pandas.DataFrame | list[dict] | None): The list of role assignments for the connection.

    Examples:
        ```python
        list_connection_role_assignments("123e4567-e89b-12d3-a456-426614174000")
        ```
    """
    return _list_generic(
        'connections_role_assignments',
        workspace_id=connection_id,
    )


@df
def add_connection_role_assignment(
    connection: str,
    user_uuid: str,
    user_type: Literal[
        'User', 'Group', 'ServicePrincipal', 'ServicePrincipalProfile'
    ] = 'User',
    role: Literal['Owner', 'User', 'UserWithReshare'] = 'User',
    *,
    df: bool = True,
) -> pandas.DataFrame | dict | None:
    """
    Adds a role to a connection.

    Args:
        connection_id (str): The id of the connection to add the role to.
        user_uuid (str): The UUID of the user or group to assign the role to.
        user_type (str): The type of the principal. Options: User, Group, ServicePrincipal, ServicePrincipalProfile.
        role (str): The role to add to the connection. Options: Owner, User, UserWithReshare.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (pandas.DataFrame | dict | None): The role assignment details.

    Examples:
        ```python
        add_connection_role_assignment(
            '123e4567-e89b-12d3-a456-426614174000', 
            'abcd1234-5678-90ef-ghij-klmnopqrstuv', 
            'User', 
            'Owner'
        )
        ```
    """
    return _post_generic(
        'connections_role_assignments',
        workspace_id=connection,
        payload={
            'principal': {'id': user_uuid, 'type': user_type},
            'role': role
        }
    )


@df
def get_connection_role_assignment(
    connection_id: str, user_uuid: str, *, df=True
) -> pandas.DataFrame | dict | None:
    """
    Retrieves a role assignment for a connection.

    Args:
        connection_id (str): The ID of the connection to retrieve the role assignment from.
        user_uuid (str): The UUID of the user or group to retrieve the role assignment for.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (pandas.DataFrame | dict | None): The role assignment details.

    Examples:
        ```python
        get_connection_role_assignment(
            "123e4567-e89b-12d3-a456-426614174000", 
            "98765432-9817-1234-5678-987654321234",
        )
        ```
    """
    return _get_generic(
        'connections_role_assignments',
        workspace_id=connection_id,
        item_id=user_uuid,
    )


@df
def update_connection_role_assignment(
    connection_id: str,
    user_uuid: str,
    user_type: Literal[
        'User', 'Group', 'ServicePrincipal', 'ServicePrincipalProfile'
    ] = 'User',
    role: Literal['Owner', 'User', 'UserWithReshare'] = 'User',
    *,
    df: bool = False,
) -> pandas.DataFrame | dict | None:
    """
    Updates a role assignment for a connection.

    Args:
        connection_id (str): The ID of the connection to update the role assignment for.
        user_uuid (str): The UUID of the user or group to update the role assignment for.
        user_type (str): The type of the principal. Options: User, Group, ServicePrincipal, ServicePrincipalProfile.
        role (str): The role to assign to the user or group. Options: Owner, User, UserWithReshare.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (pandas.DataFrame | dict | None): The updated role assignment details.

    Examples:
        ```python
        update_connection_role_assignment(
            "123e4567-e89b-12d3-a456-426614174000", 
            "98765432-9817-1234-5678-987654321234", 
            "User", 
            "Owner"
        )
        ```
    """
    return _patch_generic(
        'connections_role_assignments',
        workspace_id=connection_id,
        item_id=user_uuid,
        payload={
            'principal': {'id': user_uuid, 'type': user_type},
            'role': role
        }
    )


def delete_connection_role_assignment(
    connection_id: str,
    user_uuid: str,
) -> None:
    """
    Deletes a role assignment for a connection.

    Args:
        connection_id (str): The ID of the connection to delete the role assignment from.
        user_uuid (str): The UUID of the user or group to delete the role assignment for.

    Returns:
        dict: The response from the API if successful, otherwise None.

    Examples:
        ```python
        delete_connection_role_assignment(
            "123e4567-e89b-12d3-a456-426614174000", 
            "98765432-9817-1234-5678-987654321234",
        ) 
        ```
    """
    return _delete_generic(
        'connections_role_assignments',
        workspace_id=connection_id,
        item_id=user_uuid,
    )  
