from typing import Any, Dict, List, Literal, Optional, Union

from pandas import DataFrame

from pyfabricops import api

from ..api.api import api_request
from ..utils.decorators import df
from ..utils.logging import get_logger
from ..utils.utils import is_valid_uuid

logger = get_logger(__name__)


@df
def list_connections(
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Returns the list of connections.

    Args:
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A list of connections.

    Examples:
        ```python
        list_connections()
        ```
    """
    return api('/connections', support_pagination=True)


def get_connection_id(connection: str) -> str | None:
    """
    Retrieves the ID of a connection by its name.

    Args:
        connection (str): The name of the connection.

    Returns:
        str | None: The ID of the connection if found, otherwise None.
    """
    connections = list_connections(df=False)

    for _connection in connections:
        if _connection['displayName'] == connection:
            return _connection['id']

    logger.warning(f"Connection '{connection}' not found.")
    return None


def resolve_connection(connection: str) -> str | None:
    """
    Resolves a connection name to its ID.

    Args:
        connection (str): The name of the connection.

    Returns:
        str | None: The ID of the connection if found, otherwise None.
    """
    if is_valid_uuid(connection):
        return connection
    else:
        return get_connection_id(connection)


@df
def get_connection(
    connection: str, df: Optional[bool] = True
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Returns the specified connection.

    Args:
        connection (str): The name or ID of the connection to retrieve.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
                If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]) The details of the connection if found, otherwise None. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        get_connection('123e4567-e89b-12d3-a456-426614174000')
        get_connection('MyProjectConnection')
        get_connection('MyProjectConnection', df=False) # Returns as list
        ```
    """
    return api_request('/connections/' + resolve_connection(connection))


def delete_connection(connection: str) -> None:
    """
    Deletes a connection.

    Args:
        connection (str): The name or ID of the connection to delete.

    Returns:
        None

    Examples:
        ```python
        delete_connection("123e4567-e89b-12d3-a456-426614174000")
        ```
    """
    return api_request(
        '/connections/' + resolve_connection(connection),
        method='delete'
    )


@df
def list_connection_role_assignments(
    connection: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Lists all role assignments for a connection.

    Args:
        connection (str): The name or ID of the connection.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): The list of role assignments for the connection.

    Examples:
        ```python
        list_connection_role_assignments("123e4567-e89b-12d3-a456-426614174000")
        ```
    """
    return api_request(
        '/connections/' + resolve_connection(connection) + '/roleAssignments',
        support_pagination=True,
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
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Adds a role to a connection.

    Args:
        connection (str): The name or id of the connection to add the role to.
        user_uuid (str): The UUID of the user or group to assign the role to.
        user_type (str): The type of the principal. Options: User, Group, ServicePrincipal, ServicePrincipalProfile.
        role (str): The role to add to the connection. Options: Owner, User, UserWithReshare.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.  If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The role assignment details.

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
    payload = {
        'principal': {'id': user_uuid, 'type': user_type},
        'role': role,
    }

    return api_request(
        '/connections/' + resolve_connection(connection) + '/roleAssignments',
        method='post',
        payload=payload,
    )


@df
def get_connection_role_assignment(
    connection: str, user_uuid: str, *, df: Optional[bool] = True
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Retrieves a role assignment for a connection.

    Args:
        connection (str): The name or ID of the connection to retrieve the role assignment from.
        user_uuid (str): The UUID of the user or group to retrieve the role assignment for.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The role assignment details.

    Examples:
        ```python
        get_connection_role_assignment(
            "123e4567-e89b-12d3-a456-426614174000",
            "98765432-9817-1234-5678-987654321234",
        )
        ```
    """
    return api_request(
        '/connections/' + resolve_connection(connection) + '/roleAssignments/' + user_uuid,
    )


@df
def update_connection_role_assignment(
    connection: str,
    user_uuid: str,
    user_type: Literal[
        'User', 'Group', 'ServicePrincipal', 'ServicePrincipalProfile'
    ] = 'User',
    role: Literal['Owner', 'User', 'UserWithReshare'] = 'User',
    *,
    df: Optional[bool] = False,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Updates a role assignment for a connection.

    Args:
        connection (str): The name or ID of the connection to update the role assignment for.
        user_uuid (str): The UUID of the user or group to update the role assignment for.
        user_type (str): The type of the principal. Options: User, Group, ServicePrincipal, ServicePrincipalProfile.
        role (str): The role to assign to the user or group. Options: Owner, User, UserWithReshare.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The updated role assignment details.

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
    payload={
            'principal': {'id': user_uuid, 'type': user_type},
            'role': role,
        },
    return api_request(
        '/connections/' + resolve_connection(connection) + '/roleAssignments/' + user_uuid,
        method='patch',
        payload=payload,
    )


def delete_connection_role_assignment(
    connection: str,
    user_uuid: str,
) -> None:
    """
    Deletes a role assignment for a connection.

    Args:
        connection (str): The name or ID of the connection to delete the role assignment from.
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
    return api_request(
        '/connections/' + resolve_connection(connection) + '/roleAssignments/' + user_uuid,
        method='delete',
    ) 
