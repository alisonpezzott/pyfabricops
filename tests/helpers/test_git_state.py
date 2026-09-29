"""Tests for GitStateBackend, against a bare repository standing for a remote."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from pyfabricops.helpers.deployment_state import (
    DeploymentJournal,
    DeploymentLock,
    DeploymentState,
    JournalEntry,
    JournalingStateBackend,
    LockingStateBackend,
)
from pyfabricops.helpers.git_state import GitStateBackend
from pyfabricops.utils.exceptions import (
    ConfigurationError,
    DeploymentLockedError,
    RequestError,
)
from tests.helpers.git_repo import GitRepo

_MODULE = "pyfabricops.helpers.git_state"
_BRANCH = "pyfabricops/state"
_REF = f"refs/heads/{_BRANCH}"

Checkout = Callable[[], GitRepo]


@pytest.fixture()
def remote(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A bare repository, standing for the remote of the checkouts."""
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    path = tmp_path_factory.mktemp("remote") / "origin.git"
    subprocess.run(["git", "init", "--quiet", "--bare", str(path)], check=True)
    return path


@pytest.fixture()
def checkout(
    tmp_path_factory: pytest.TempPathFactory, remote: Path
) -> Checkout:
    """Make a checkout of the remote, as each pipeline run has its own."""

    def make() -> GitRepo:
        root = tmp_path_factory.mktemp("checkout")
        subprocess.run(["git", "init", "--quiet", str(root)], check=True)
        # The settings of init_git_repo and the remote, written at once: each
        # git process costs time, on Windows above all.
        with (root / ".git" / "config").open("a", encoding="utf-8") as file:
            file.write(
                "[user]\n\tname = Test\n\temail = test@example.com\n"
                "[commit]\n\tgpgsign = false\n"
                "[core]\n\tautocrlf = false\n"
                f'[remote "origin"]\n\turl = {remote.as_posix()}\n'
                "\tfetch = +refs/heads/*:refs/remotes/origin/*\n"
            )
        repo = GitRepo(root)
        repo.run("commit", "--quiet", "--allow-empty", "-m", "The code")
        return repo

    return make


def _remote_git(remote: Path, *args: str) -> str:
    """Run git in the remote and return its output."""
    result = subprocess.run(
        ["git", "--git-dir", str(remote), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _files(remote: Path) -> list[str]:
    """The files on the branch of the states, in the remote."""
    return _remote_git(remote, "ls-tree", "-r", "--name-only", _REF).split()


def _file(remote: Path, path: str) -> str:
    """A file on the branch of the states, in the remote."""
    return _remote_git(remote, "show", f"{_REF}:{path}")


def _messages(remote: Path) -> list[str]:
    """The subjects of the commits of the branch, newest first."""
    return _remote_git(remote, "log", "--format=%s", _REF).splitlines()


def _commit_to_branch(
    repo: GitRepo,
    path: str,
    content: str | None,
    *,
    date: datetime | None = None,
) -> None:
    """Change a file on the branch from a checkout, as a person would."""
    repo.run(
        "fetch", "--quiet", "origin", f"+{_REF}:refs/remotes/origin/{_BRANCH}"
    )
    repo.run(
        "checkout",
        "--quiet",
        "-B",
        "by-hand",
        f"refs/remotes/origin/{_BRANCH}",
    )
    file = repo.root / path
    if content is None:
        file.unlink()
    else:
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")
    repo.run("add", "--all")
    env = dict(os.environ)
    if date is not None:
        stamp = f"{int(date.timestamp())} +0000"
        env.update(GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    subprocess.run(
        ["git", "-C", str(repo.root), "commit", "--quiet", "-m", "By hand"],
        env=env,
        check=True,
    )
    repo.run("push", "--quiet", "origin", f"HEAD:{_REF}")


def _state(
    environment: str = "prod", commit: str = "a" * 40
) -> DeploymentState:
    return DeploymentState(
        environment=environment,
        workspace="Sales-PRD",
        workspace_id="00000000-0000-0000-0000-000000000001",
        source_commit=commit,
        commits={"Notebook": commit},
        deployed_at_utc="2026-09-28T12:00:00Z",
    )


def _backend(repo: GitRepo, **kwargs: Any) -> GitStateBackend:
    return GitStateBackend(repo.root, **kwargs)


def _other_lock(**changes: str) -> str:
    fields = {
        "environment": "prod",
        "lock_id": "other-run",
        "holder": "ci@runner",
        "acquired_at_utc": "2026-09-28T10:00:00Z",
        "expires_at_utc": "2999-01-01T00:00:00Z",
    }
    fields.update(changes)
    return json.dumps(fields)


def _lose_the_answer_of_the_first_push(
    monkeypatch: pytest.MonkeyPatch,
) -> list[str]:
    """Push for real, then answer the first push as a lost connection."""
    lost: list[str] = []
    push = GitStateBackend._push

    def pushed_but_lost(
        self: GitStateBackend, commit: str
    ) -> subprocess.CompletedProcess[bytes]:
        result = push(self, commit)
        if lost:
            return result
        lost.append(commit)
        return subprocess.CompletedProcess(
            result.args, 128, b"", b"fatal: the remote end hung up"
        )

    monkeypatch.setattr(GitStateBackend, "_push", pushed_but_lost)
    return lost


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------


def test_the_git_backend_locks_and_keeps_journals() -> None:
    """It keeps runs apart and resumes them, as the other backends do."""
    backend = GitStateBackend()

    assert isinstance(backend, LockingStateBackend)
    assert isinstance(backend, JournalingStateBackend)


def test_an_environment_without_a_branch_loads_none(
    checkout: Checkout,
) -> None:
    """No branch yet means no deployment recorded yet."""
    assert _backend(checkout()).load("prod") is None


def test_the_first_save_starts_an_orphan_branch_with_a_marker(
    checkout: Checkout, remote: Path
) -> None:
    """The branch shares no history with the code, and says what it is."""
    repo = checkout()
    backend = _backend(repo)
    backend.load("prod")

    backend.save("prod", _state())

    assert _files(remote) == [".pyfabricops-state", "README.md", "prod.json"]
    assert "pyfabricops keeps here" in _file(remote, "README.md")
    # One commit, with no parent: the branch starts from nothing.
    assert _remote_git(remote, "rev-list", "--parents", _REF).split() == [
        _remote_git(remote, "rev-parse", _REF)
    ]
    assert repo.run("rev-parse", "HEAD") not in _remote_git(
        remote, "rev-list", _REF
    )


def test_a_state_survives_a_round_trip_through_the_branch(
    checkout: Checkout,
) -> None:
    """Another checkout, as the next pipeline run, reads it back."""
    backend = _backend(checkout())
    backend.load("prod")

    backend.save("prod", _state())

    assert _backend(checkout()).load("prod") == _state()


def test_the_first_state_is_saved_only_where_there_is_none(
    checkout: Checkout,
) -> None:
    """load found nothing, so save must not overwrite another run's."""
    backend = _backend(checkout())
    backend.load("prod")
    _backend(checkout()).save("prod", _state(commit="c" * 40))

    with pytest.raises(RequestError, match="changed in .* since this run"):
        backend.save("prod", _state(commit="b" * 40))

    assert _backend(checkout()).load("prod") == _state(commit="c" * 40)


def test_a_state_is_saved_only_over_the_one_loaded(
    checkout: Checkout,
) -> None:
    """Another run saved in between: its state is left as it is."""
    first = _backend(checkout())
    first.load("prod")
    first.save("prod", _state())
    backend = _backend(checkout())
    backend.load("prod")
    first.save("prod", _state(commit="c" * 40))

    with pytest.raises(RequestError) as caught:
        backend.save("prod", _state(commit="b" * 40))

    assert str(caught.value) == (
        "Deployment state 'prod' changed in origin/pyfabricops/state:"
        "prod.json since this run read it, so it was not overwritten: "
        "another run deployed to the environment meanwhile."
    )
    assert _backend(checkout()).load("prod") == _state(commit="c" * 40)


def test_consecutive_saves_of_one_run_follow_their_own_version(
    checkout: Checkout,
) -> None:
    """Each save knows the blob it wrote."""
    backend = _backend(checkout())
    backend.load("prod")

    backend.save("prod", _state())
    backend.save("prod", _state(commit="b" * 40))

    assert _backend(checkout()).load("prod") == _state(commit="b" * 40)


def test_a_save_is_made_again_over_what_another_environment_wrote(
    checkout: Checkout, remote: Path
) -> None:
    """The branch moved, but not the file: the save goes on the new tip."""
    backend = _backend(checkout())
    backend.load("prod")
    other = _backend(checkout())
    other.load("dev")
    other.save("dev", _state("dev"))

    backend.save("prod", _state())

    assert _backend(checkout()).load("dev") == _state("dev")
    assert _backend(checkout()).load("prod") == _state()
    assert "dev.json" in _files(remote)


def test_a_save_whose_answer_was_lost_is_not_a_conflict(
    checkout: Checkout, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Looked at again, the branch holds the run's own write."""
    backend = _backend(checkout())
    backend.load("prod")
    lost = _lose_the_answer_of_the_first_push(monkeypatch)

    backend.save("prod", _state())

    assert len(lost) == 1
    assert _backend(checkout()).load("prod") == _state()


def test_a_save_without_a_load_writes_whatever_is_there(
    checkout: Checkout,
) -> None:
    """Nothing was read, so there is nothing to compare with."""
    _backend(checkout()).save("prod", _state())

    _backend(checkout()).save("prod", _state(commit="b" * 40))

    assert _backend(checkout()).load("prod") == _state(commit="b" * 40)


def test_a_push_that_fails_while_the_branch_stays_is_a_request_error(
    checkout: Checkout, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Such as an identity without the right to push: git says why."""
    sleep = MagicMock()
    monkeypatch.setattr(f"{_MODULE}.time.sleep", sleep)

    def refused(
        self: GitStateBackend, commit: str
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(
            ["git", "push"],
            1,
            b"",
            b"remote: TF401027: You need the Git 'GenericContribute' "
            b"permission to perform this action.\n"
            b"error: failed to push some refs",
        )

    monkeypatch.setattr(GitStateBackend, "_push", refused)

    with pytest.raises(RequestError) as caught:
        _backend(checkout()).save("prod", _state())

    assert str(caught.value) == (
        "git could not push to origin/pyfabricops/state: remote: TF401027: "
        "You need the Git 'GenericContribute' permission to perform this "
        "action. error: failed to push some refs"
    )
    assert sleep.call_count == 2


def test_the_pushes_skip_the_pre_push_hooks_of_the_checkout(
    checkout: Checkout,
) -> None:
    """Such hooks check code; a state push must not run or fail them."""
    repo = checkout()
    hook = repo.root / ".git" / "hooks" / "pre-push"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)

    _backend(repo).save("prod", _state())

    assert _backend(checkout()).load("prod") == _state()


def test_a_branch_the_backend_did_not_create_is_left_alone(
    checkout: Checkout, remote: Path
) -> None:
    """Without the marker, nothing is read from it or written to it."""
    repo = checkout()
    repo.run("push", "--quiet", "origin", f"HEAD:{_REF}")
    tip = _remote_git(remote, "rev-parse", _REF)

    with pytest.raises(ConfigurationError, match="has no .pyfabricops-state"):
        _backend(repo).load("prod")
    with pytest.raises(ConfigurationError, match="did not create it"):
        _backend(repo).save("prod", _state())

    assert _remote_git(remote, "rev-parse", _REF) == tip


def test_a_branch_of_code_named_by_mistake_is_never_written(
    checkout: Checkout, remote: Path
) -> None:
    """main is refused, as any branch without the marker."""
    repo = checkout()
    repo.run("push", "--quiet", "origin", "HEAD:refs/heads/main")
    tip = _remote_git(remote, "rev-parse", "refs/heads/main")

    with pytest.raises(ConfigurationError, match="origin/main has no"):
        _backend(repo, branch="main").save("prod", _state())

    assert _remote_git(remote, "rev-parse", "refs/heads/main") == tip


def test_the_checkout_is_left_as_it_was(checkout: Checkout) -> None:
    """Its HEAD, index, working tree and branches do not change."""
    repo = checkout()

    def look() -> tuple[str, ...]:
        return (
            repo.run("rev-parse", "HEAD"),
            repo.run("status", "--porcelain", "--ignored"),
            repo.run("ls-files", "--stage"),
            repo.run("for-each-ref", "--format=%(refname)", "refs/heads"),
        )

    before = look()
    backend = _backend(repo)
    with backend.lock("prod"):
        backend.load("prod")
        backend.save("prod", _state())
        backend.save_journal("prod", _journal())

    assert look() == before


def _items_folder(repo: GitRepo) -> Path:
    """The folder of the items, below the root, as a pipeline gives it."""
    folder = repo.root / "fabric-workspace"
    folder.mkdir()
    return folder


def test_a_folder_below_the_root_releases_the_lock_it_takes(
    checkout: Checkout, remote: Path
) -> None:
    """Each deployment of a run takes the lock after the one before."""
    items = _items_folder(checkout())
    backend = GitStateBackend(items)

    for _ in range(2):
        with backend.lock("prod"):
            backend.save("prod", _state())
            backend.save_journal("prod", _journal())
        assert "prod.lock" not in _files(remote)

    assert _files(remote) == [
        ".pyfabricops-state",
        "README.md",
        "prod.journal.json",
        "prod.json",
    ]


def test_a_folder_below_the_root_removes_a_lock_by_force(
    checkout: Checkout, remote: Path
) -> None:
    """force_unlock removes the lock from there too."""
    abandoned = _backend(checkout()).lock("prod")
    gone = abandoned.__enter__()

    removed = GitStateBackend(_items_folder(checkout())).force_unlock("prod")

    assert removed is not None and removed.lock_id == gone.lock_id
    assert "prod.lock" not in _files(remote)
    abandoned.__exit__(None, None, None)


def test_a_folder_below_the_root_dates_an_unreadable_lock(
    checkout: Checkout,
) -> None:
    """From its last change on the branch, so that it can expire."""
    _backend(checkout()).save("prod", _state())
    hours_ago = datetime.now(timezone.utc) - timedelta(hours=3)
    _commit_to_branch(checkout(), "prod.lock", "{", date=hours_ago)

    with GitStateBackend(_items_folder(checkout())).lock("prod") as held:
        assert held.holder != "an unknown run"


def test_a_change_git_did_not_make_is_never_pushed(
    checkout: Checkout, remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A commit that changes nothing would pass for the change."""
    _backend(checkout()).save("prod", _state())
    tip = _remote_git(remote, "rev-parse", _REF)
    monkeypatch.setattr(
        GitStateBackend, "_put", lambda self, path, blob, index: None
    )

    with pytest.raises(ConfigurationError, match="git did not write prod"):
        _backend(checkout()).save("prod", _state(commit="b" * 40))

    assert _remote_git(remote, "rev-parse", _REF) == tip


def test_each_commit_says_what_it_does_and_skips_ci(
    checkout: Checkout, remote: Path
) -> None:
    """[skip ci] keeps the pipelines of the repository from running."""
    backend = _backend(checkout())

    with backend.lock("prod"):
        backend.load("prod")
        backend.save("prod", _state())
        backend.save_journal("prod", _journal())

    assert _messages(remote) == [
        "chore(pyfabricops): unlock prod [skip ci]",
        "chore(pyfabricops): journal prod [skip ci]",
        "chore(pyfabricops): record the state of prod at aaaaaaaaaaaa "
        "[skip ci]",
        "chore(pyfabricops): lock prod [skip ci]",
    ]


def test_the_commits_are_made_by_the_identity_of_the_repository(
    checkout: Checkout, remote: Path
) -> None:
    """As any commit made in the checkout would be."""
    _backend(checkout()).save("prod", _state())

    author = _remote_git(remote, "log", "-1", "--format=%an <%ae>", _REF)
    assert author == "Test <test@example.com>"


def test_without_an_identity_the_commits_are_made_by_pyfabricops(
    tmp_path: Path, remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As on a CI runner, where git would refuse to commit."""
    empty = tmp_path / "gitconfig"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for role in ("AUTHOR", "COMMITTER"):
        for part in ("NAME", "EMAIL"):
            monkeypatch.delenv(f"GIT_{role}_{part}", raising=False)
    monkeypatch.delenv("EMAIL", raising=False)
    root = tmp_path / "runner"
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    subprocess.run(
        ["git", "-C", str(root), "remote", "add", "origin", str(remote)],
        check=True,
    )

    GitStateBackend(root).save("prod", _state())

    author = _remote_git(remote, "log", "-1", "--format=%an <%ae>|%cn", _REF)
    assert author == "pyfabricops <noreply@pyfabricops.invalid>|pyfabricops"


def test_a_folder_of_the_branch_holds_the_files(
    checkout: Checkout, remote: Path
) -> None:
    """So that projects of one repository keep their states apart."""
    backend = _backend(checkout(), folder="/sales/")

    with backend.lock("prod"):
        backend.save("prod", _state())
        backend.save_journal("prod", _journal())

    assert _files(remote) == [
        ".pyfabricops-state",
        "README.md",
        "sales/prod.journal.json",
        "sales/prod.json",
    ]
    assert _backend(checkout(), folder="sales").load("prod") == _state()


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"branch": ""}, "cannot name a branch"),
        ({"branch": "-x"}, "cannot name a branch"),
        ({"remote": "--upload-pack=x"}, "cannot name a remote"),
        ({"folder": "../outside"}, "cannot name a folder"),
        ({"folder": "sales/.git"}, "cannot name a folder"),
    ],
)
def test_names_git_would_refuse_are_configuration_errors(
    arguments: dict[str, Any], message: str
) -> None:
    """They are refused before git runs."""
    with pytest.raises(ConfigurationError, match=message):
        GitStateBackend(".", **arguments)


def test_a_branch_name_git_refuses_is_a_configuration_error(
    checkout: Checkout,
) -> None:
    """git itself checks the name, before any fetch."""
    with pytest.raises(ConfigurationError, match="'a..b' cannot name"):
        _backend(checkout(), branch="a..b").load("prod")


def test_a_missing_remote_is_a_configuration_error(
    checkout: Checkout,
) -> None:
    """The remote must be one the repository knows."""
    with pytest.raises(ConfigurationError, match="Remote 'upstream' not"):
        _backend(checkout(), remote="upstream").load("prod")


def test_a_folder_outside_a_repository_is_a_configuration_error(
    tmp_path: Path,
) -> None:
    """The states need a repository to live in."""
    if shutil.which("git") is None:
        pytest.skip("git is not installed")

    with pytest.raises(ConfigurationError, match="not inside a Git repo"):
        GitStateBackend(tmp_path / "nowhere").load("prod")


def test_a_remote_out_of_reach_is_a_request_error(
    git_repo: GitRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After the tries, git says why."""
    sleep = MagicMock()
    monkeypatch.setattr(f"{_MODULE}.time.sleep", sleep)
    git_repo.run("remote", "add", "origin", str(tmp_path / "gone.git"))

    with pytest.raises(RequestError, match="git could not fetch origin/"):
        GitStateBackend(git_repo.root).load("prod")

    assert sleep.call_count == 2


def test_a_remote_that_does_not_answer_is_a_request_error(
    checkout: Checkout, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fetch or a push has a timeout, so a run never hangs on it."""
    run = subprocess.run

    def hangs(command: list[str], **kwargs: Any) -> Any:
        if "fetch" in command:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return run(command, **kwargs)

    monkeypatch.setattr(f"{_MODULE}.subprocess.run", hangs)

    with pytest.raises(RequestError, match="did not finish within 120"):
        _backend(checkout()).load("prod")


def test_no_git_is_a_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The backend needs git on PATH."""
    monkeypatch.setattr(
        f"{_MODULE}.subprocess.run", MagicMock(side_effect=FileNotFoundError)
    )

    with pytest.raises(ConfigurationError, match="git was not found"):
        GitStateBackend().load("prod")


def test_a_state_of_another_environment_is_rejected(
    checkout: Checkout,
) -> None:
    """The environment inside the file must be the one asked for."""
    _backend(checkout()).save("prod", _state())
    repo = checkout()
    _commit_to_branch(repo, "dev.json", json.dumps(_state("prod").to_dict()))

    with pytest.raises(ConfigurationError, match="environment 'prod'"):
        _backend(repo).load("dev")


def test_an_invalid_state_file_is_a_configuration_error(
    checkout: Checkout,
) -> None:
    """What is on the branch is named in the error."""
    _backend(checkout()).save("prod", _state())
    repo = checkout()
    _commit_to_branch(repo, "prod.json", "{not json")

    with pytest.raises(ConfigurationError, match="prod.json is not valid"):
        _backend(repo).load("prod")


# ---------------------------------------------------------------------------
# Locks
# ---------------------------------------------------------------------------


def test_a_lock_is_created_only_where_there_is_none(
    checkout: Checkout, remote: Path
) -> None:
    """The lock file holds who and until when, and goes on release."""
    backend = _backend(checkout())

    with backend.lock("prod") as held:
        assert json.loads(_file(remote, "prod.lock")) == held.to_dict()

    assert "prod.lock" not in _files(remote)


def test_a_lock_another_run_holds_fails_at_once(checkout: Checkout) -> None:
    """The error says who holds it and until when."""
    with _backend(checkout()).lock("prod") as held:
        with pytest.raises(DeploymentLockedError) as caught:
            with _backend(checkout()).lock("prod"):
                pass

    assert f"held by {held.holder}" in str(caught.value)


def test_an_expired_lock_is_taken_over(
    checkout: Checkout, remote: Path
) -> None:
    """Only the expired lock read is replaced."""
    _backend(checkout()).save("prod", _state())
    _commit_to_branch(
        checkout(),
        "prod.lock",
        _other_lock(expires_at_utc="2026-09-28T11:00:00Z"),
    )

    with _backend(checkout()).lock("prod") as held:
        assert held.lock_id != "other-run"
        assert json.loads(_file(remote, "prod.lock")) == held.to_dict()

    assert (
        "chore(pyfabricops): take over the expired lock of prod [skip ci]"
        in _messages(remote)
    )


def test_a_lock_taken_over_first_by_another_run_stays_its(
    checkout: Checkout, remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two runs take over one expired lock: only one of them wins."""
    _backend(checkout()).save("prod", _state())
    person = checkout()
    _commit_to_branch(
        person, "prod.lock", _other_lock(expires_at_utc="2026-09-28T11:00:00Z")
    )
    push = GitStateBackend._push
    raced: list[bool] = []

    def another_run_first(
        self: GitStateBackend, commit: str
    ) -> subprocess.CompletedProcess[bytes]:
        if not raced:
            raced.append(True)
            _commit_to_branch(
                person, "prod.lock", _other_lock(lock_id="third-run")
            )
        return push(self, commit)

    monkeypatch.setattr(GitStateBackend, "_push", another_run_first)

    with pytest.raises(DeploymentLockedError):
        with _backend(checkout()).lock("prod"):
            pass

    assert json.loads(_file(remote, "prod.lock"))["lock_id"] == "third-run"


def test_a_lock_whose_answer_was_lost_is_known_as_this_runs(
    checkout: Checkout, remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Looked at again, the branch holds the run's own lock."""
    lost = _lose_the_answer_of_the_first_push(monkeypatch)

    with _backend(checkout()).lock("prod"):
        pass

    assert len(lost) == 1
    assert "prod.lock" not in _files(remote)


def test_a_run_that_died_cannot_remove_the_lock_that_replaced_its_own(
    checkout: Checkout, remote: Path
) -> None:
    """Its release finds another run's lock, and leaves it."""
    abandoned = _backend(checkout(), lock_ttl=-1).lock("prod")
    gone = abandoned.__enter__()

    with _backend(checkout()).lock("prod") as held:
        abandoned.__exit__(None, None, None)
        assert json.loads(_file(remote, "prod.lock")) == held.to_dict()

    assert held.lock_id != gone.lock_id


def test_force_unlock_removes_the_lock_whoever_holds_it(
    checkout: Checkout, remote: Path
) -> None:
    """It says whose lock it removed."""
    abandoned = _backend(checkout()).lock("prod")
    gone = abandoned.__enter__()

    removed = _backend(checkout()).force_unlock("prod")

    assert isinstance(removed, DeploymentLock)
    assert removed.lock_id == gone.lock_id
    assert _backend(checkout()).force_unlock("prod") is None
    assert _messages(remote)[0] == (
        "chore(pyfabricops): remove the lock of prod [skip ci]"
    )
    # The run that is gone finds no lock of its own to release.
    abandoned.__exit__(None, None, None)
    assert "prod.lock" not in _files(remote)


def test_a_lock_timeout_waits_on_git_too(
    checkout: Checkout, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other run releases it during the wait."""
    other = _backend(checkout()).lock("prod")
    other.__enter__()
    released = MagicMock(
        side_effect=lambda seconds: other.__exit__(None, None, None)
    )
    monkeypatch.setattr(
        "pyfabricops.helpers.deployment_state.time.sleep", released
    )

    with _backend(checkout(), lock_timeout=30).lock("prod") as held:
        assert held.holder

    released.assert_called_once()


def test_an_unreadable_lock_holds_until_its_ttl_from_its_last_change(
    checkout: Checkout,
) -> None:
    """Then another run may take it over."""
    _backend(checkout()).save("prod", _state())
    person = checkout()
    _commit_to_branch(person, "prod.lock", "")
    with pytest.raises(DeploymentLockedError, match="an unknown run"):
        with _backend(checkout()).lock("prod"):
            pass

    hours_ago = datetime.now(timezone.utc) - timedelta(hours=3)
    _commit_to_branch(person, "prod.lock", "{", date=hours_ago)
    with _backend(checkout()).lock("prod") as held:
        assert held.holder != "an unknown run"


# ---------------------------------------------------------------------------
# Journals
# ---------------------------------------------------------------------------


def _journal() -> DeploymentJournal:
    return DeploymentJournal(
        environment="prod",
        workspace="Sales-PRD",
        run_id="run-1",
        source_commit="a" * 40,
        started_at_utc="2026-09-28T10:00:00Z",
        entries=[
            JournalEntry(
                item_type="Notebook",
                display_name="A",
                outcome="updated",
                at_utc="2026-09-28T10:01:00Z",
                content_hash="h",
            )
        ],
    )


def test_a_journal_survives_a_round_trip_through_the_branch(
    checkout: Checkout, remote: Path
) -> None:
    """Next to the state, as <environment>.journal.json."""
    _backend(checkout()).save_journal("prod", _journal())

    assert _backend(checkout()).load_journal("prod") == _journal()
    assert "prod.journal.json" in _files(remote)


def test_no_journal_on_the_branch_loads_none(checkout: Checkout) -> None:
    """No run yet kept one."""
    assert _backend(checkout()).load_journal("prod") is None


def test_a_file_that_holds_no_journal_is_left_alone(
    checkout: Checkout,
) -> None:
    """A journal only saves work, so a bad one stops nothing."""
    _backend(checkout()).save("prod", _state())
    repo = checkout()
    _commit_to_branch(repo, "prod.journal.json", "{not json")

    assert _backend(repo).load_journal("prod") is None
