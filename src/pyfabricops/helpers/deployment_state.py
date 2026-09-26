"""
Deployment state: what was last deployed successfully to an environment.

A ``DeploymentState`` records the workspace an environment targets, the
last commit deployed successfully for each item type, so the next
deployment of a type compares only what changed since then, and the hash
and folder last sent for each item, so an item sent unchanged needs
nothing. It is written only after a deployment in which every item
succeeded, and it never holds secrets.

``DeploymentStateBackend`` is where states are kept; the engine knows
nothing more. ``LocalJsonStateBackend`` keeps them as JSON files in a local
folder, and ``OneLakeStateBackend``, in ``pyfabricops.helpers.onelake_state``,
in the Files of a lakehouse, where they outlive any CI run.

A backend that also locks (``LockingStateBackend``) keeps two runs from
deploying to one environment at a time: a run holds a ``DeploymentLock``
from before it reads the state until after it records it. A lock has a
validity, after which another run may take it over, so a run that died
holding it does not block the environment for good.
"""

from __future__ import annotations

import getpass
import json
import os
import re
import socket
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from ..helpers.deployment_plan import DeployedItem
from ..utils.exceptions import ConfigurationError, DeploymentLockedError
from ..utils.logging import get_logger

__all__ = [
    "DeploymentLock",
    "DeploymentState",
    "DeploymentStateBackend",
    "LocalJsonStateBackend",
    "LockingStateBackend",
]

logger = get_logger(__name__)

_SCHEMA_VERSION = 1

# How long a lock holds when its run never releases it, and how often a run
# waiting for a lock looks again.
LOCK_TTL_SECONDS = 2 * 60 * 60
_LOCK_POLL_SECONDS = 5.0

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
        items (Mapping[tuple[str, str], DeployedItem]): What was last sent
            for each item, by ``(item_type, display_name)``: the hash of its
            definition and its folder. Read-only.
        schema_version (int): The layout of the stored state.
    """

    environment: str
    workspace: str
    workspace_id: str
    source_commit: str
    commits: Mapping[str, str]
    deployed_at_utc: str
    items: Mapping[tuple[str, str], DeployedItem] = field(default_factory=dict)
    schema_version: int = _SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "commits", MappingProxyType(dict(self.commits))
        )
        object.__setattr__(self, "items", MappingProxyType(dict(self.items)))

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
            dict[str, Any]: The fields, with ``commits`` as a plain dict and
                ``items`` keyed ``"<item_type>.<display_name>"``.
        """
        return {
            "schema_version": self.schema_version,
            **{name: getattr(self, name) for name in _TEXT_FIELDS},
            "commits": dict(self.commits),
            "items": {
                f"{item_type}.{display_name}": {
                    "item_type": item_type,
                    "display_name": display_name,
                    "content_hash": deployed.content_hash,
                    "folder_path": deployed.folder_path,
                }
                for (item_type, display_name), deployed in self.items.items()
            },
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
            items=_read_items(data.get("items", {}), source),
        )


def _read_items(raw: Any, source: str) -> dict[tuple[str, str], DeployedItem]:
    """Read the per-item records of a state; an older state has none."""
    if not isinstance(raw, dict):
        raise ConfigurationError(f"{source} has no valid items.")

    items: dict[tuple[str, str], DeployedItem] = {}
    for record in raw.values():
        if not isinstance(record, dict):
            raise ConfigurationError(f"{source} has no valid items.")
        item_type = record.get("item_type")
        display_name = record.get("display_name")
        content_hash = record.get("content_hash")
        folder_path = record.get("folder_path")
        if not (
            isinstance(item_type, str)
            and item_type
            and isinstance(display_name, str)
            and display_name
            and isinstance(content_hash, str)
            and content_hash
            and (folder_path is None or isinstance(folder_path, str))
        ):
            raise ConfigurationError(f"{source} has no valid items.")
        items[(item_type, display_name)] = DeployedItem(
            content_hash, folder_path
        )
    return items


@dataclass(frozen=True)
class DeploymentLock:
    """
    The lock a deployment run holds on the state of an environment.

    A lock holds no secret: who took it, when, and until when it holds.

    Attributes:
        environment (str): The environment whose state is locked.
        lock_id (str): A random ID, which tells this lock from any other.
        holder (str): Who took it: ``user@host``, and the CI run when there
            is one.
        acquired_at_utc (str): When it was taken, as
            ``YYYY-MM-DDTHH:MM:SSZ``.
        expires_at_utc (str): When another run may take it over, if its run
            has not released it.
    """

    environment: str
    lock_id: str
    holder: str
    acquired_at_utc: str
    expires_at_utc: str

    @classmethod
    def new(cls, environment: str, ttl_seconds: float) -> DeploymentLock:
        """
        Make a lock for this process, valid for ``ttl_seconds``.

        Args:
            environment (str): The environment to lock.
            ttl_seconds (float): How long the lock holds unless released.

        Returns:
            DeploymentLock: The lock, not taken yet.
        """
        now = datetime.now(timezone.utc).replace(microsecond=0)
        return cls(
            environment=environment,
            lock_id=uuid.uuid4().hex,
            holder=_holder(),
            acquired_at_utc=_utc_text(now),
            expires_at_utc=_utc_text(now + timedelta(seconds=ttl_seconds)),
        )

    @property
    def expired(self) -> bool:
        """Whether another run may take the lock over."""
        return _parse_utc(self.expires_at_utc) <= datetime.now(timezone.utc)

    def describe(self) -> str:
        """
        Say who holds the lock, since when and until when.

        Returns:
            str: Such as ``held by ci@runner since 2026-09-25T10:00:00Z,
                until 2026-09-25T12:00:00Z``.
        """
        return (
            f"held by {self.holder} since {self.acquired_at_utc}, until "
            f"{self.expires_at_utc}"
        )

    def to_dict(self) -> dict[str, str]:
        """
        Return the lock as JSON-ready data.

        Returns:
            dict[str, str]: The fields.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any, *, source: str) -> DeploymentLock:
        """
        Read a lock from JSON data.

        Args:
            data (Any): The parsed JSON.
            source (str): Where the data came from, for error messages.

        Returns:
            DeploymentLock: The lock.

        Raises:
            ConfigurationError: If the data is not a lock.
        """
        names = ("environment", "lock_id", "holder")
        times = ("acquired_at_utc", "expires_at_utc")
        if not isinstance(data, dict) or not all(
            isinstance(data.get(name), str) and data[name]
            for name in (*names, *times)
        ):
            raise ConfigurationError(f"{source} is not a deployment lock.")
        try:
            for name in times:
                _parse_utc(data[name])
        except ValueError as e:
            raise ConfigurationError(
                f"{source} is not a deployment lock."
            ) from e
        return cls(**{name: data[name] for name in (*names, *times)})


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


@runtime_checkable
class LockingStateBackend(DeploymentStateBackend, Protocol):
    """
    A state backend that also locks the state of an environment.

    ``deploy_all_items`` holds the lock from before it reads the state until
    after it records it, so two runs never deploy to one environment at a
    time. The backends of pyfabricops lock; a backend with only ``load``
    and ``save`` still works, without a lock.
    """

    def lock(self, environment: str) -> AbstractContextManager[DeploymentLock]:
        """
        Hold the lock of an environment for the length of a ``with`` block.

        Raises:
            DeploymentLockedError: If another run holds it.
        """
        ...

    def force_unlock(self, environment: str) -> DeploymentLock | None:
        """Remove the lock of an environment, whoever holds it."""
        ...


class LocalJsonStateBackend:
    """
    Keep deployment states as JSON files in a local folder.

    Each environment gets ``<folder>/<environment>.json``. In the file name,
    characters other than letters, digits, ``.``, ``_`` and ``-`` become
    ``-``; the environment is also stored inside the file, so two names that
    map to one file are caught. A file is replaced atomically, so a failed
    write leaves the previous state intact.

    The lock of an environment is ``<folder>/<environment>.lock``, created
    only when there is none. It says who holds it and until when; once
    expired, another run takes it over. It keeps apart runs that share the
    folder, such as two on one machine.

    Args:
        folder (str | Path): The folder of the state files, created on the
            first save.
        lock_timeout (float, optional): How many seconds to wait for a lock
            another run holds. Defaults to 0: fail at once.
        lock_ttl (float, optional): How many seconds a lock holds unless its
            run releases it. Defaults to two hours.

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

    def __init__(
        self,
        folder: str | Path,
        *,
        lock_timeout: float = 0,
        lock_ttl: float = LOCK_TTL_SECONDS,
    ) -> None:
        self._folder = Path(folder)
        self._lock_timeout = lock_timeout
        self._lock_ttl = lock_ttl
        self._locks = _LocalLocks(self._lock_path, lock_ttl)

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
        _replace(path, content + "\n")

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

    def _path(self, environment: str) -> Path:
        """Return the file that keeps the state of an environment."""
        return self._folder / f"{state_file_name(environment)}.json"

    def _lock_path(self, environment: str) -> Path:
        """Return the file that holds the lock of an environment."""
        return self._folder / f"{state_file_name(environment)}.lock"


class _LockStore(Protocol):
    """
    Where a backend keeps its locks, one per environment.

    Each change applies only to the lock as the caller last saw it, known by
    its version, so two runs cannot both win a lock.
    """

    def create(self, lock: DeploymentLock) -> str | None:
        """Write a lock where there is none: its version, or None."""
        ...

    def read(self, environment: str) -> tuple[DeploymentLock, str] | None:
        """Return the lock of an environment and its version, if any."""
        ...

    def replace(self, lock: DeploymentLock, version: str) -> str | None:
        """Replace the lock at ``version``: the new version, or None."""
        ...

    def delete(self, environment: str, version: str | None) -> bool:
        """Delete the lock at ``version``, or any for None; True if done."""
        ...


@contextmanager
def _hold_lock(
    store: _LockStore, environment: str, *, timeout: float, ttl: float
) -> Iterator[DeploymentLock]:
    """Hold the lock of an environment for the length of a ``with`` block."""
    held, version = _acquire(store, environment, timeout=timeout, ttl=ttl)
    logger.info(
        f"Deployment state '{environment}' locked until {held.expires_at_utc}."
    )
    try:
        yield held
    finally:
        if not store.delete(environment, version):
            logger.warning(
                f"The lock of deployment state '{environment}' is no longer "
                "this run's; left as it is."
            )


def _acquire(
    store: _LockStore, environment: str, *, timeout: float, ttl: float
) -> tuple[DeploymentLock, str]:
    """
    Take the lock of an environment, taking over an expired one.

    Raises:
        DeploymentLockedError: If another run holds it for ``timeout``
            seconds.
    """
    deadline = time.monotonic() + timeout
    # One ID for every attempt, so a lock this run wrote is known as its own.
    lock_id = uuid.uuid4().hex
    while True:
        mine = replace(DeploymentLock.new(environment, ttl), lock_id=lock_id)
        created = store.create(mine)
        if created is not None:
            return mine, created
        current = store.read(environment)
        if current is None:
            # Released meanwhile: try again.
            continue
        held, version = current
        if held.lock_id == lock_id:
            # Written by a request tried again after its answer was lost.
            return held, version
        if held.expired:
            replaced = store.replace(mine, version)
            if replaced is not None:
                logger.warning(
                    f"Took over the lock of deployment state '{environment}',"
                    f" which expired: it was {held.describe()}."
                )
                return mine, replaced
            continue
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DeploymentLockedError(_locked(environment, held))
        time.sleep(min(_LOCK_POLL_SECONDS, remaining))


def _force_unlock(
    store: _LockStore, environment: str
) -> DeploymentLock | None:
    """Remove the lock of an environment, whoever holds it; return it."""
    current = store.read(environment)
    if current is None:
        return None
    held, _ = current
    store.delete(environment, None)
    logger.warning(
        f"Lock of deployment state '{environment}' removed; it was "
        f"{held.describe()}."
    )
    return held


def _unknown_lock(
    environment: str, changed: datetime, ttl: float
) -> DeploymentLock:
    """
    Stand for a lock whose content cannot be read.

    Caught while it is written, or left half written, it counts as held by
    an unknown run for ``ttl`` seconds from its last change.
    """
    since = changed.astimezone(timezone.utc).replace(microsecond=0)
    return DeploymentLock(
        environment=environment,
        lock_id="",
        holder="an unknown run",
        acquired_at_utc=_utc_text(since),
        expires_at_utc=_utc_text(since + timedelta(seconds=ttl)),
    )


def _lock_json(lock: DeploymentLock) -> str:
    """Write a lock as the JSON its file holds."""
    return json.dumps(lock.to_dict(), indent=2) + "\n"


class _LocalLocks:
    """
    The lock files of a local backend; a lock's version is its ID.

    A file is created only when there is none, which the file system keeps
    to one run. Replacing or deleting one checks its ID first, which leaves
    only a short race between two runs that take over one expired lock.
    """

    def __init__(self, path_of: Callable[[str], Path], ttl: float) -> None:
        self._path_of = path_of
        self._ttl = ttl

    def create(self, lock: DeploymentLock) -> str | None:
        path = self._path_of(lock.environment)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return None
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            f.write(_lock_json(lock))
        return lock.lock_id

    def read(self, environment: str) -> tuple[DeploymentLock, str] | None:
        path = self._path_of(environment)
        try:
            content = path.read_bytes()
            changed = path.stat().st_mtime
        except FileNotFoundError:
            return None
        try:
            lock = DeploymentLock.from_dict(
                json.loads(content), source=str(path)
            )
        except (ValueError, ConfigurationError):
            lock = _unknown_lock(
                environment,
                datetime.fromtimestamp(changed, timezone.utc),
                self._ttl,
            )
        return lock, lock.lock_id

    def replace(self, lock: DeploymentLock, version: str) -> str | None:
        current = self.read(lock.environment)
        if current is None or current[1] != version:
            return None
        _replace(self._path_of(lock.environment), _lock_json(lock))
        current = self.read(lock.environment)
        if current is None or current[1] != lock.lock_id:
            return None
        return lock.lock_id

    def delete(self, environment: str, version: str | None) -> bool:
        current = self.read(environment)
        if current is None or version not in (None, current[1]):
            return False
        self._path_of(environment).unlink(missing_ok=True)
        return True


def state_file_name(environment: str) -> str:
    """
    Name the files of an environment's state and lock, without extension.

    Characters other than letters, digits, ``.``, ``_`` and ``-`` become
    ``-``.

    Raises:
        ConfigurationError: If nothing of the name is left.
    """
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", environment).strip(".-")
    if not name:
        raise ConfigurationError(
            f"'{environment}' cannot name a deployment state file."
        )
    return name


def _replace(path: Path, content: str) -> None:
    """Replace a file atomically, so a failed write leaves the old one."""
    handle, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _locked(environment: str, held: DeploymentLock) -> str:
    """Say who holds the lock of an environment, and what to do about it."""
    return (
        f"Deployment state '{environment}' is locked, {held.describe()}. "
        "Wait for that run to finish; if it is gone, call "
        f"force_unlock('{environment}') on the state backend."
    )


def _holder() -> str:
    """Name who takes a lock: the user and host, and the CI run if any."""
    try:
        user = getpass.getuser()
    except (KeyError, OSError):
        user = "unknown"
    holder = f"{user}@{socket.gethostname()}"
    if os.environ.get("GITHUB_RUN_ID"):
        return f"{holder} (GitHub Actions run {os.environ['GITHUB_RUN_ID']})"
    if os.environ.get("BUILD_BUILDID"):
        return (
            f"{holder} (Azure Pipelines build {os.environ['BUILD_BUILDID']})"
        )
    return holder


def _utc_text(moment: datetime) -> str:
    """Write a UTC time as ``YYYY-MM-DDTHH:MM:SSZ``."""
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(text: str) -> datetime:
    """
    Read a time written by ``_utc_text``.

    Raises:
        ValueError: If the text is not such a time.
    """
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
