"""Tests for the deployment state in pyfabricops.helpers.deployment_state."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pyfabricops.helpers.deployment_plan import DeployedItem
from pyfabricops.helpers.deployment_state import (
    DeploymentLock,
    DeploymentState,
    DeploymentStateBackend,
    LocalJsonStateBackend,
    LockingStateBackend,
)
from pyfabricops.utils.exceptions import (
    ConfigurationError,
    DeploymentLockedError,
)

_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
_OLD = "a" * 40
_NEW = "b" * 40


def _state(environment: str = "prod", **changes: Any) -> DeploymentState:
    """A state of the Sales-PRD workspace, with some fields changed."""
    fields: dict[str, Any] = {
        "environment": environment,
        "workspace": "Sales-PRD",
        "workspace_id": _WORKSPACE_ID,
        "source_commit": _NEW,
        "commits": {"Notebook": _NEW, "Report": _OLD},
        "deployed_at_utc": "2026-09-23T12:30:00Z",
    }
    fields.update(changes)
    return DeploymentState(**fields)


@pytest.fixture()
def backend(tmp_path: Path) -> LocalJsonStateBackend:
    """A backend over an empty folder."""
    return LocalJsonStateBackend(tmp_path / "state")


# ---------------------------------------------------------------------------
# The state
# ---------------------------------------------------------------------------


def test_a_state_targets_its_workspace_by_name_or_id() -> None:
    """Either form of the workspace given to deploy_all_items matches."""
    state = _state()

    assert state.targets("Sales-PRD")
    assert state.targets(_WORKSPACE_ID)
    assert not state.targets("Sales-DEV")


def test_the_commits_and_items_cannot_be_changed() -> None:
    """A recorded deployment is a record, not a scratch pad."""
    state = _state()

    with pytest.raises(TypeError):
        state.commits["Notebook"] = _OLD  # type: ignore[index]
    with pytest.raises(TypeError):
        state.items[("Notebook", "Orders")] = DeployedItem("h")  # type: ignore[index]


# ---------------------------------------------------------------------------
# Local JSON files
# ---------------------------------------------------------------------------


def test_an_environment_without_a_state_loads_none(
    backend: LocalJsonStateBackend,
) -> None:
    """No file yet means no deployment recorded yet."""
    assert backend.load("prod") is None


def test_a_state_survives_a_round_trip(backend: LocalJsonStateBackend) -> None:
    """What is saved is what is loaded."""
    backend.save("prod", _state())

    assert backend.load("prod") == _state()


def test_saving_replaces_the_previous_state(
    backend: LocalJsonStateBackend,
) -> None:
    """Only the last successful deployment is kept."""
    backend.save("prod", _state(source_commit=_OLD))
    backend.save("prod", _state(source_commit=_NEW))

    loaded = backend.load("prod")
    assert loaded is not None
    assert loaded.source_commit == _NEW


def test_the_file_is_readable_json(
    tmp_path: Path, backend: LocalJsonStateBackend
) -> None:
    """One sorted, indented JSON file per environment, nothing else."""
    backend.save("prod", _state())

    folder = tmp_path / "state"
    assert [p.name for p in folder.iterdir()] == ["prod.json"]
    content = (folder / "prod.json").read_text(encoding="utf-8")
    assert content.endswith("}\n")
    data = json.loads(content)
    assert list(data) == sorted(data)
    assert data["schema_version"] == 1
    assert data["commits"] == {"Notebook": _NEW, "Report": _OLD}


def test_unsafe_characters_do_not_reach_the_file_name(
    tmp_path: Path, backend: LocalJsonStateBackend
) -> None:
    """Names become safe file names inside the folder, never outside it."""
    backend.save("Sales (PRD)", _state("Sales (PRD)"))
    backend.save("../escape", _state("../escape"))

    assert sorted(p.name for p in (tmp_path / "state").iterdir()) == [
        "Sales-PRD.json",
        "escape.json",
    ]


def test_two_environments_sharing_a_file_are_caught(
    backend: LocalJsonStateBackend,
) -> None:
    """The file keeps the real name, so a clash is not a silent mix-up."""
    backend.save("Sales (PRD)", _state("Sales (PRD)"))

    with pytest.raises(ConfigurationError, match="holds the state of"):
        backend.load("Sales-PRD")


def test_a_state_is_saved_only_under_its_own_environment(
    backend: LocalJsonStateBackend,
) -> None:
    """Saving the prod state as dev is a mistake, not a copy."""
    with pytest.raises(ConfigurationError, match="Cannot save the state"):
        backend.save("dev", _state("prod"))


def test_a_name_that_cannot_name_a_file_is_rejected(
    backend: LocalJsonStateBackend,
) -> None:
    """Nothing is left of '...' once unsafe characters go."""
    with pytest.raises(ConfigurationError, match="cannot name"):
        backend.load("...")


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("not json", "is not valid JSON"),
        ("[]", "is not a deployment state"),
        ('{"schema_version": 2}', "schema version 2"),
        ('{"schema_version": 1, "environment": "prod"}', "no valid workspace"),
    ],
)
def test_an_invalid_state_file_is_a_configuration_error(
    tmp_path: Path, content: str, message: str
) -> None:
    """A broken or newer state stops the run instead of being guessed at."""
    folder = tmp_path / "state"
    folder.mkdir()
    (folder / "prod.json").write_text(content, encoding="utf-8")

    with pytest.raises(ConfigurationError, match=message):
        LocalJsonStateBackend(folder).load("prod")


def test_what_was_sent_for_each_item_survives_a_round_trip(
    backend: LocalJsonStateBackend,
) -> None:
    """Per-item hashes and folders are kept, keyed Type.DisplayName."""
    state = _state(
        items={
            ("Notebook", "Orders"): DeployedItem("h1", "Sales"),
            ("Report", "Sales.Summary"): DeployedItem("h2"),
        }
    )

    backend.save("prod", state)

    assert backend.load("prod") == state
    assert set(state.to_dict()["items"]) == {
        "Notebook.Orders",
        "Report.Sales.Summary",
    }


def test_a_state_without_items_still_loads(tmp_path: Path) -> None:
    """A state written before per-item records has none, not an error."""
    data = _state().to_dict()
    del data["items"]
    folder = tmp_path / "state"
    folder.mkdir()
    (folder / "prod.json").write_text(json.dumps(data), encoding="utf-8")

    loaded = LocalJsonStateBackend(folder).load("prod")

    assert loaded is not None
    assert dict(loaded.items) == {}


def test_an_item_record_without_a_hash_is_rejected(tmp_path: Path) -> None:
    """A record that cannot be compared is not guessed at."""
    data = _state().to_dict()
    data["items"] = {
        "Notebook.Orders": {"item_type": "Notebook", "display_name": "Orders"}
    }
    folder = tmp_path / "state"
    folder.mkdir()
    (folder / "prod.json").write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="no valid items"):
        LocalJsonStateBackend(folder).load("prod")


def test_commits_must_map_types_to_commit_ids(tmp_path: Path) -> None:
    """A commit that is not a string is not a baseline."""
    data = _state().to_dict()
    data["commits"] = {"Notebook": 7}
    folder = tmp_path / "state"
    folder.mkdir()
    (folder / "prod.json").write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="no valid commits"):
        LocalJsonStateBackend(folder).load("prod")


# ---------------------------------------------------------------------------
# Locks
# ---------------------------------------------------------------------------


def _lock_file(backend: LocalJsonStateBackend, environment: str) -> Path:
    """Where the backend keeps the lock of an environment."""
    return backend._lock_path(environment)


def _write_lock(path: Path, **changes: str) -> DeploymentLock:
    """Write a lock of another run, with some fields changed."""
    fields = {
        "environment": "prod",
        "lock_id": "other-run",
        "holder": "ci@runner (GitHub Actions run 42)",
        "acquired_at_utc": "2026-09-25T10:00:00Z",
        "expires_at_utc": "2999-01-01T00:00:00Z",
    }
    fields.update(changes)
    lock = DeploymentLock(**fields)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(lock.to_dict()), encoding="utf-8")
    return lock


def test_the_local_backend_locks() -> None:
    """Both kinds are state backends; only a locking one has a lock."""

    class LoadSaveOnly:
        def load(self, environment: str) -> DeploymentState | None:
            return None

        def save(self, environment: str, state: DeploymentState) -> None:
            pass

    plain: DeploymentStateBackend = LoadSaveOnly()

    assert isinstance(LocalJsonStateBackend("state"), LockingStateBackend)
    assert not isinstance(plain, LockingStateBackend)


def test_a_lock_is_held_for_the_block_and_released_after(
    backend: LocalJsonStateBackend,
) -> None:
    """The lock file says who holds it, and goes when the block ends."""
    path = _lock_file(backend, "prod")

    with backend.lock("prod") as held:
        recorded = json.loads(path.read_text(encoding="utf-8"))
        assert recorded == held.to_dict()
        assert held.environment == "prod"
        assert "@" in held.holder

    assert not path.exists()


def test_the_holder_names_the_ci_run(
    backend: LocalJsonStateBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lock taken in a pipeline says which run took it."""
    monkeypatch.setenv("GITHUB_RUN_ID", "1234")

    with backend.lock("prod") as held:
        assert held.holder.endswith("(GitHub Actions run 1234)")


def test_a_lock_is_released_when_the_block_fails(
    backend: LocalJsonStateBackend,
) -> None:
    """A failed deployment does not leave the environment locked."""
    with pytest.raises(RuntimeError), backend.lock("prod"):
        raise RuntimeError("the deployment failed")

    assert not _lock_file(backend, "prod").exists()


def test_a_lock_another_run_holds_fails_at_once(
    backend: LocalJsonStateBackend,
) -> None:
    """The error says who holds it, until when, and what to do."""
    _write_lock(_lock_file(backend, "prod"))

    with pytest.raises(DeploymentLockedError) as caught:
        with backend.lock("prod"):
            pass

    assert str(caught.value) == (
        "Deployment state 'prod' is locked, held by ci@runner (GitHub "
        "Actions run 42) since 2026-09-25T10:00:00Z, until "
        "2999-01-01T00:00:00Z. Wait for that run to finish; if it is gone, "
        "call force_unlock('prod') on the state backend."
    )


def test_a_lock_timeout_waits_for_the_other_run(tmp_path: Path) -> None:
    """With lock_timeout, the lock is taken once the other run releases it."""
    backend = LocalJsonStateBackend(tmp_path / "state", lock_timeout=60)
    path = _lock_file(backend, "prod")
    _write_lock(path)

    with (
        patch(
            "pyfabricops.helpers.deployment_state.time.sleep",
            side_effect=lambda seconds: path.unlink(),
        ) as sleep,
        backend.lock("prod") as held,
    ):
        assert held.lock_id != "other-run"

    sleep.assert_called_once()


def test_a_lock_timeout_gives_up_in_the_end(tmp_path: Path) -> None:
    """The other run never releases it: the error comes after the wait."""
    backend = LocalJsonStateBackend(tmp_path / "state", lock_timeout=10)
    _write_lock(_lock_file(backend, "prod"))
    clock = iter([0.0, 5.0, 11.0])

    with (
        patch(
            "pyfabricops.helpers.deployment_state.time.monotonic",
            side_effect=lambda: next(clock),
        ),
        patch("pyfabricops.helpers.deployment_state.time.sleep") as sleep,
        pytest.raises(DeploymentLockedError),
    ):
        with backend.lock("prod"):
            pass

    sleep.assert_called_once_with(5.0)


def test_an_expired_lock_is_taken_over(
    backend: LocalJsonStateBackend,
) -> None:
    """Its run never released it; after its validity it no longer counts."""
    _write_lock(
        _lock_file(backend, "prod"), expires_at_utc="2026-09-25T12:00:00Z"
    )

    with backend.lock("prod") as held:
        assert held.lock_id != "other-run"

    assert not _lock_file(backend, "prod").exists()


def test_a_lock_expires_after_its_ttl(tmp_path: Path) -> None:
    """lock_ttl sets how long a lock holds unless released."""
    backend = LocalJsonStateBackend(tmp_path / "state", lock_ttl=60)

    with backend.lock("prod") as held:
        pass

    assert not held.expired
    assert DeploymentLock.new("prod", -1).expired


def test_an_unreadable_lock_counts_as_held_until_its_ttl(
    tmp_path: Path,
) -> None:
    """A lock file caught while written is a lock, not garbage."""
    backend = LocalJsonStateBackend(tmp_path / "state", lock_ttl=60)
    path = _lock_file(backend, "prod")
    path.parent.mkdir(parents=True)
    path.write_text("", encoding="utf-8")

    with pytest.raises(DeploymentLockedError, match="an unknown run"):
        with backend.lock("prod"):
            pass

    hours_ago = time.time() - 2 * 60 * 60
    os.utime(path, (hours_ago, hours_ago))
    with backend.lock("prod") as held:
        assert held.holder != "an unknown run"


def test_a_lock_taken_over_meanwhile_is_left_alone(
    backend: LocalJsonStateBackend,
) -> None:
    """The release removes only this run's lock."""
    path = _lock_file(backend, "prod")

    with backend.lock("prod"):
        other = _write_lock(path)

    assert json.loads(path.read_text(encoding="utf-8")) == other.to_dict()


def test_force_unlock_removes_the_lock_whoever_holds_it(
    backend: LocalJsonStateBackend,
) -> None:
    """For a run that is gone; it says whose lock it was."""
    other = _write_lock(_lock_file(backend, "prod"))

    assert backend.force_unlock("prod") == other
    assert backend.force_unlock("prod") is None
    with backend.lock("prod"):
        pass


def test_each_environment_has_its_own_lock(
    backend: LocalJsonStateBackend,
) -> None:
    """Deploying to prod does not hold back dev."""
    with backend.lock("prod"), backend.lock("dev"):
        assert _lock_file(backend, "prod") != _lock_file(backend, "dev")


def test_a_lock_file_that_is_no_lock_is_rejected() -> None:
    """Every field must be there, and the times must be UTC times."""
    with pytest.raises(ConfigurationError, match="not a deployment lock"):
        DeploymentLock.from_dict(
            {
                "environment": "prod",
                "lock_id": "x",
                "holder": "me",
                "acquired_at_utc": "yesterday",
                "expires_at_utc": "2999-01-01T00:00:00Z",
            },
            source="prod.lock",
        )
