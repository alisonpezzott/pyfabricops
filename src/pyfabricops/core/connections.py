import re
from typing import Any, Dict, List, Literal, Optional, Union

from pandas import DataFrame

from ..api.api import api_request
from ..core.gateways_encryp_creds import _get_encrypt_gateway_credentials
from ..core.workspaces import resolve_workspace
from ..items.semantic_models import resolve_semantic_model
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
    return api_request('/connections', support_pagination=True)


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
        '/connections/' + resolve_connection(connection), method='delete'
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
        '/connections/'
        + resolve_connection(connection)
        + '/roleAssignments/'
        + user_uuid,
    )


@df
def update_connection_role_assignment(
    connection: str,
    user_uuid: str,
    role: Literal['Owner', 'User', 'UserWithReshare'] = 'User',
    *,
    df: Optional[bool] = False,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Updates a role assignment for a connection.

    Args:
        connection (str): The name or ID of the connection to update the role assignment for.
        user_uuid (str): The UUID of the user or group to update the role assignment for.
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
    payload = {'role': role}
    return api_request(
        '/connections/'
        + resolve_connection(connection)
        + '/roleAssignments/'
        + user_uuid,
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
        '/connections/'
        + resolve_connection(connection)
        + '/roleAssignments/'
        + user_uuid,
        method='delete',
    )


@df
def create_github_source_control_connection(
    display_name: str,
    repository: str,
    github_token: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Creates a new GitHub source control connection.

    Args:
        display_name (str): The display name for the connection.
        repository (str): The URL of the GitHub repository.
        github_token (str): The GitHub token for authentication.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The created connection.

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

    return api_request(
        '/connections',
        method='post',
        payload=payload,
    )


@df
def create_sql_cloud_connection(
    display_name: str,
    server: str,
    database: str,
    username: str,
    password: str,
    privacy_level: Optional[str] = 'Organizational',
    connection_encryption: Optional[str] = 'NotEncrypted',
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Creates a new cloud connection using the Fabric API.

    Args:
        display_name (str): The display name for the connection.
        server (str): The server name for the SQL connection.
        database (str): The database name for the SQL connection.
        username (str): The username for the SQL connection.
        password (str): The password for the SQL connection.
        privacy_level (Optional[str]): The privacy level of the connection. Default is "Organizational".
        connection_encryption (Optional[str]): The encryption type for the connection. Default is "NotEncrypted".
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The response from the API if successful.

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
        ```
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
    return api_request(
        '/connections',
        method='post',
        payload=payload,
    )


@df
def create_sql_on_premises_connection(
    display_name: str,
    gateway_id: str,
    server: str,
    database: str,
    username: str,
    password: str,
    *,
    credential_type: Optional[str] = 'Basic',
    privacy_level: Optional[str] = 'Organizational',
    connection_encryption: Optional[str] = 'NotEncrypted',
    skip_test_connection: Optional[bool] = False,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Creates a new cloud connection using the Fabric API.

    Args:
        display_name (str): The display name for the connection. If None, defaults to connection_name.
        gateway_id (str): The ID or displayName of the gateway to use for the connection.
        server (str): The server name for the SQL connection.
        database (str): The database name for the SQL connection.
        username (str): The username for the SQL connection.
        password (str): The password for the SQL connection.
        credential_type (str): The type of credentials to use. Default is "Basic".
        privacy_level (str): The privacy level of the connection. Default is "Organizational".
        connection_encryption (str): The encryption type for the connection. Default is "NotEncrypted".
        skip_test_connection (bool): Whether to skip the test connection step. Default is False.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The response from the API.

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
        ```
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
    return api_request(
        '/connections',
        method='post',
        payload=payload,
    )


def bind_semantic_model_connection(
    workspace: str,
    semantic_model: str,
    connection_type: str,
    connection_path: str,
    connectivity_type: Literal[
        'ShareableCloud',
        'PersonalCloud',
        'OnPremisesGateway',
        'OnPremisesGatewayPersonal',
        'VirtualNetworkGateway',
        'Automatic',
        'None',
    ] = 'ShareableCloud',
    connection: str = None,
) -> None:
    """
    Binds the semantic model to a connection.

    Returns:
        None

    Examples:
        ```python
        bind_semantic_model_connection(
            workspace='Sandbox Fabric',
            semantic_model='Contoso Sales',
            connection_type='SQL',
            connection_path='pezzot-mvp.database.windows.net;contoso',
            connectivity_type='ShareableCloud',
            connection='pezzott-mvp_contoso',
        )

        # Unbind connection
        bind_semantic_model_connection(
            workspace='Sandbox Fabric',
            semantic_model='Contoso Sales',
            connection_type='SQL',
            connection_path='pezzot-mvp.database.windows.net;contoso',
            connectivity_type='None',
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)
    semantic_model_id = resolve_semantic_model(workspace_id, semantic_model)
    payload = {
        'connectionBinding': {
            'connectivityType': connectivity_type,
            'connectionDetails': {
                'type': connection_type,
                'path': connection_path,
            },
        }
    }
    if connection is not None:
        connection_id = resolve_connection(connection)
        payload['connectionBinding']['id'] = connection_id

    response = api_request(
        endpoint=f'/workspaces/{workspace_id}/semanticModels/{semantic_model_id}/bindConnection',
        method='post',
        payload=payload,
    )

    if response == None:
        if connectivity_type == 'None':
            logger.success(
                f"Semantic model '{semantic_model}' in workspace '{workspace}' successfully unbinded from current connection."
            )
        else:
            logger.success(
                f"Semantic model '{semantic_model}' in workspace '{workspace}' successfully binded to connection {connection}."
            )

    return response
