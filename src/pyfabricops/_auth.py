import json
import logging
import os
import tempfile
import time
from typing import Literal, Union

import requests
from azure.identity import ClientSecretCredential, InteractiveBrowserCredential
from azure.keyvault.secrets import SecretClient
from dotenv import load_dotenv

from ._exceptions import (
    AuthenticationError,
    OptionNotAvailableError,
    ResourceNotFoundError,
)
from ._scopes import FABRIC_SCOPE, POWERBI_SCOPE, TOKEN_TEMPLATE

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

CACHE_TEMPLATE = {
    'FABRIC_SPN': {'access_token': '', 'expires_at': 0},
    'FABRIC_USER': {'access_token': '', 'expires_at': 0},
    'FABRIC_INTERACTIVE': {'access_token': '', 'expires_at': 0},
    'POWERBI_SPN': {'access_token': '', 'expires_at': 0},
    'POWERBI_USER': {'access_token': '', 'expires_at': 0},
    'POWERBI_INTERACTIVE': {'access_token': '', 'expires_at': 0},
}

CACHE_FILE = os.path.join(tempfile.gettempdir(), 'py_fab_token_cache.json')


def _init_tokens_cache():
    if not os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'w') as f:
            json.dump(CACHE_TEMPLATE, f)


def _load_tokens():
    _init_tokens_cache()
    with open(CACHE_FILE, 'r') as f:
        return json.load(f)


def _save_tokens(tokens):
    with open(CACHE_FILE, 'w') as f:
        json.dump(tokens, f, indent=4)


tokens = _load_tokens()


def _set_auth_provider(source: Literal['env', 'vault', 'oauth'] = 'env'):
    if source not in ['env', 'vault', 'oauth']:
        raise OptionNotAvailableError(
            f'Source not available. Available: env, vault, oauth. Got: {source}'
        )
    auth_provider = source
    return auth_provider


def _set_audience(audience: Literal['fabric', 'powerbi'] = 'fabric'):
    audience = audience
    return audience


def _set_credential_type(credential_type: Literal['spn', 'user'] = 'spn'):
    credential_type = credential_type
    return credential_type


def _get_env() -> dict:
    load_dotenv()
    fab_client_id = os.getenv('FAB_CLIENT_ID')
    fab_client_secret = os.getenv('FAB_CLIENT_SECRET')
    fab_tenant_id = os.getenv('FAB_TENANT_ID')
    fab_username = os.getenv('FAB_USERNAME')
    fab_password = os.getenv('FAB_PASSWORD')
    azure_tenant_id = os.getenv('AZURE_TENANT_ID')
    azure_client_id = os.getenv('AZURE_CLIENT_ID')
    azure_client_secret = os.getenv('AZURE_CLIENT_SECRET')
    azure_key_vault_name = os.getenv('AZURE_KEY_VAULT_NAME')
    github_token = os.getenv('GITHUB_TOKEN')
    return {
        'fab_client_id': fab_client_id,
        'fab_client_secret': fab_client_secret,
        'fab_tenant_id': fab_tenant_id,
        'fab_username': fab_username,
        'fab_password': fab_password,
        'azure_tenant_id': azure_tenant_id,
        'azure_client_id': azure_client_id,
        'azure_client_secret': azure_client_secret,
        'azure_key_vault_name': azure_key_vault_name,
        'github_token': github_token,
    }


def _get_vault_secrets():
    creds = _get_env()
    vault_url = f"https://{creds['azure_key_vault_name']}.vault.azure.net"
    credential = ClientSecretCredential(
        tenant_id=creds['azure_tenant_id'],
        client_id=creds['azure_client_id'],
        client_secret=creds['azure_client_secret'],
    )
    client = SecretClient(vault_url=vault_url, credential=credential)
    secrets = {}
    for secret_name in [
        'fab-client-id',
        'fab-client-secret',
        'fab-tenant-id',
        'fab-username',
        'fab-password',
        'github-token',
        'database-username',
        'database-password',
    ]:
        secret = client.get_secret(secret_name)
        secrets[secret_name.replace('-', '_')] = secret.value
    return secrets


def _build_payload(
    audience: Literal['fabric', 'powerbi'] = 'fabric',
    auth_provider: Literal['env', 'vault', 'oauth'] = 'env',
    credential_type: Literal['spn', 'user'] = 'spn',
) -> dict:

    auth_provider = _set_auth_provider(auth_provider)
    credential_type = _set_credential_type(credential_type)
    audience = _set_audience(audience)

    if auth_provider == 'env':
        secrets = _get_env()
    elif auth_provider == 'vault':
        secrets = _get_vault_secrets()
    else:
        raise OptionNotAvailableError(
            'Invalid credentials source. Use `env` or `vault`.'
        )

    payload = {
        'client_id': secrets['fab_client_id'],
        'client_secret': secrets['fab_client_secret'],
        'tenant_id': secrets['fab_tenant_id'],
        'grant_type': 'client_credentials'
        if credential_type == 'spn'
        else 'password',
        'scope': FABRIC_SCOPE if audience == 'fabric' else POWERBI_SCOPE,
    }

    if credential_type == 'user':
        payload['username'] = secrets['fab_username']
        payload['password'] = secrets['fab_password']

    return payload


def _retrieve_token(
    audience: Literal['fabric', 'powerbi'] = 'fabric',
    auth_provider: Literal['env', 'vault', 'oauth'] = 'env',
    credential_type: Literal['spn', 'user'] = 'spn',
) -> Union[dict, None]:

    if auth_provider == 'env':
        secrets = _get_env()
    elif auth_provider == 'vault':
        secrets = _get_vault_secrets()
    else:
        raise OptionNotAvailableError(
            'Invalid credentials source. Use `env` or `vault`.'
        )

    tenant_id = secrets['fab_tenant_id']
    url = TOKEN_TEMPLATE.format(tenant_id=tenant_id)

    payload = _build_payload(audience, auth_provider, credential_type)

    try:
        resp = requests.post(url, data=payload)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        raise AuthenticationError(f'Failed to retrieve token: {str(e)}')


def _get_token_silently(
    audience: Literal['fabric', 'powerbi'] = 'fabric',
    auth_provider: Literal['env', 'vault'] = 'env',
    credential_type: Literal['spn', 'user'] = 'spn',
):

    token_key = f'{audience.upper()}_{credential_type.upper()}'

    now = time.time()
    expires_at = tokens[token_key].get('expires_at', 0)
    expires_in = expires_at - now

    if expires_in > 300 and tokens[token_key]['access_token']:
        return tokens[token_key]

    resp = _retrieve_token(audience, auth_provider, credential_type)

    if not resp:
        raise ResourceNotFoundError('Access token not found.')

    refreshed_at = time.time()
    tokens[token_key] = {
        'access_token': resp['access_token'],
        'expires_at': refreshed_at + resp['expires_in'],
    }
    _save_tokens(tokens)
    return tokens[token_key]


def _get_token_oauth(audience: Literal['fabric', 'powerbi'] = 'fabric'):
    scope = FABRIC_SCOPE if audience == 'fabric' else POWERBI_SCOPE
    token_key = f'{audience.upper()}_INTERACTIVE'

    now = time.time()
    expires_at = tokens[token_key].get('expires_at', 0)
    expires_in = expires_at - now

    if expires_in > 300 and tokens[token_key]['access_token']:
        return tokens[token_key]

    logger.info('Opening browser for user authentication...')
    credential = InteractiveBrowserCredential()
    new_token = credential.get_token(scope)
    if not new_token:
        raise ResourceNotFoundError('Access token not found.')
    logger.info('Token retrieved successfully.')

    tokens[token_key] = {
        'access_token': new_token.token,
        'expires_at': new_token.expires_on,
    }
    _save_tokens(tokens)
    return tokens[token_key]


class _TokenManager:
    def __init__(
        self,
        auth_provider: Literal['env', 'vault', 'oauth'] = 'env',
    ):
        self.auth_provider = auth_provider


_token_manager = _TokenManager()


def set_auth_provider(
    source: Literal['env', 'vault', 'oauth'] = 'env'
) -> None:
    """
    Set the authentication provider for token retrieval.

    Args:
        source (str): The provider of credentials. Can be "env", "vault", or "oauth".

    Returns:
        None

    Raises:
        OptionNotAvailableError: If the source is not one of the available options.

    Examples:
        ### Environment variables (.env, GitHub Secrets, Ado Secrets...)
        ```python
        set_auth_provider("env")
        ```

        This is the default behavior.
        You can set these in a .env file or directly in your environment (GitHub Secrets, ADO Secrets...).

        Example .env file:
        ```
        FAB_CLIENT_ID=your_client_id_here
        FAB_CLIENT_SECRET=your_client_secret_here
        FAB_TENANT_ID=your_tenant_id_here
        FAB_USERNAME=your_username_here   # Necessary for some functions with no SPN support
        FAB_PASSWORD=your_password_here   # Necessary for some functions with no SPN support
        ```


        ### Azure Key Vault

        ```python
        set_auth_provider("vault")
        ```
        Ensure you have the required Azure Key Vault secrets set:
        ```
        AZURE_CLIENT_ID=your_azure_client_id_here
        AZURE_CLIENT_SECRET=your_azure_client_secret_here
        AZURE_TENANT_ID=your_azure_tenant_id_here
        AZURE_KEY_VAULT_NAME=your_key_vault_name_here
        ```


        ### OAuth (Interactive)

        ```python
        set_auth_provider("oauth")
        ```
        This will open a browser window for user authentication.
    """
    global _token_manager
    _token_manager.auth_provider = _set_auth_provider(source)


def _get_token(
    audience: Literal['fabric', 'powerbi'] = 'fabric',
    auth_provider: Literal['env', 'vault', 'oauth'] = 'env',
    credential_type: Literal['spn', 'user'] = 'spn',
) -> Union[dict, None]:

    auth_provider = _token_manager.auth_provider

    if auth_provider == 'oauth':
        return _get_token_oauth(audience)
    else:
        return _get_token_silently(audience, auth_provider, credential_type)


def _get_github_token(
    provider: Literal['env', 'vault', 'oauth'] = 'env'
) -> str:
    if provider in ['env', 'oauth']:
        return _get_env().get('github_token', '')
    elif provider == 'vault':
        return _get_vault_secrets().get('github_token', '')
    else:
        raise OptionNotAvailableError(
            'Invalid provider. Use `env` or `vault`.'
        )


def _delete_tokens_cache():
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
        logger.info(f'File {CACHE_FILE} deleted successfully!')
    else:
        logger.warning(f'File {CACHE_FILE} not found.')


def _open_tokens_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            tokens = json.load(f)
            logger.info(f'Tokens loaded successfully: {tokens}')
            return tokens
    else:
        logger.warning(f'File {CACHE_FILE} not found.')
        return None
