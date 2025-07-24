import pandas

from ..api.api import _post_request
from ..utils.decorators import df
from ..utils.logging import get_logger
from .encrypt_gateway_credentials import _get_encrypt_gateway_credentials

logger = get_logger(__name__)


@df
def create_github_source_control_connection(
    display_name: str,
    repository: str,
    github_token: str,
    *,
    df: bool = True,
) -> pandas.DataFrame | dict | None:
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

    return _post_request(
        'connections',
        payload=payload,
    )


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
) -> pandas.DataFrame | dict | None:
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
        (pandas.DataFrame | dict | None): The response from the API if successful.

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
    return _post_request(
        'connections',
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
    return _post_request(
        'connections',
        payload=payload,
    )
