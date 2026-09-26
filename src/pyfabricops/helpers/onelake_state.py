"""
Deployment states kept in a OneLake lakehouse.

``OneLakeStateBackend`` keeps the state of each environment as a JSON file in
the Files of a lakehouse, and its lock next to it, through the OneLake Blob
API. Every write is conditional: a state is saved only over the one the run
read, and a lock is created only where there is none, so two runs never
overwrite each other. It needs a token for OneLake, which accepts only the
Azure Storage audience, and no dependency beyond ``requests``.
"""

from __future__ import annotations

import json
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

from ..api.api import _send
from ..api.auth import _get_token
from ..core.workspaces import resolve_workspace
from ..items.lakehouses import resolve_lakehouse
from ..utils.exceptions import (
    AuthenticationError,
    ConfigurationError,
    RequestError,
)
from .deployment_state import (
    LOCK_TTL_SECONDS,
    DeploymentLock,
    DeploymentState,
    _force_unlock,
    _hold_lock,
    _lock_json,
    _unknown_lock,
    state_file_name,
)

__all__ = ["ONELAKE_BLOB_ENDPOINT", "OneLakeStateBackend"]

# The global OneLake Blob endpoint. A regional one, such as
# https://westus-onelake.blob.fabric.microsoft.com, keeps the data in its
# region.
ONELAKE_BLOB_ENDPOINT = "https://onelake.blob.fabric.microsoft.com"

# The Blob API version of every request, and how long to wait for an answer.
_API_VERSION = "2021-06-08"
_TIMEOUT_SECONDS = 60


class OneLakeStateBackend:
    """
    Keep deployment states as JSON files in a OneLake lakehouse.

    Each environment gets ``Files/<folder>/<environment>.json`` in the
    lakehouse, named as ``LocalJsonStateBackend`` names its files, and its
    lock ``<environment>.lock`` next to it. The lakehouse can be in any
    workspace the identity can write to, such as one kept for operations.

    A state is saved only over the one ``load`` read, or where there was
    none: when another run saved one in between, the save fails instead of
    overwriting it. A lock is created only where there is none; it says who
    holds it and until when, and once expired another run takes it over.

    The workspace and the lakehouse are looked up once, by name or ID, and
    then reached by ID. The identity needs a token for OneLake, which
    ``set_auth_provider`` gets as for the Fabric API.

    Args:
        workspace (str): The name or ID of the lakehouse's workspace.
        lakehouse (str): The name or ID of the lakehouse.
        folder (str, optional): The folder under ``Files``. Defaults to
            ``"pyfabricops/state"``.
        endpoint (str, optional): The OneLake Blob endpoint. Defaults to the
            global one, ``ONELAKE_BLOB_ENDPOINT``.
        lock_timeout (float, optional): How many seconds to wait for a lock
            another run holds. Defaults to 0: fail at once.
        lock_ttl (float, optional): How many seconds a lock holds unless its
            run releases it. Defaults to two hours.

    Examples:
        ```python
        state = OneLakeStateBackend('Ops', 'DeploymentState')
        report = deploy_all_items(
            'Sales-PRD',
            staging,
            start_path=staging,
            repository_path='workspace',
            state_backend=state,
            environment='prod',
        )
        ```
    """

    def __init__(
        self,
        workspace: str,
        lakehouse: str,
        folder: str = "pyfabricops/state",
        *,
        endpoint: str = ONELAKE_BLOB_ENDPOINT,
        lock_timeout: float = 0,
        lock_ttl: float = LOCK_TTL_SECONDS,
    ) -> None:
        self._workspace = workspace
        self._lakehouse = lakehouse
        self._folder = folder.strip("/")
        self._endpoint = endpoint.rstrip("/")
        self._lock_timeout = lock_timeout
        self._lock_ttl = lock_ttl
        # The URL of the folder, once the workspace and lakehouse are found.
        self._base: str | None = None
        # For each environment loaded, the ETag of its state, or None when
        # it had none.
        self._etags: dict[str, str | None] = {}
        self._locks = _OneLakeLocks(self)

    def load(self, environment: str) -> DeploymentState | None:
        """
        Return the state of an environment, or None when it has none.

        Args:
            environment (str): The environment name.

        Returns:
            DeploymentState | None: The state, or None without a file.

        Raises:
            ConfigurationError: If the file is not a valid state, or holds the
                state of another environment, or the lakehouse is not found.
            RequestError: If OneLake cannot be read.
        """
        file = f"{state_file_name(environment)}.json"
        response = self._request("GET", file)
        if response.status_code == 404:
            self._etags[environment] = None
            return None
        self._check(response, "read", file)

        where = self._where(file)
        try:
            data = json.loads(response.content)
        except ValueError as e:
            raise ConfigurationError(f"{where} is not valid JSON: {e}") from e
        state = DeploymentState.from_dict(data, source=where)
        if state.environment != environment:
            raise ConfigurationError(
                f"{where} holds the state of environment "
                f"'{state.environment}', not '{environment}'."
            )
        self._etags[environment] = response.headers.get("ETag")
        return state

    def save(self, environment: str, state: DeploymentState) -> None:
        """
        Store the state of an environment, over the one ``load`` read.

        Without an earlier ``load`` of the environment, the state is written
        whatever the file holds.

        Args:
            environment (str): The environment name.
            state (DeploymentState): The state to store.

        Raises:
            ConfigurationError: If the state belongs to another environment,
                or the lakehouse is not found.
            RequestError: If another run saved a state since ``load``, which
                is left as it is, or OneLake cannot be written.
        """
        if state.environment != environment:
            raise ConfigurationError(
                f"Cannot save the state of environment '{state.environment}' "
                f"as '{environment}'."
            )
        file = f"{state_file_name(environment)}.json"
        content = (
            json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        headers = {
            "x-ms-blob-type": "BlockBlob",
            "Content-Type": "application/json",
        }
        if environment in self._etags:
            etag = self._etags[environment]
            headers.update(
                {"If-Match": etag} if etag else {"If-None-Match": "*"}
            )

        response = self._request("PUT", file, data=content, headers=headers)
        if response.status_code in (409, 412):
            # A request tried again after its answer was lost finds its own
            # write: then the state is saved.
            current = self._request("GET", file)
            if current.status_code != 200 or current.content != content:
                raise RequestError(
                    f"Deployment state '{environment}' changed in "
                    f"{self._where(file)} since this run read it, so it was "
                    "not overwritten: another run deployed to the "
                    "environment meanwhile."
                )
            response = current
        else:
            self._check(response, "write", file)
        self._etags[environment] = response.headers.get("ETag")

    def lock(self, environment: str) -> AbstractContextManager[DeploymentLock]:
        """
        Hold the lock of an environment for the length of a ``with`` block.

        Args:
            environment (str): The environment name.

        Returns:
            AbstractContextManager[DeploymentLock]: Gives the lock held, and
                releases it when the block ends, even on an error.

        Raises:
            DeploymentLockedError: On entering the block, if another run
                holds the lock and still does after ``lock_timeout``
                seconds.
        """
        return _hold_lock(
            self._locks,
            environment,
            timeout=self._lock_timeout,
            ttl=self._lock_ttl,
        )

    def force_unlock(self, environment: str) -> DeploymentLock | None:
        """
        Remove the lock of an environment, whoever holds it.

        For a lock whose run is gone, when waiting for it to expire is not
        an option. Make sure no run is deploying to the environment first.

        Args:
            environment (str): The environment name.

        Returns:
            DeploymentLock | None: The lock removed, or None without one.
        """
        return _force_unlock(self._locks, environment)

    def _request(
        self,
        method: str,
        file: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> requests.Response:
        """
        Send a Blob request for a file of the folder.

        A request is tried again after a transient failure: the callers
        tell a write of their own from another run's.

        Raises:
            AuthenticationError: If no token for OneLake can be had.
            RequestError: If OneLake cannot be reached.
        """
        token = _get_token(audience="storage")
        if not token or not token.get("access_token"):
            raise AuthenticationError(
                "Failed to retrieve a token for OneLake. Ensure that the "
                "authentication is set up correctly."
            )
        try:
            return _send(
                retry_transient=True,
                method=method,
                url=f"{self._base_url()}/{file}",
                headers={
                    "Authorization": f"Bearer {token['access_token']}",
                    "x-ms-version": _API_VERSION,
                    **(headers or {}),
                },
                data=data,
                timeout=_TIMEOUT_SECONDS,
            )
        except requests.exceptions.RequestException as e:
            raise RequestError(
                f"OneLake could not be reached for {self._where(file)}: {e}"
            ) from e

    def _base_url(self) -> str:
        """
        Return the URL of the folder, by the IDs of workspace and lakehouse.

        Raises:
            ConfigurationError: If the workspace or the lakehouse is not
                found.
        """
        if self._base is None:
            workspace_id = resolve_workspace(self._workspace)
            if workspace_id is None:
                raise ConfigurationError(
                    f"Workspace '{self._workspace}' not found."
                )
            lakehouse_id = resolve_lakehouse(workspace_id, self._lakehouse)
            if lakehouse_id is None:
                raise ConfigurationError(
                    f"Lakehouse '{self._lakehouse}' not found in workspace "
                    f"'{self._workspace}'."
                )
            files = f"Files/{self._folder}" if self._folder else "Files"
            self._base = (
                f"{self._endpoint}/{workspace_id}/{lakehouse_id}/{files}"
            )
        return self._base

    def _where(self, file: str) -> str:
        """Name a file for a message, by the names it was given."""
        folder = f"{self._folder}/" if self._folder else ""
        return f"{self._workspace}/{self._lakehouse}/Files/{folder}{file}"

    def _check(
        self, response: requests.Response, action: str, file: str
    ) -> None:
        """
        Raise when a request failed.

        Raises:
            RequestError: With the status and OneLake's error code.
        """
        if not response.ok:
            code = response.headers.get("x-ms-error-code")
            status = (
                f"{response.status_code} {code}"
                if code
                else (f"HTTP {response.status_code}")
            )
            raise RequestError(
                f"OneLake could not {action} {self._where(file)}: {status}."
            )


class _OneLakeLocks:
    """The lock files of a OneLake backend; a lock's version is its ETag."""

    def __init__(self, backend: OneLakeStateBackend) -> None:
        self._backend = backend

    def create(self, lock: DeploymentLock) -> str | None:
        file = _lock_file(lock.environment)
        response = self._backend._request(
            "PUT",
            file,
            data=_lock_json(lock).encode("utf-8"),
            headers={**_LOCK_HEADERS, "If-None-Match": "*"},
        )
        if response.status_code in (409, 412):
            return None
        self._backend._check(response, "create the lock", file)
        return str(response.headers.get("ETag", ""))

    def read(self, environment: str) -> tuple[DeploymentLock, str] | None:
        file = _lock_file(environment)
        response = self._backend._request("GET", file)
        if response.status_code == 404:
            return None
        self._backend._check(response, "read the lock", file)
        try:
            lock = DeploymentLock.from_dict(
                json.loads(response.content),
                source=self._backend._where(file),
            )
        except (ValueError, ConfigurationError):
            lock = _unknown_lock(
                environment, _last_modified(response), self._backend._lock_ttl
            )
        return lock, str(response.headers.get("ETag", ""))

    def replace(self, lock: DeploymentLock, version: str) -> str | None:
        file = _lock_file(lock.environment)
        response = self._backend._request(
            "PUT",
            file,
            data=_lock_json(lock).encode("utf-8"),
            headers={**_LOCK_HEADERS, "If-Match": version},
        )
        if response.status_code in (404, 409, 412):
            return None
        self._backend._check(response, "take over the lock", file)
        return str(response.headers.get("ETag", ""))

    def delete(self, environment: str, version: str | None) -> bool:
        file = _lock_file(environment)
        response = self._backend._request(
            "DELETE",
            file,
            headers={"If-Match": version} if version is not None else None,
        )
        if response.status_code in (404, 412):
            return False
        self._backend._check(response, "release the lock", file)
        return True


# The headers of a lock written as a block blob.
_LOCK_HEADERS = {
    "x-ms-blob-type": "BlockBlob",
    "Content-Type": "application/json",
}


def _lock_file(environment: str) -> str:
    """Name the file that holds the lock of an environment."""
    return f"{state_file_name(environment)}.lock"


def _last_modified(response: requests.Response) -> datetime:
    """When a file last changed, from its answer, or now if it does not say."""
    try:
        return parsedate_to_datetime(response.headers["Last-Modified"])
    except (KeyError, TypeError, ValueError):
        return datetime.now(timezone.utc)
