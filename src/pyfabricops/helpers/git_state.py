"""
Deployment states kept on a branch of the Git repository.

``GitStateBackend`` keeps the state of each environment as a JSON file on a
branch of its own, ``pyfabricops/state`` by default, whose history never
joins that of the branches deployed; the lock of each environment and the
journal of its last run lie next to its state. It needs only the
repository, so it suits a project with no Fabric capacity for a lakehouse.

Every change is a commit pushed without force, which the remote accepts only
over the tip it was made on: a state is saved only over the one the run
read, and a lock is created only where there is none, so two runs never
overwrite each other. The commits are made in the local repository without
touching its working tree, index or branches, and git pushes them with the
credentials it already has; the backend handles none.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path

from ..utils.exceptions import ConfigurationError, RequestError
from .deployment_state import (
    LOCK_TTL_SECONDS,
    DeploymentJournal,
    DeploymentLock,
    DeploymentState,
    _force_unlock,
    _hold_lock,
    _lock_json,
    _parse_journal,
    _unknown_lock,
    journal_json,
    state_file_name,
)

__all__ = ["GIT_STATE_BRANCH", "GitStateBackend"]

# The branch of the states unless another is given.
GIT_STATE_BRANCH = "pyfabricops/state"

# The file that marks a branch as one this backend created. It writes to no
# branch without it, so a branch of code named by mistake is left alone.
_MARKER = ".pyfabricops-state"
_MARKER_TEXT = (
    "This file marks the branch as the one pyfabricops keeps deployment "
    "states on.\n"
)
_README = "README.md"
_README_TEXT = """\
# Deployment state

pyfabricops keeps here the deployment state of each environment this
repository deploys to:

- `<environment>.json`: what the last successful deployment sent;
- `<environment>.lock`: the lock of the run deploying, while it runs;
- `<environment>.journal.json`: what the last run did, item by item.

This branch shares no history with the others. Do not merge it, connect no
workspace to it, and do not force-push to it or delete it: the next
deployments would lose what it records.
"""

# How long a fetch or a push may take, how many times one that fails is
# tried, and how long the first wait between tries is.
_NETWORK_TIMEOUT_SECONDS = 120
_TRIES = 3
_RETRY_WAIT_SECONDS = 2.0

# How many times a change is made again over a tip that moved meanwhile.
_REBUILDS = 5

# Who makes the commits when the repository names no one.
_FALLBACK_NAME = "pyfabricops"
_FALLBACK_EMAIL = "noreply@pyfabricops.invalid"

# A folder of the branch: names of letters, digits, ".", "_" and "-", none
# starting with ".", separated by "/".
_FOLDER = re.compile(r"[\w-][\w.-]*(/[\w-][\w.-]*)*", re.ASCII)


class GitStateBackend:
    """
    Keep deployment states on a branch of the Git repository.

    Each environment gets ``<environment>.json`` on the branch, named as
    ``LocalJsonStateBackend`` names its files, and its lock
    ``<environment>.lock`` and the journal of its last run
    ``<environment>.journal.json`` next to it. The first write creates the
    branch as an orphan, with no history in common with the others, holding
    a README that says what it is and a ``.pyfabricops-state`` marker. The
    backend writes to no branch without the marker, so a branch of code
    named by mistake is left as it is.

    A state is saved only over the one ``load`` read, or where there was
    none: when another run saved one in between, the save fails instead of
    overwriting it. A lock is created only where there is none; it says who
    holds it and until when, and once expired another run takes it over.
    Each change is a commit pushed without force. When the branch moved
    meanwhile, the change is made again over the new tip, unless the file it
    changes moved too.

    The commits are made in the repository ``repository`` belongs to, and
    leave its working tree, index, HEAD and branches as they are: the tip of
    the branch is fetched into a ref under ``refs/pyfabricops/``. They say
    ``[skip ci]``, so that no pipeline runs for them, and are pushed without
    the local pre-push hooks, which check code, not states. They are made by
    the Git identity of the repository, else by
    ``pyfabricops <noreply@pyfabricops.invalid>``. Whoever pushes needs the
    right to push to the branch, and to create it the first time.

    Args:
        repository (str | Path, optional): A folder inside the repository,
            such as the checkout of a pipeline. Defaults to the current
            folder.
        branch (str, optional): The branch of the states. Defaults to
            ``"pyfabricops/state"``.
        remote (str, optional): The remote of the branch. Defaults to
            ``"origin"``.
        folder (str, optional): A folder of the branch for the files of the
            states. Defaults to its root.
        lock_timeout (float, optional): How many seconds to wait for a lock
            another run holds. Defaults to 0: fail at once.
        lock_ttl (float, optional): How many seconds a lock holds unless its
            run releases it. Defaults to two hours.

    Raises:
        ConfigurationError: If ``branch``, ``remote`` or ``folder`` is not a
            name git would take.

    Examples:
        ```python
        state = GitStateBackend('.', 'pyfabricops/state')
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
        repository: str | Path = ".",
        branch: str = GIT_STATE_BRANCH,
        *,
        remote: str = "origin",
        folder: str = "",
        lock_timeout: float = 0,
        lock_ttl: float = LOCK_TTL_SECONDS,
    ) -> None:
        if not branch or branch.startswith(("-", "/")):
            raise ConfigurationError(f"'{branch}' cannot name a branch.")
        if not remote or remote.startswith("-"):
            raise ConfigurationError(f"'{remote}' cannot name a remote.")
        folder = folder.strip("/")
        if folder and not _FOLDER.fullmatch(folder):
            raise ConfigurationError(
                f"'{folder}' cannot name a folder of the branch: use letters, "
                "digits, '.', '_' and '-', with no name starting with '.'."
            )
        self._repository = Path(repository)
        # The root of the working tree, where git runs once it is known.
        self._root: Path | None = None
        self._branch = branch
        self._remote = remote
        self._folder = folder
        self._lock_timeout = lock_timeout
        self._lock_ttl = lock_ttl
        self._ref = f"refs/heads/{branch}"
        # Where the tip of the branch is fetched to: a ref of the backend's
        # own, so no branch of the repository changes.
        self._fetched_ref = f"refs/pyfabricops/{remote}/{branch}"
        # The tip last fetched or pushed, once known; None while the branch
        # does not exist.
        self._tip: str | None = None
        self._seen = False
        self._ready = False
        self._identity: dict[str, str] | None = None
        # For each environment loaded, the blob of its state, or None when
        # it had none.
        self._versions: dict[str, str | None] = {}
        self._locks = _GitLocks(self)

    def load(self, environment: str) -> DeploymentState | None:
        """
        Return the state of an environment, or None when it has none.

        Args:
            environment (str): The environment name.

        Returns:
            DeploymentState | None: The state, or None without a file.

        Raises:
            ConfigurationError: If the file is not a valid state, or holds the
                state of another environment, or the branch was not created
                by this backend.
            RequestError: If the branch cannot be fetched.
        """
        path = self._path(f"{state_file_name(environment)}.json")
        found = self._read(path)
        if found is None:
            self._versions[environment] = None
            return None

        content, blob = found
        where = self._where(path)
        try:
            data = json.loads(content)
        except ValueError as e:
            raise ConfigurationError(f"{where} is not valid JSON: {e}") from e
        state = DeploymentState.from_dict(data, source=where)
        if state.environment != environment:
            raise ConfigurationError(
                f"{where} holds the state of environment "
                f"'{state.environment}', not '{environment}'."
            )
        self._versions[environment] = blob
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
                or the branch was not created by this backend.
            RequestError: If another run saved a state since ``load``, which
                is left as it is, or the branch cannot be pushed to.
        """
        if state.environment != environment:
            raise ConfigurationError(
                f"Cannot save the state of environment '{state.environment}' "
                f"as '{environment}'."
            )
        path = self._path(f"{state_file_name(environment)}.json")
        content = json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n"
        blob = self._store(content)
        loaded = environment in self._versions
        expected = self._versions.get(environment)
        saved = self._change(
            path,
            blob,
            message=(
                f"record the state of {environment} at "
                f"{state.source_commit[:12]}"
            ),
            allowed=lambda current: not loaded or current == expected,
        )
        if not saved:
            raise RequestError(
                f"Deployment state '{environment}' changed in "
                f"{self._where(path)} since this run read it, so it was not "
                "overwritten: another run deployed to the environment "
                "meanwhile."
            )
        self._versions[environment] = blob

    def load_journal(self, environment: str) -> DeploymentJournal | None:
        """
        Return the journal of the environment's last run, if any.

        A file that holds no journal of the environment is left alone with
        a warning: a journal only saves work, and its loss costs none.

        Args:
            environment (str): The environment name.

        Returns:
            DeploymentJournal | None: The journal, or None.

        Raises:
            RequestError: If the branch cannot be fetched.
        """
        path = self._journal_path(environment)
        found = self._read(path)
        if found is None:
            return None
        return _parse_journal(found[0], self._where(path), environment)

    def save_journal(
        self, environment: str, journal: DeploymentJournal
    ) -> None:
        """
        Store the journal of a run, replacing the one before.

        Only the run that holds the lock writes the journal, so it is
        written whatever the file holds.

        Args:
            environment (str): The environment name.
            journal (DeploymentJournal): The journal.

        Raises:
            RequestError: If the branch cannot be pushed to.
        """
        self._change(
            self._journal_path(environment),
            self._store(journal_json(journal)),
            message=f"journal {environment}",
            allowed=lambda current: True,
        )

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

    # -----------------------------------------------------------------------
    # The branch
    # -----------------------------------------------------------------------

    def _path(self, name: str) -> str:
        """Return the path of a file on the branch."""
        return f"{self._folder}/{name}" if self._folder else name

    def _journal_path(self, environment: str) -> str:
        """Return the path of the journal of an environment."""
        return self._path(f"{state_file_name(environment)}.journal.json")

    def _lock_path(self, environment: str) -> str:
        """Return the path of the lock of an environment."""
        return self._path(f"{state_file_name(environment)}.lock")

    def _where(self, path: str | None = None) -> str:
        """Name the branch, or a file on it, for a message."""
        branch = f"{self._remote}/{self._branch}"
        return f"{branch}:{path}" if path else branch

    def _read(self, path: str) -> tuple[bytes, str] | None:
        """
        Fetch the branch and read a file at its tip.

        Returns:
            tuple[bytes, str] | None: The content and the blob of the file,
                or None when the branch or the file does not exist.
        """
        tip = self._fetch()
        if tip is None:
            return None
        # One call gives both the blob and its content.
        output = self._git(
            "cat-file", "--batch", input=f"{tip}:{path}\n".encode()
        )
        header, _, rest = output.partition(b"\n")
        fields = header.decode("utf-8", errors="replace").split()
        if len(fields) != 3 or fields[1] != "blob":
            return None
        return rest[: int(fields[2])], fields[0]

    def _change(
        self,
        path: str,
        blob: str | None,
        *,
        message: str,
        allowed: Callable[[str | None], bool],
    ) -> bool:
        """
        Put a blob at a path of the branch, or remove the path, and push it.

        ``allowed`` is given the blob the path holds at the tip, or None,
        and tells whether the change may apply over it. The change is made
        over the tip last seen; when the push is refused because the branch
        moved, it is made again over the new tip. A path that holds
        ``blob`` already needs nothing, as when a push that succeeded lost
        its answer.

        Returns:
            bool: True when the tip of the branch holds the change, False
                when ``allowed`` refused what the path holds.

        Raises:
            RequestError: If a push fails while the branch does not move, or
                the branch keeps moving.
        """
        if self._seen:
            base, fresh = self._tip, False
        else:
            base, fresh = self._fetch(), True
        pushed_once = False
        rebuilds = failures = 0
        while True:
            current = self._blob(base, path)
            # A removal is done only once this run asked for it.
            if current == blob and (blob is not None or pushed_once):
                return True
            if not allowed(current):
                if fresh:
                    return False
                base, fresh = self._fetch(), True
                continue

            commit = self._commit(base, path, blob, message)
            pushed = self._push(commit)
            pushed_once = True
            if pushed.returncode == 0:
                self._tip = commit
                return True

            tip = self._fetch()
            if tip == base:
                failures += 1
                if failures >= _TRIES:
                    raise RequestError(
                        f"git could not push to {self._where()}: "
                        f"{_detail(pushed)}"
                    )
                time.sleep(_RETRY_WAIT_SECONDS * failures)
            else:
                rebuilds += 1
                if rebuilds > _REBUILDS:
                    raise RequestError(
                        f"{self._where()} kept changing while this run "
                        f"wrote {path}; it gave up after {_REBUILDS} tries."
                    )
            base, fresh = tip, True

    def _fetch(self) -> str | None:
        """
        Fetch the tip of the branch, or learn that it does not exist.

        Returns:
            str | None: The commit at the tip, or None without the branch.

        Raises:
            ConfigurationError: If the branch has no marker.
            RequestError: If the remote cannot be reached.
        """
        self._check_setup()
        for attempt in range(1, _TRIES + 1):
            fetched = self._run(
                "fetch",
                "--quiet",
                "--no-tags",
                self._remote,
                f"+{self._ref}:{self._fetched_ref}",
                network=True,
            )
            if fetched.returncode == 0:
                # One call gives the tip and tells whether it has the marker,
                # which is checked before the tip is kept, so that no later
                # change is made over a branch without it.
                tip, marked = self._git(
                    "cat-file",
                    "--batch-check=%(objectname) %(objecttype)",
                    input=(
                        f"{self._fetched_ref}^{{commit}}\n"
                        f"{self._fetched_ref}:{_MARKER}\n"
                    ).encode(),
                ).splitlines()
                if not marked.endswith(b" blob"):
                    raise ConfigurationError(
                        f"{self._where()} has no {_MARKER}: GitStateBackend "
                        "did not create it, so it leaves it alone. Give it a "
                        f"branch of its own, such as '{GIT_STATE_BRANCH}'."
                    )
                commit = tip.split()[0].decode("ascii")
                self._tip, self._seen = commit, True
                return commit

            # A fetch fails for a missing branch as for a network error:
            # ls-remote tells them apart by its exit code.
            probe = self._run(
                "ls-remote",
                "--exit-code",
                self._remote,
                self._ref,
                network=True,
            )
            if probe.returncode == 2:
                self._run("update-ref", "-d", self._fetched_ref)
                self._tip, self._seen = None, True
                return None
            if attempt < _TRIES:
                time.sleep(_RETRY_WAIT_SECONDS * attempt)
        raise RequestError(
            f"git could not fetch {self._where()}: {_detail(fetched)}"
        )

    def _push(self, commit: str) -> subprocess.CompletedProcess[bytes]:
        """Push a commit to the branch, without force or pre-push hooks."""
        return self._run(
            "push",
            "--quiet",
            "--no-verify",
            self._remote,
            f"{commit}:{self._ref}",
            network=True,
        )

    def _commit(
        self, base: str | None, path: str, blob: str | None, message: str
    ) -> str:
        """
        Make a commit over ``base`` that puts ``blob`` at ``path``.

        With None for ``blob``, the commit removes the path. Without a
        ``base``, the commit starts the branch, with its README and marker.
        The tree is built in an index of its own, so the index of the
        repository is left alone.
        """
        with tempfile.TemporaryDirectory(prefix="pyfabricops-git-") as folder:
            index = {"GIT_INDEX_FILE": str(Path(folder) / "index")}
            if base is None:
                self._git("read-tree", "--empty", env=index)
                for name, text in (
                    (_MARKER, _MARKER_TEXT),
                    (_README, _README_TEXT),
                ):
                    self._put(name, self._store(text), index)
            else:
                self._git("read-tree", base, env=index)
            if blob is None:
                self._git(
                    "update-index", "--force-remove", "--", path, env=index
                )
            else:
                self._put(path, blob, index)
            tree = self._git("write-tree", env=index).decode("ascii").strip()

        parents = ["-p", base] if base is not None else []
        output = self._git(
            "commit-tree",
            tree,
            *parents,
            "-m",
            f"chore(pyfabricops): {message} [skip ci]",
            env=self._author(),
        )
        commit = output.decode("ascii").strip()
        # A commit that does not hold the change would be pushed as if it
        # did, and a lock would stay in place: none goes out.
        if self._blob(commit, path) != blob:
            action = "remove" if blob is None else "write"
            raise ConfigurationError(
                f"git did not {action} {path} in the commit for "
                f"{self._where()}; nothing was pushed."
            )
        return commit

    def _put(self, path: str, blob: str, index: dict[str, str]) -> None:
        """Put a blob at a path of a temporary index."""
        self._git(
            "update-index",
            "--add",
            "--cacheinfo",
            f"100644,{blob},{path}",
            env=index,
        )

    def _store(self, text: str) -> str:
        """Write text to the object database and return its blob."""
        self._check_setup()
        blob = self._git(
            "hash-object", "-w", "--stdin", input=text.encode("utf-8")
        )
        return blob.decode("ascii").strip()

    def _blob(self, tip: str | None, path: str) -> str | None:
        """Return the blob at a path of a commit, or None without one."""
        if tip is None:
            return None
        found = self._run("rev-parse", "--verify", "--quiet", f"{tip}:{path}")
        if found.returncode != 0:
            return None
        return found.stdout.decode("ascii").strip()

    def _changed_at(self, path: str) -> datetime:
        """When a file last changed on the branch, or now if unknown."""
        if self._tip is not None:
            found = self._run(
                "log", "-1", "--format=%ct", self._tip, "--", path
            )
            seconds = found.stdout.decode("ascii").strip()
            if found.returncode == 0 and seconds.isdigit():
                return datetime.fromtimestamp(int(seconds), timezone.utc)
        return datetime.now(timezone.utc)

    def _check_setup(self) -> None:
        """
        Check once that the repository, the branch and the remote exist.

        Raises:
            ConfigurationError: If git cannot run, the folder is not inside a
                Git repository, a name is not one git takes, or the remote is
                not configured.
        """
        if self._ready:
            return
        top = self._run("rev-parse", "--show-toplevel")
        if top.returncode != 0:
            raise ConfigurationError(
                f"{self._repository} is not inside a Git repository, or "
                "has no working tree."
            )
        # git reads the paths some commands take, such as those of
        # update-index or a pathspec, from the folder it runs in: from the
        # root, they are the paths of the branch.
        self._root = Path(top.stdout.decode("utf-8").rstrip("\r\n"))
        # The ref the tip is fetched to holds the names of both the remote
        # and the branch: git takes it only if it takes them.
        if self._run("check-ref-format", self._fetched_ref).returncode != 0:
            raise ConfigurationError(
                f"'{self._branch}' cannot name a branch of remote "
                f"'{self._remote}'."
            )
        if self._run("remote", "get-url", self._remote).returncode != 0:
            raise ConfigurationError(
                f"Remote '{self._remote}' not found in the repository of "
                f"{self._repository}."
            )
        self._ready = True

    def _author(self) -> dict[str, str]:
        """
        Name who makes the commits, where the repository names no one.

        The Git identity of the repository, or of the environment, is kept;
        what neither gives becomes pyfabricops.
        """
        if self._identity is None:
            # user.name and user.email, from any level of the Git settings.
            found = self._run(
                "config", "--get-regexp", r"^user\.(name|email)$"
            )
            known: dict[str, str] = {}
            for line in found.stdout.decode("utf-8", "replace").splitlines():
                key, _, value = line.partition(" ")
                if value.strip():
                    known[key.split(".")[-1].upper()] = value.strip()
            fallback = {"NAME": _FALLBACK_NAME, "EMAIL": _FALLBACK_EMAIL}
            self._identity = {
                f"GIT_{role}_{part}": fallback[part]
                for role in ("AUTHOR", "COMMITTER")
                for part in ("NAME", "EMAIL")
                if part not in known and f"GIT_{role}_{part}" not in os.environ
            }
        return self._identity

    def _git(
        self,
        *args: str,
        env: dict[str, str] | None = None,
        input: bytes | None = None,
    ) -> bytes:
        """
        Run git in the repository and return its output.

        Raises:
            ConfigurationError: If git fails.
        """
        result = self._run(*args, env=env, input=input)
        if result.returncode != 0:
            raise ConfigurationError(
                f"git {args[0]} failed in {self._repository}: "
                f"{_detail(result)}"
            )
        return result.stdout

    def _run(
        self,
        *args: str,
        env: dict[str, str] | None = None,
        input: bytes | None = None,
        network: bool = False,
    ) -> subprocess.CompletedProcess[bytes]:
        """
        Run git at the root of the repository, capturing its output.

        Until the root is known, git runs in the folder given. A call to the
        remote has a timeout.

        Raises:
            ConfigurationError: If git cannot run.
            RequestError: If a call to the remote takes too long.
        """
        folder = self._root or self._repository
        try:
            return subprocess.run(
                ["git", "-C", str(folder), *args],
                input=input,
                capture_output=True,
                check=False,
                env={**os.environ, **env} if env else None,
                timeout=_NETWORK_TIMEOUT_SECONDS if network else None,
            )
        except FileNotFoundError as e:
            raise ConfigurationError(
                "git was not found; GitStateBackend needs git on PATH."
            ) from e
        except subprocess.TimeoutExpired as e:
            raise RequestError(
                f"git {args[0]} did not finish within "
                f"{_NETWORK_TIMEOUT_SECONDS} seconds for {self._where()}."
            ) from e
        except OSError as e:
            raise ConfigurationError(f"Could not run git: {e}") from e


class _GitLocks:
    """The lock files of a Git backend; a lock's version is its blob."""

    def __init__(self, backend: GitStateBackend) -> None:
        self._backend = backend

    def create(self, lock: DeploymentLock) -> str | None:
        return self._write(
            lock,
            f"lock {lock.environment}",
            lambda current: current is None,
        )

    def read(self, environment: str) -> tuple[DeploymentLock, str] | None:
        path = self._backend._lock_path(environment)
        found = self._backend._read(path)
        if found is None:
            return None
        content, blob = found
        try:
            lock = DeploymentLock.from_dict(
                json.loads(content), source=self._backend._where(path)
            )
        except (ValueError, ConfigurationError):
            lock = _unknown_lock(
                environment,
                self._backend._changed_at(path),
                self._backend._lock_ttl,
            )
        return lock, blob

    def replace(self, lock: DeploymentLock, version: str) -> str | None:
        return self._write(
            lock,
            f"take over the expired lock of {lock.environment}",
            lambda current: current == version,
        )

    def delete(self, environment: str, version: str | None) -> bool:
        return self._backend._change(
            self._backend._lock_path(environment),
            None,
            message=(
                f"unlock {environment}"
                if version is not None
                else f"remove the lock of {environment}"
            ),
            allowed=lambda current: (
                current is not None and version in (None, current)
            ),
        )

    def _write(
        self,
        lock: DeploymentLock,
        message: str,
        allowed: Callable[[str | None], bool],
    ) -> str | None:
        """Write a lock where ``allowed`` lets it: its blob, or None."""
        blob = self._backend._store(_lock_json(lock))
        path = self._backend._lock_path(lock.environment)
        if self._backend._change(path, blob, message=message, allowed=allowed):
            return blob
        return None


def _detail(result: subprocess.CompletedProcess[bytes]) -> str:
    """What git said about a failure, on one line."""
    text = result.stderr.decode("utf-8", errors="replace").strip()
    return " ".join(text.split()) or f"exit code {result.returncode}"
