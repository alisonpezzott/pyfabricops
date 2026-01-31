import json
import os
import tempfile
import time
from abc import ABC, abstractmethod
from typing import Dict, Literal, Optional, Union

import requests
from azure.identity import InteractiveBrowserCredential
from dotenv import load_dotenv

from ..utils.exceptions import (
    AuthenticationError,
    OptionNotAvailableError,
    ResourceNotFoundError,
)
from ..utils.logging import get_logger
from .scopes import FABRIC_SCOPE, POWERBI_SCOPE, TOKEN_TEMPLATE

logger = get_logger(__name__)

# Define what should be publicly exported from this module
__all__ = ['set_auth_provider', 'clear_token_cache']


class TokenCache:
    """Manage the token cache in a temporary file"""

    CACHE_TEMPLATE = {
        'FABRIC_SPN': {'access_token': '', 'expires_at': 0},
        'FABRIC_USER': {'access_token': '', 'expires_at': 0},
        'FABRIC_INTERACTIVE': {'access_token': '', 'expires_at': 0},
        'POWERBI_SPN': {'access_token': '', 'expires_at': 0},
        'POWERBI_USER': {'access_token': '', 'expires_at': 0},
        'POWERBI_INTERACTIVE': {'access_token': '', 'expires_at': 0},
    }

    def __init__(self, cache_file: Optional[str] = None):
        self.cache_file = cache_file or os.path.join(
            tempfile.gettempdir(), 'pf_token_cache.json'
        )
        self._init_cache()

    def _init_cache(self):
        """Initialize the cache file if it does not exist"""
        if not os.path.exists(self.cache_file):
            with open(self.cache_file, 'w') as f:
                json.dump(self.CACHE_TEMPLATE, f)

    def load_tokens(self) -> Dict:
        """Load tokens from cache"""
        try:
            with open(self.cache_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._init_cache()
            return self.CACHE_TEMPLATE.copy()

    def save_tokens(self, tokens: Dict):
        """Save tokens to cache"""
        with open(self.cache_file, 'w') as f:
            json.dump(tokens, f, indent=4)

    def get_token(self, token_key: str) -> Optional[Dict]:
        """Get a specific token from cache"""
        tokens = self.load_tokens()
        return tokens.get(token_key)

    def is_token_valid(
        self, token_key: str, buffer_seconds: int = 300
    ) -> bool:
        """Check if a token is still valid"""
        token_data = self.get_token(token_key)
        if not token_data or not token_data.get('access_token'):
            return False

        now = time.time()
        expires_at = token_data.get('expires_at', 0)
        return (expires_at - now) > buffer_seconds

    def store_token(self, token_key: str, access_token: str, expires_in: int):
        """Store a new token in cache"""
        tokens = self.load_tokens()
        tokens[token_key] = {
            'access_token': access_token,
            'expires_at': time.time() + expires_in,
        }
        self.save_tokens(tokens)

    def clear_cache(self):
        """Clear the token cache by deleting the cache file"""
        if os.path.exists(self.cache_file):
            os.remove(self.cache_file)
            logger.info(f'Token cache cleared: {self.cache_file}')
        else:
            logger.warning(f'Cache file not found: {self.cache_file}')


class CredentialProvider(ABC):
    """Abstract class for different credential providers"""

    @abstractmethod
    def get_credentials(self) -> Dict[str, str]:
        """Return the necessary credentials"""
        pass


class EnvCredentialProvider(CredentialProvider):
    """Environment variable credential provider"""

    def get_credentials(self) -> Dict[str, str]:
        load_dotenv()
        return {
            'fab_client_id': os.getenv('FAB_CLIENT_ID'),
            'fab_client_secret': os.getenv('FAB_CLIENT_SECRET'),
            'fab_tenant_id': os.getenv('FAB_TENANT_ID'),
            'fab_username': os.getenv('FAB_USERNAME'),
            'fab_password': os.getenv('FAB_PASSWORD'),
            'github_token': os.getenv('GH_TOKEN'),
        }


class OAuthProvider:
    """OAuth interactive authentication provider"""

    def __init__(self, cache: TokenCache):
        self.cache = cache

    def get_token(
        self, audience: Literal['fabric', 'powerbi'] = 'fabric'
    ) -> Dict:
        scope = FABRIC_SCOPE if audience == 'fabric' else POWERBI_SCOPE
        token_key = f'{audience.upper()}_INTERACTIVE'

        # Check if cached token is still valid
        if self.cache.is_token_valid(token_key):
            return self.cache.get_token(token_key)

        logger.info('Opening browser for user authentication...')
        credential = InteractiveBrowserCredential()
        new_token = credential.get_token(scope)

        if not new_token:
            raise ResourceNotFoundError('Access token not found.')

        logger.success('Token retrieved successfully.')

        # Calculate expires_in based on expires_on
        expires_in = int(new_token.expires_on - time.time())
        self.cache.store_token(token_key, new_token.token, expires_in)

        return self.cache.get_token(token_key)


class TokenManager:
    """Main token and authentication manager"""

    def __init__(self, auth_provider: Literal['env', 'oauth'] = 'env'):
        self.cache = TokenCache()
        self.auth_provider = auth_provider
        self._credential_providers = {
            'env': EnvCredentialProvider(),
        }
        self.oauth_provider = OAuthProvider(self.cache)

    def set_auth_provider(self, source: Literal['env', 'oauth'] = 'env'):
        """Define the authentication provider"""
        if source not in ['env', 'oauth']:
            raise OptionNotAvailableError(
                f'Source not available. Available: env, oauth. Got: {source}'
            )
        self.auth_provider = source

    def _build_token_payload(
        self,
        audience: Literal['fabric', 'powerbi'],
        credential_type: Literal['spn', 'user'],
        credentials: Dict[str, str],
    ) -> Dict:
        """Construct the payload for token request"""
        payload = {
            'client_id': credentials['fab_client_id'],
            'client_secret': credentials['fab_client_secret'],
            'tenant_id': credentials['fab_tenant_id'],
            'grant_type': 'client_credentials'
            if credential_type == 'spn'
            else 'password',
            'scope': FABRIC_SCOPE if audience == 'fabric' else POWERBI_SCOPE,
        }

        if credential_type == 'user':
            payload['username'] = credentials['fab_username']
            payload['password'] = credentials['fab_password']

        return payload

    def _retrieve_token_from_api(
        self,
        audience: Literal['fabric', 'powerbi'],
        credential_type: Literal['spn', 'user'],
    ) -> Dict:
        """Makes an HTTP request to retrieve the token"""
        if self.auth_provider not in self._credential_providers:
            raise OptionNotAvailableError(
                f'Invalid auth provider: {self.auth_provider}'
            )

        credentials = self._credential_providers[
            self.auth_provider
        ].get_credentials()
        tenant_id = credentials['fab_tenant_id']
        url = TOKEN_TEMPLATE.format(tenant_id=tenant_id)

        payload = self._build_token_payload(
            audience, credential_type, credentials
        )

        try:
            resp = requests.post(url, data=payload)
            if resp.status_code == 200:
                return resp.json()
            else:
                raise AuthenticationError(
                    f'Token request failed: {resp.status_code} - {resp.text}'
                )
        except Exception as e:
            raise AuthenticationError(f'Failed to retrieve token: {str(e)}')

    def get_token(
        self,
        audience: Literal['fabric', 'powerbi'] = 'fabric',
        credential_type: Literal['spn', 'user'] = 'spn',
    ) -> Dict:
        """Get a valid token, using cache when possible"""

        # OAuth uses a different flow
        if self.auth_provider == 'oauth':
            return self.oauth_provider.get_token(audience)

        # For env, use cache + API
        token_key = f'{audience.upper()}_{credential_type.upper()}'

        # Check if cached token is still valid
        if self.cache.is_token_valid(token_key):
            return self.cache.get_token(token_key)

        # Fetch new token from API
        token_response = self._retrieve_token_from_api(
            audience, credential_type
        )
        if not token_response:
            raise ResourceNotFoundError('Access token not found.')

        # Store in cache
        self.cache.store_token(
            token_key,
            token_response['access_token'],
            token_response['expires_in'],
        )

        return self.cache.get_token(token_key)


# Global instance of the token manager
# This allows the same instance to be used across the application
_token_manager = TokenManager()


def set_auth_provider(source: Literal['env', 'oauth'] = 'env') -> None:
    """
    Set the authentication provider for token retrieval.

    Args:
        source (str): The provider of credentials. Can be "env" or "oauth".

    Returns:
        None

    Raises:
        OptionNotAvailableError: If the source is not one of the available options.

    Examples:
        ### Environment variables (.env, GitHub Secrets, Ado Secrets...)
        ```python
        set_auth_provider("env")
        ```

        ### OAuth (Interactive)
        ```python
        set_auth_provider("oauth")
        ```
    """
    global _token_manager
    _token_manager.set_auth_provider(source)


def clear_token_cache() -> None:
    """
    Clear the token cache by deleting the cache file.

    This will force all subsequent token requests to retrieve new tokens
    from the authentication provider.

    Returns:
        None

    Examples:
        ```python
        from pyfabricops.api.auth import clear_token_cache

        # Clear all cached tokens
        clear_token_cache()
        ```
    """
    global _token_manager
    _token_manager.cache.clear_cache()


def _get_token(
    audience: Literal['fabric', 'powerbi'] = 'fabric',
    auth_provider: Literal['env', 'oauth'] = 'env',
    credential_type: Literal['spn', 'user'] = 'spn',
) -> Union[dict, None]:
    """Get a token"""
    return _token_manager.get_token(audience, credential_type)
