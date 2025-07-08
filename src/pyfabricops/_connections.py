import logging
from typing import Literal

import pandas

from ._core import ApiResult, api_core_request, pagination_handler
from ._decorators import df
from ._encrypt_gateway_credentials import _get_encrypt_gateway_credentials
from ._utils import is_valid_uuid

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


@df
def list_connections(*, df=False) -> list | pandas.DataFrame:
    """
    Lists all connections.

    Args:
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (list or pandas.DataFrame): The list of connections.

    Examples:
        ```python
        list_connections()
        list_connections(df=True)
        ```
    """
    response = api_core_request(endpoint='/connections')
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        response = pagination_handler(response)
        return response.data.get('value')


def resolve_connection(connection: str, *, silent: bool = False) -> str:
    """
    Resolves a connection name to its ID.

    Args:
        connection (str): The name of the connection.
        silent (bool, optional): If True, suppresses warnings. Defaults to False.

    Returns:
        str: The ID of the connection.

    Examples:
        ```python
        resolve_connection("My Connection")
        resolve_connection("123e4567-e89b-12d3-a456-426614174000")
        ```
    """
    if is_valid_uuid(connection):
        return connection

    connections = list_connections(df=False)
    if not connections:
        return None

    for conn in connections:
        if conn['displayName'] == connection:
            return conn['id']

    # If we get here, connection was not found
    if not silent:
        logger.warning(f"Connection '{connection}' not found.")
    return None


@df
def get_connection(connection: str, *, df=False) -> dict | pandas.DataFrame:
    """
    Retrieves the details of a connection by its ID or name.

    Args:
        connection (str): The ID or name of the connection to retrieve.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame): The details of the specified connection, or None if not found.

    Examples:
        ```python
        get_connection("My Connection")
        get_connection("123e4567-e89b-12d3-a456-426614174000")
        ```
    """
    connection_id = resolve_connection(connection)
    if connection_id is None:
        return None
    response = api_core_request(endpoint=f'/connections/{connection_id}')
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


def delete_connection(connection: str) -> bool:
    """
    Removes a connection by name or ID.

    Args:
        connection (str): The ID or name of the connection to delete.

    Returns:
        bool: True if the connection was deleted successfully, False otherwise.

    Examples:
        ```python
        delete_connection("My Connection")
        delete_connection("123e4567-e89b-12d3-a456-426614174000")
        ```
    """
    connection_id = resolve_connection(connection)
    if not connection_id:
        return None
    response = api_core_request(
        endpoint=f'/connections/{connection_id}',
        method='delete',
        return_raw=True,
    )
    if not response.status_code == 200:
        logger.warning(f'{response.status_code}: {response.text}.')
        return False
    else:
        return True


@df
def list_connection_role_assignments(
    connection: str, *, df=False
) -> dict | pandas.DataFrame:
    """
    Lists all role assignments for a connection.

    Args:
        connection (str): The ID or name of the connection.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame): The list of role assignments for the connection.

    Examples:
        ```python
        list_connection_role_assignments("My Connection")
        list_connection_role_assignments("123e4567-e89b-12d3-a456-426614174000")
        ```
    """
    connection_id = resolve_connection(connection)
    if connection_id is None:
        return None

    response = api_core_request(
        endpoint=f'/connections/{connection_id}/roleAssignments'
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        response = pagination_handler(response)
    return response.data.get('value')


@df
def add_connection_role_assignment(
    connection: str,
    user_uuid: str,
    user_type: Literal[
        'User', 'Group', 'ServicePrincipal', 'ServicePrincipalProfile'
    ] = 'User',
    role: Literal['Owner', 'User', 'UserWithReshare'] = 'User',
    *,
    df: bool = False,
) -> dict | pandas.DataFrame:
    """
    Adds a role to a connection.

    Args:
        connection_id (str): The id of the connection to add the role to.
        user_uuid (str): The UUID of the user or group to assign the role to.
        user_type (str): The type of the principal. Options: User, Group, ServicePrincipal, ServicePrincipalProfile.
        role (str): The role to add to the connection. Options: Owner, User, UserWithReshare.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame): The role assignment details.

    Examples:
        ```python
        add_connection_role_assignment("My Connection", "user-uuid", "User", "Owner")
        add_connection_role_assignment("123e4567-e89b-12d3-a456-426614174000", "user-uuid", "User", "Owner")
        ```
    """
    connection_id = resolve_connection(connection)
    if not connection_id:
        return None
    payload = {'principal': {'id': user_uuid, 'type': user_type}, 'role': role}
    response = api_core_request(
        endpoint=f'/connections/{connection_id}/roleAssignments',
        method='post',
        payload=payload,
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


@df
def get_connection_role_assignment(
    connection: str, user_uuid: str, *, df=False
) -> dict | pandas.DataFrame:
    """
    Retrieves a role assignment for a connection.

    Args:
        connection_id (str): The ID of the connection to retrieve the role assignment from.
        user_uuid (str): The UUID of the user or group to retrieve the role assignment for.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame): The role assignment details.

    Examples:
        ```python
        get_connection_role_assignment("My Connection", "98765432-9817-1234-5678-987654321234")
        get_connection_role_assignment("123e4567-e89b-12d3-a456-426614174000", "98765432-9817-1234-5678-987654321234")
        ```
    """
    connection_id = resolve_connection(connection)
    if not connection_id:
        return None

    response = api_core_request(
        endpoint=f'/connections/{connection_id}/roleAssignments/{user_uuid}'
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


@df
def update_connection_role_assignment(
    connection: str,
    user_uuid: str,
    user_type: Literal[
        'User', 'Group', 'ServicePrincipal', 'ServicePrincipalProfile'
    ] = 'User',
    role: Literal['Owner', 'User', 'UserWithReshare'] = 'User',
    *,
    df: bool = False,
) -> dict | pandas.DataFrame:
    """
    Updates a role assignment for a connection.

    Args:
        connection_id (str): The ID of the connection to update the role assignment for.
        user_uuid (str): The UUID of the user or group to update the role assignment for.
        user_type (str): The type of the principal. Options: User, Group, ServicePrincipal, ServicePrincipalProfile.
        role (str): The role to assign to the user or group. Options: Owner, User, UserWithReshare.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame): The updated role assignment details.

    Examples:
        ```python
        update_connection_role_assignment(
            "My Connection", "98765432-9817-1234-5678-987654321234", "User", "Owner"
        )

        update_connection_role_assignment(
            "123e4567-e89b-12d3-a456-426614174000", "98765432-9817-1234-5678-987654321234", "User", "Owner"
        )
        ```
    """
    connection_id = resolve_connection(connection)
    if not connection_id:
        return None

    payload = {'principal': {'id': user_uuid, 'type': user_type}, 'role': role}
    response = api_core_request(
        endpoint=f'/connections/{connection_id}/roleAssignments/{user_uuid}',
        method='patch',
        payload=payload,
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


def delete_connection_role_assignment(
    connection: str,
    user_uuid: str,
):
    """
    Deletes a role assignment for a connection.

    Args:
        connection_id (str): The ID of the connection to delete the role assignment from.
        user_uuid (str): The UUID of the user or group to delete the role assignment for.

    Returns:
        dict: The response from the API if successful, otherwise None.

    Examples:
        ```python
        delete_connection_role_assignment("My Connection", "98765432-9817-1234-5678-987654321234")
        delete_connection_role_assignment("123e4567-e89b-12d3-a456-426614174000", "98765432-9817-1234-5678-987654321234")
        ```
    """
    connection_id = resolve_connection(connection)
    if not connection_id:
        return None

    response = api_core_request(
        endpoint=f'/connections/{connection_id}/roleAssignments/{user_uuid}',
        method='delete',
        return_raw=True,
    )
    if not response.status_code == 200:
        logger.warning(f'{response.status_code}: {response.text}.')
        return False
    else:
        return True


@df
def create_github_source_control_connection(
    display_name: str, repository: str, github_token: str, *, df: bool = False
):
    """
    Creates a new GitHub source control connection.

    Args:
        display_name (str): The display name for the connection.
        repository (str): The URL of the GitHub repository.
        github_token (str): The GitHub token for authentication.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame): The created connection.

    Examples:
        ```python
            from dotenv import load_dotenv
            load_dotenv()
            pf.create_github_source_control_connection(
                display_name='pyfabricops-examples',
                repository='https://github.com/alisonpezzott/pyfabricops-examples',
                github_token=os.getenv('GH_TOKEN'),
                df=True,
            )
        ```
    """
    payload = {
        'connectivityType': 'ShareableCloud',
        'displayName': display_name,
        'connectionDetails': {
            'type': 'GitHubSourceControl',
            'creationMethod': 'GitHubSourceControl.Contents',
            'parameters': [
                {'dataType': 'Text', 'name': 'url', 'value': repository}
            ],
        },
        'privacyLevel': 'Organizational',
        'credentialDetails': {
            'singleSignOnType': 'None',
            'connectionEncryption': 'NotEncrypted',
            'credentials': {'credentialType': 'Key', 'key': github_token},
        },
    }

    response = api_core_request(
        endpoint='/connections',
        method='post',
        payload=payload,
        return_raw=True,
    )

    if not response.status_code == 201:
        logger.warning(f'{response.status_code}: {response.text}.')
        return False
    else:
        return response.json()


@df
def create_sql_cloud_connection(
    display_name: str,
    server: str,
    database: str,
    username: str,
    password: str,
    privacy_level: str = 'Organizational',
    connection_encryption: str = 'NotEncrypted',
    *,
    df: bool = False,
) -> ApiResult:
    """
    Creates a new cloud connection using the Fabric API.

    Args:
        display_name (str): The display name for the connection.
        server (str): The server name for the SQL connection.
        database (str): The database name for the SQL connection.
        username (str): The username for the SQL connection.
        password (str): The password for the SQL connection.
        privacy_level (str): The privacy level of the connection. Default is "Organizational".
        connection_encryption (str): The encryption type for the connection. Default is "NotEncrypted".
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame): The response from the API if successful.

    Examples:
        ```python
        from dotenv import load_dotenv
        load_dotenv()

        create_sql_cloud_connection(
            display_name='My SQL Connection',
            server='myserver.database.windows.net',
            database='mydatabase',
            username=os.getenv('SQL_USERNAME'),
            password=os.getenv('SQL_PASSWORD'),
            privacy_level='Organizational',
            connection_encryption='NotEncrypted',
            df=True,
        )
    """
    payload = {
        'connectivityType': 'ShareableCloud',
        'displayName': display_name,
        'connectionDetails': {
            'type': 'SQL',
            'creationMethod': 'SQL',
            'parameters': [
                {'dataType': 'Text', 'name': 'server', 'value': server},
                {'dataType': 'Text', 'name': 'database', 'value': database},
            ],
        },
        'privacyLevel': privacy_level,
        'credentialDetails': {
            'singleSignOnType': 'None',
            'connectionEncryption': connection_encryption,
            'credentials': {
                'credentialType': 'Basic',
                'username': username,
                'password': password,
            },
        },
    }
    response = api_core_request(
        endpoint=f'/connections',
        method='post',
        payload=payload,
        return_raw=True,
    )

    if not response.status_code == 201:
        logger.warning(f'{response.status_code}: {response.text}.')
        return False
    else:
        return response.json()


@df
def create_sql_on_premises_connection(
    display_name: str,
    gateway_id: str,
    server: str,
    database: str,
    username: str,
    password: str,
    credential_type: str = 'Basic',
    privacy_level: str = 'Organizational',
    connection_encryption: str = 'NotEncrypted',
    skip_test_connection: bool = False,
    *,
    df: bool = False,
):
    """
    Creates a new cloud connection using the Fabric API.

    Args:
        display_name (str): The display name for the connection. If None, defaults to connection_name.
        gateway (str): The ID or displayName of the gateway to use for the connection.
        server (str): The server name for the SQL connection.
        database (str): The database name for the SQL connection.
        username (str): The username for the SQL connection.
        password (str): The password for the SQL connection.
        credential_type (str): The type of credentials to use. Default is "Basic".
        privacy_level (str): The privacy level of the connection. Default is "Organizational".
        connection_encryption (str): The encryption type for the connection. Default is "NotEncrypted".
        skip_test_connection (bool): Whether to skip the test connection step. Default is False.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame): The response from the API.

    Examples:
        ```python
        from dotenv import load_dotenv
        load_dotenv()

        create_sql_on_premises_connection(
            display_name='My SQL On-Premises Connection',
            gateway_id='123e4567-e89b-12d3-a456-426614174000',
            server='myserver.database.windows.net',
            database='mydatabase',
            username=os.getenv('SQL_USERNAME'),
            password=os.getenv('SQL_PASSWORD'),
            credential_type='Basic',
            privacy_level='Organizational',
            connection_encryption='NotEncrypted',
            skip_test_connection=False,
            df=True,
        )
    """
    encrypted_credentials = _get_encrypt_gateway_credentials(
        gateway_id=gateway_id, username=username, password=password
    )
    payload = {
        'connectivityType': 'OnPremisesGateway',
        'gatewayId': gateway_id,
        'displayName': display_name,
        'connectionDetails': {
            'type': 'SQL',
            'creationMethod': 'SQL',
            'parameters': [
                {'dataType': 'Text', 'name': 'server', 'value': server},
                {'dataType': 'Text', 'name': 'database', 'value': database},
            ],
        },
        'privacyLevel': privacy_level,
        'credentialDetails': {
            'singleSignOnType': 'None',
            'connectionEncryption': connection_encryption,
            'skipTestConnection': skip_test_connection,
            'credentials': {
                'credentialType': credential_type,
                'values': [
                    {
                        'gatewayId': gateway_id,
                        'encryptedCredentials': encrypted_credentials,
                    }
                ],
            },
        },
    }
    response = api_core_request(
        endpoint=f'/connections',
        method='post',
        payload=payload,
        return_raw=True,
    )

    if not response.status_code == 201:
        logger.warning(f'{response.status_code}: {response.text}.')
        return False
    else:
        return response.json()
