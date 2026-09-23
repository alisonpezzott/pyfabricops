"""Tests for the deployment state in pyfabricops.helpers.deployment_state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pyfabricops.helpers.deployment_state import (
    DeploymentState,
    LocalJsonStateBackend,
)
from pyfabricops.utils.exceptions import ConfigurationError

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


def test_the_commits_cannot_be_changed() -> None:
    """A recorded deployment is a record, not a scratch pad."""
    state = _state()

    with pytest.raises(TypeError):
        state.commits["Notebook"] = _OLD  # type: ignore[index]


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


def test_commits_must_map_types_to_commit_ids(tmp_path: Path) -> None:
    """A commit that is not a string is not a baseline."""
    data = _state().to_dict()
    data["commits"] = {"Notebook": 7}
    folder = tmp_path / "state"
    folder.mkdir()
    (folder / "prod.json").write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="no valid commits"):
        LocalJsonStateBackend(folder).load("prod")
