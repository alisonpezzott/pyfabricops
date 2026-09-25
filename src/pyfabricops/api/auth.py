import contextlib
import hashlib
import json
import os
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from typing import Any, Literal

import requests
from azure.identity import InteractiveBrowserCredential
from dotenv import load_dotenv

from ..utils.exceptions import (
    AuthenticationError,
    OptionNotAvailableError,
    ResourceNotFoundError,
)
from ..utils.logging import get_logger
from .scopes import FABRIC_SCOPE, GRAPH_SCOPE, POWERBI_SCOPE, TOKEN_TEMPLATE

logger = get_logger(__name__)

# Define what should be publicly exported from this module
__all__ = ["set_auth_provider", "clear_token_cache"]


def _default_cache_file() -> str:
    """Return the token cache file in the cache folder of the current user."""
    home = os.path.expanduser("~")
    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA") or os.path.join(
            home, "AppData", "Local"
        )
    elif sys.platform == "darwin":
        base = os.path.join(home, "Library", "Caches")
    else:
        base = os.getenv("XDG_CACHE_HOME") or os.path.join(home, ".cache")
    return os.path.join(base, "pyfabricops", "token_cache.json")


def _belongs_to_another_user(path: str) -> bool:
    """Tell whether a path exists and another user owns it (POSIX only)."""
    getuid: Callable[[], int] | None = getattr(os, "getuid", None)
    if getuid is None:
        return False
    try:
        return os.stat(path).st_uid != getuid()
    except OSError:
        # Missing or unreachable: nobody's file to refuse.
        return False


class TokenCache:
    """
    Keep access tokens in a file only the current user can read.

    By default the file is ``pyfabricops/token_cache.json`` in the cache
    folder of the user (``%LOCALAPPDATA%`` on Windows, ``~/Library/Caches``
    on macOS, ``$XDG_CACHE_HOME`` or ``~/.cache`` elsewhere), and the
    ``pyfabricops`` folder is made private to the user. The file is replaced
    atomically by one only its owner can read, and a file owned by another
    user is never used. When the file cannot be used, the tokens are kept
    in memory for the rest of the process.

    Args:
        cache_file (str, optional): The cache file. Defaults to the one in
            the cache folder of the user.
    """

    def __init__(self, cache_file: str | None = None):
        self._private_folder = cache_file is None
        self.cache_file = cache_file or _default_cache_file()
        # The tokens of this process, once the file cannot be used.
        self._memory: dict[str, Any] | None = None

    def _use_memory(self, reason: str) -> None:
        """Keep the tokens in memory for the rest of the process."""
        if self._memory is None:
            logger.warning(
                f"Token cache {self.cache_file} not used ({reason}); tokens "
                "are kept in memory for this process."
            )
            self._memory = {}

    def load_tokens(self) -> dict[str, Any]:
        """Load tokens from cache"""
        if self._memory is not None:
            return dict(self._memory)
        if _belongs_to_another_user(self.cache_file):
            self._use_memory("the file belongs to another user")
            return {}
        try:
            with open(self.cache_file, encoding="utf-8") as f:
                tokens = json.load(f)
        except (OSError, ValueError):
            return {}
        return tokens if isinstance(tokens, dict) else {}

    def save_tokens(self, tokens: dict[str, Any]) -> None:
        """Save tokens to cache"""
        if self._memory is None:
            try:
                self._write(tokens)
                return
            except OSError as e:
                self._use_memory(str(e))
        self._memory = dict(tokens)

    def _write(self, tokens: dict[str, Any]) -> None:
        """Replace the file atomically by one only its owner can read."""
        folder = os.path.dirname(os.path.abspath(self.cache_file))
        if self._private_folder:
            os.makedirs(folder, mode=0o700, exist_ok=True)
            if _belongs_to_another_user(folder):
                raise PermissionError(f"{folder} belongs to another user")
            if hasattr(os, "getuid"):
                os.chmod(folder, 0o700)
        elif _belongs_to_another_user(self.cache_file):
            raise PermissionError("the file belongs to another user")

        # mkstemp creates the file readable and writable by its owner only.
        handle, temporary = tempfile.mkstemp(dir=folder, prefix=".tokens-")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as f:
                json.dump(tokens, f)
            os.replace(temporary, self.cache_file)
        except BaseException:
            with contextlib.suppress(OSError):
                os.remove(temporary)
            raise

    def get_token(self, token_key: str) -> dict | None:
        """Get a specific token from cache"""
        tokens = self.load_tokens()
        return tokens.get(token_key)

    def is_token_valid(
        self, token_key: str, buffer_seconds: int = 300
    ) -> bool:
        """Check if a token is still valid"""
        token_data = self.get_token(token_key)
        if not token_data or not token_data.get("access_token"):
            return False

        now = time.time()
        expires_at = token_data.get("expires_at", 0)
        return (expires_at - now) > buffer_seconds

    def store_token(self, token_key: str, access_token: str, expires_in: int):
        """Store a new token in cache"""
        tokens = self.load_tokens()
        tokens[token_key] = {
            "access_token": access_token,
            "expires_at": time.time() + expires_in,
        }
        self.save_tokens(tokens)

    def clear_cache(self) -> None:
        """Clear the token cache by deleting the cache file"""
        if self._memory is not None:
            self._memory = {}
        if _belongs_to_another_user(self.cache_file):
            logger.warning(
                f"Cache file {self.cache_file} belongs to another user; "
                "not removed."
            )
            return
        try:
            os.remove(self.cache_file)
        except FileNotFoundError:
            logger.warning(f"Cache file not found: {self.cache_file}")
        else:
            logger.info(f"Token cache cleared: {self.cache_file}")


def _identity_key(
    audience: str,
    credential_type: str,
    credentials: Mapping[str, str | None],
) -> str:
    """
    Name the cache entry of a token after the identity that obtains it.

    The tenant, the client ID and, for the password flow, the username are
    hashed, so the cache does not list them; secrets are never part of it.
    """
    parts = [
        credentials.get("fab_tenant_id"),
        credentials.get("fab_client_id"),
    ]
    if credential_type == "user":
        parts.append(credentials.get("fab_username"))
    identity = "\n".join(part or "" for part in parts)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
    return f"{audience.upper()}_{credential_type.upper()}_{digest}"


class CredentialProvider(ABC):
    """Abstract class for different credential providers"""

    @abstractmethod
    def get_credentials(self) -> dict[str, str]:
        """Return the necessary credentials"""
        pass


class EnvCredentialProvider(CredentialProvider):
    """Environment variable credential provider"""

    def get_credentials(self) -> dict[str, str]:
        load_dotenv()
        return {
            "fab_client_id": os.getenv("FAB_CLIENT_ID"),
            "fab_client_secret": os.getenv("FAB_CLIENT_SECRET"),
            "fab_tenant_id": os.getenv("FAB_TENANT_ID"),
            "fab_username": os.getenv("FAB_USERNAME"),
            "fab_password": os.getenv("FAB_PASSWORD"),
            "github_token": os.getenv("GH_TOKEN"),
        }


class OAuthProvider:
    """OAuth interactive authentication provider"""

    def __init__(self, cache: TokenCache):
        self.cache = cache

    def get_token(
        self, audience: Literal["fabric", "powerbi", "graph"] = "fabric"
    ) -> dict:
        if audience not in ["fabric", "powerbi", "graph"]:
            raise OptionNotAvailableError(
                f"Audience not available. Available: fabric, powerbi, graph. Got: {audience}"
            )
        if audience == "graph":
            scope = GRAPH_SCOPE
        elif audience == "powerbi":
            scope = POWERBI_SCOPE
        else:
            scope = FABRIC_SCOPE
        token_key = f"{audience.upper()}_INTERACTIVE"

        # Check if cached token is still valid
        if self.cache.is_token_valid(token_key):
            return self.cache.get_token(token_key)

        logger.info("Opening browser for user authentication...")
        credential = InteractiveBrowserCredential()
        new_token = credential.get_token(scope)

        if not new_token:
            raise ResourceNotFoundError("Access token not found.")

        logger.success("Token retrieved successfully.")

        # Calculate expires_in based on expires_on
        expires_in = int(new_token.expires_on - time.time())
        self.cache.store_token(token_key, new_token.token, expires_in)

        return self.cache.get_token(token_key)


class FabricNotebookProvider:
    """Fabric Notebook authentication provider using notebookutils.credentials"""

    def __init__(self, cache: TokenCache):
        self.cache = cache
        self._notebookutils = None

    def _get_notebookutils(self):
        """Lazy load notebookutils module"""
        if self._notebookutils is None:
            try:
                from notebookutils import credentials

                self._notebookutils = credentials
            except ImportError:
                raise AuthenticationError(
                    "notebookutils is not available. "
                    "This authentication method only works inside Microsoft Fabric notebooks. "
                    'If you are running outside Fabric, use set_auth_provider("env") or set_auth_provider("oauth") instead.'
                )
        return self._notebookutils

    def get_token(
        self, audience: Literal["fabric", "powerbi", "graph"] = "fabric"
    ) -> dict:
        """Get token from Fabric notebook context"""
        token_key = f"{audience.upper()}_NOTEBOOK"

        # Check if cached token is still valid
        if self.cache.is_token_valid(token_key):
            return self.cache.get_token(token_key)

        logger.info("Getting token from Fabric notebook context...")
        credentials = self._get_notebookutils()

        # Get token using notebookutils
        # For Power BI API, use 'pbi' resource
        # For Fabric API, use 'storage' or the appropriate resource
        resource = "pbi" if audience == "powerbi" else "pbi"
        access_token = credentials.getToken(resource)

        if not access_token:
            raise ResourceNotFoundError(
                f"Access token not found for resource: {resource}"
            )

        logger.success("Token retrieved successfully from Fabric notebook.")

        # Store in cache with default expiration (1 hour)
        expires_in = 3600
        self.cache.store_token(token_key, access_token, expires_in)

        return self.cache.get_token(token_key)


class TokenManager:
    """Main token and authentication manager"""

    def __init__(
        self, auth_provider: Literal["env", "oauth", "fabric"] = "env"
    ):
        self.cache = TokenCache()
        self.auth_provider = auth_provider
        self.credential_type: Literal["spn", "user"] = "spn"
        self._credential_providers = {
            "env": EnvCredentialProvider(),
        }
        self.oauth_provider = OAuthProvider(self.cache)
        self.fabric_provider = FabricNotebookProvider(self.cache)

    def set_auth_provider(
        self,
        source: Literal["env", "oauth", "fabric"] = "env",
        credential_type: Literal["spn", "user"] = "spn",
    ):
        """Define the authentication provider and credential type"""
        if source not in ["env", "oauth", "fabric"]:
            raise OptionNotAvailableError(
                f"Source not available. Available: env, oauth, fabric. Got: {source}"
            )
        if credential_type not in ["spn", "user"]:
            raise OptionNotAvailableError(
                f"credential_type not available. Available: spn, user. Got: {credential_type}"
            )
        self.auth_provider = source
        self.credential_type = credential_type

    def _build_token_payload(
        self,
        audience: Literal["fabric", "powerbi", "graph"],
        credential_type: Literal["spn", "user"],
        credentials: dict[str, str],
    ) -> dict:
        """Construct the payload for token request"""
        if audience == "graph":
            scope = GRAPH_SCOPE
        elif audience == "powerbi":
            scope = POWERBI_SCOPE
        else:
            scope = FABRIC_SCOPE

        payload = {
            "client_id": credentials["fab_client_id"],
            "client_secret": credentials["fab_client_secret"],
            "tenant_id": credentials["fab_tenant_id"],
            "grant_type": "client_credentials"
            if credential_type == "spn"
            else "password",
            "scope": scope,
        }

        if credential_type == "user":
            payload["username"] = credentials["fab_username"]
            payload["password"] = credentials["fab_password"]

        return payload

    def _retrieve_token_from_api(
        self,
        audience: Literal["fabric", "powerbi", "graph"],
        credential_type: Literal["spn", "user"],
    ) -> dict:
        """Makes an HTTP request to retrieve the token"""
        if self.auth_provider not in self._credential_providers:
            raise OptionNotAvailableError(
                f"Invalid auth provider: {self.auth_provider}"
            )

        credentials = self._credential_providers[
            self.auth_provider
        ].get_credentials()
        tenant_id = credentials["fab_tenant_id"]
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
                    f"Token request failed: {resp.status_code} - {resp.text}"
                )
        except Exception as e:
            raise AuthenticationError(f"Failed to retrieve token: {str(e)}")

    def get_token(
        self,
        audience: Literal["fabric", "powerbi", "graph"] = "fabric",
        credential_type: Literal["spn", "user"] | None = None,
    ) -> dict:
        """Get a valid token, using cache when possible"""

        # Resolve credential_type: use the globally configured value when not
        # explicitly overridden by the caller.
        if credential_type is None:
            credential_type = self.credential_type

        # OAuth uses a different flow
        if self.auth_provider == "oauth":
            return self.oauth_provider.get_token(audience)

        # Fabric notebook uses notebookutils
        if self.auth_provider == "fabric":
            return self.fabric_provider.get_token(audience)

        # For env, use cache + API, with one cache entry per identity
        provider = self._credential_providers.get(self.auth_provider)
        credentials = provider.get_credentials() if provider else {}
        token_key = _identity_key(audience, credential_type, credentials)

        # Check if cached token is still valid
        if self.cache.is_token_valid(token_key):
            return self.cache.get_token(token_key)

        # Fetch new token from API
        token_response = self._retrieve_token_from_api(
            audience, credential_type
        )
        if not token_response:
            raise ResourceNotFoundError("Access token not found.")

        # Store in cache
        self.cache.store_token(
            token_key,
            token_response["access_token"],
            token_response["expires_in"],
        )

        return self.cache.get_token(token_key)


# Global instance of the token manager
# This allows the same instance to be used across the application
_token_manager = TokenManager()


def set_auth_provider(
    source: Literal["env", "oauth", "fabric"] = "env",
    *,
    credential_type: Literal["spn", "user"] = "spn",
) -> None:
    """
    Set the authentication provider for token retrieval.

    Args:
        source (str): The provider of credentials. Can be ``"env"``,
            ``"oauth"``, or ``"fabric"``.
        credential_type (str): The credential flow to use when
            ``source="env"``. ``"spn"`` (default) uses the
            ``client_credentials`` grant with ``FAB_CLIENT_ID``,
            ``FAB_CLIENT_SECRET``, and ``FAB_TENANT_ID``.
            ``"user"`` uses the ROPC ``password`` grant with
            ``FAB_USERNAME``, ``FAB_PASSWORD``, ``FAB_CLIENT_ID``, and
            ``FAB_TENANT_ID``. Ignored for ``"oauth"`` and ``"fabric"``
            providers.

    Returns:
        None

    Raises:
        OptionNotAvailableError: If the source or credential_type is not
            one of the available options.

    Examples:
        ### Service Principal (default)
        ```python
        set_auth_provider("env")
        # or explicitly:
        set_auth_provider("env", credential_type="spn")
        ```

        ### User / ROPC — useful for CI/CD without a Service Principal
        ```python
        set_auth_provider("env", credential_type="user")
        ```

        ### OAuth (Interactive)
        ```python
        set_auth_provider("oauth")
        ```

        ### Fabric Notebook (uses notebookutils.credentials)
        ```python
        set_auth_provider("fabric")
        ```
        This method is designed for use inside Microsoft Fabric notebooks where
        the user is already authenticated. It uses notebookutils.credentials.getToken()
        to retrieve the access token.
    """
    global _token_manager
    _token_manager.set_auth_provider(source, credential_type=credential_type)


def clear_token_cache() -> None:
    """
    Clear the token cache by deleting the cache file.

    This will force all subsequent token requests to retrieve new tokens
    from the authentication provider. With ``set_auth_provider("env")``
    each identity (tenant, client ID and, for the password flow, user) has
    its own cache entry, so switching credentials needs no clearing; clear
    the cache to sign in with another account through ``"oauth"``.

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
    audience: Literal["fabric", "powerbi", "graph"] = "fabric",
    auth_provider: Literal["env", "oauth", "fabric"] = "env",
    credential_type: Literal["spn", "user"] | None = None,
) -> dict | None:
    """Get a token, using the globally configured credential_type when not overridden."""
    return _token_manager.get_token(audience, credential_type)
