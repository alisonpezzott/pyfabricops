"""
Deployment state: what was last deployed successfully to an environment.

A ``DeploymentState`` records the workspace an environment targets and the
last commit deployed successfully for each item type, so the next
deployment of a type compares only what changed since then. It is written
only after a deployment in which every item succeeded, and it never holds
secrets.

``DeploymentStateBackend`` is where states are kept; the engine knows
nothing more. ``LocalJsonStateBackend`` keeps them as JSON files in a local
folder, such as one a pipeline restores before a deployment and saves
after it.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

from ..utils.exceptions import ConfigurationError

__all__ = [
    "DeploymentState",
    "DeploymentStateBackend",
    "LocalJsonStateBackend",
]

_SCHEMA_VERSION = 1

_TEXT_FIELDS = (
    "environment",
    "workspace",
    "workspace_id",
    "source_commit",
    "deployed_at_utc",
)


@dataclass(frozen=True)
class DeploymentState:
    """
    The last successful deployment to an environment.

    Attributes:
        environment (str): The environment the state is kept under.
        workspace (str): The workspace name or ID the deployments target, as
            given to ``deploy_all_items``.
        workspace_id (str): The resolved workspace ID.
        source_commit (str): The commit the last successful deployment
            deployed.
        commits (Mapping[str, str]): The last commit deployed successfully
            for each item type: where its next deployment compares from.
            Read-only.
        deployed_at_utc (str): When the last successful deployment finished,
            as ``YYYY-MM-DDTHH:MM:SSZ``.
        schema_version (int): The layout of the stored state.
    """

    environment: str
    workspace: str
    workspace_id: str
    source_commit: str
    commits: Mapping[str, str]
    deployed_at_utc: str
    schema_version: int = _SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "commits", MappingProxyType(dict(self.commits))
        )

    def targets(self, workspace: str) -> bool:
        """
        Tell whether the state was recorded for a workspace.

        Args:
            workspace (str): A workspace name or ID.

        Returns:
            bool: True when it is the workspace given or its resolved ID.
        """
        return workspace in (self.workspace, self.workspace_id)

    def to_dict(self) -> dict[str, Any]:
        """
        Return the state as JSON-ready data.

        Returns:
            dict[str, Any]: The fields, with ``commits`` as a plain dict.
        """
        return {
            "schema_version": self.schema_version,
            **{name: getattr(self, name) for name in _TEXT_FIELDS},
            "commits": dict(self.commits),
        }

    @classmethod
    def from_dict(cls, data: Any, *, source: str) -> DeploymentState:
        """
        Read a state from JSON data.

        Args:
            data (Any): The parsed JSON.
            source (str): Where the data came from, for error messages.

        Returns:
            DeploymentState: The state.

        Raises:
            ConfigurationError: If the data is not a state this version of
                pyfabricops can read.
        """
        if not isinstance(data, dict):
            raise ConfigurationError(f"{source} is not a deployment state.")
        version = data.get("schema_version")
        if version != _SCHEMA_VERSION:
            raise ConfigurationError(
                f"{source} has schema version {version!r}; this version of "
                f"pyfabricops reads version {_SCHEMA_VERSION}."
            )

        text: dict[str, str] = {}
        for name in _TEXT_FIELDS:
            value = data.get(name)
            if not isinstance(value, str) or not value:
                raise ConfigurationError(f"{source} has no valid {name}.")
            text[name] = value

        commits = data.get("commits")
        if not isinstance(commits, dict) or not all(
            isinstance(k, str) and isinstance(v, str) and v
            for k, v in commits.items()
        ):
            raise ConfigurationError(f"{source} has no valid commits.")

        return cls(
            environment=text["environment"],
            workspace=text["workspace"],
            workspace_id=text["workspace_id"],
            source_commit=text["source_commit"],
            commits=commits,
            deployed_at_utc=text["deployed_at_utc"],
        )


class DeploymentStateBackend(Protocol):
    """
    Where deployment states are kept, one per environment.

    Any object with these two methods is a backend, so states can live in a
    local folder, a blob container or a pipeline artifact without the
    engine knowing. A backend must never store secrets; a state has none.
    """

    def load(self, environment: str) -> DeploymentState | None:
        """Return the state of an environment, or None when it has none."""
        ...

    def save(self, environment: str, state: DeploymentState) -> None:
        """Store the state of an environment, replacing the previous one."""
        ...


class LocalJsonStateBackend:
    """
    Keep deployment states as JSON files in a local folder.

    Each environment gets ``<folder>/<environment>.json``. In the file name,
    characters other than letters, digits, ``.``, ``_`` and ``-`` become
    ``-``; the environment is also stored inside the file, so two names that
    map to one file are caught. A file is replaced atomically, so a failed
    write leaves the previous state intact.

    Args:
        folder (str | Path): The folder of the state files, created on the
            first save.

    Examples:
        ```python
        state = LocalJsonStateBackend('.pyfabricops/state')
        report = deploy_all_items(
            'Sales-PRD',
            'workspace',
            start_path='workspace',
            state_backend=state,
            environment='prod',
        )
        ```
    """

    def __init__(self, folder: str | Path) -> None:
        self._folder = Path(folder)

    def load(self, environment: str) -> DeploymentState | None:
        """
        Return the state of an environment, or None when it has none.

        Args:
            environment (str): The environment name.

        Returns:
            DeploymentState | None: The state, or None without a file.

        Raises:
            ConfigurationError: If the file is not a valid state, or holds the
                state of another environment.
        """
        path = self._path(environment)
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            return None
        try:
            data = json.loads(content)
        except ValueError as e:
            raise ConfigurationError(f"{path} is not valid JSON: {e}") from e

        state = DeploymentState.from_dict(data, source=str(path))
        if state.environment != environment:
            raise ConfigurationError(
                f"{path} holds the state of environment "
                f"'{state.environment}', not '{environment}'."
            )
        return state

    def save(self, environment: str, state: DeploymentState) -> None:
        """
        Store the state of an environment, replacing the previous one.

        Args:
            environment (str): The environment name.
            state (DeploymentState): The state to store.

        Raises:
            ConfigurationError: If the state belongs to another environment.
            OSError: If the file cannot be written.
        """
        if state.environment != environment:
            raise ConfigurationError(
                f"Cannot save the state of environment '{state.environment}' "
                f"as '{environment}'."
            )
        path = self._path(environment)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(state.to_dict(), indent=2, sort_keys=True)

        handle, temporary = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as f:
                f.write(content + "\n")
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def _path(self, environment: str) -> Path:
        """Return the file that keeps the state of an environment."""
        name = re.sub(r"[^A-Za-z0-9._-]+", "-", environment).strip(".-")
        if not name:
            raise ConfigurationError(
                f"'{environment}' cannot name a deployment state file."
            )
        return self._folder / f"{name}.json"
