"""Offline run of scripts/e2e_state.py against an in-memory workspace."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import patch

import pytest

from tests.helpers.test_onelake_state import FakeOneLake
from tests.scripts.test_e2e_deployment import FakeWorkspace

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "e2e_state.py"
_ENGINE = "pyfabricops.helpers.deployment"
_ONELAKE = "pyfabricops.helpers.onelake_state"


def _load_script() -> ModuleType:
    """Import the script as a module, as it is not in a package."""
    spec = importlib.util.spec_from_file_location("e2e_state", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Dataclasses look their module up in sys.modules while it loads.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeSandbox(FakeWorkspace):
    """A workspace in memory that can also hold a lakehouse of states."""

    def create_lakehouse(
        self, workspace: str, display_name: str, *, df: bool | None = True
    ) -> None:
        self.create_by_hand(
            workspace, display_name, {"parts": []}, item_type="Lakehouse"
        )

    def resolve_lakehouse(self, workspace: str, lakehouse: str) -> str | None:
        for item in self.items.values():
            if (item["type"], item["displayName"]) == ("Lakehouse", lakehouse):
                return str(item["id"])
        return None


@pytest.fixture()
def sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[FakeSandbox, FakeOneLake]]:
    """Stand an in-memory workspace and OneLake in for Fabric."""
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    for name in ("FAB_CLIENT_ID", "FAB_CLIENT_SECRET", "FAB_TENANT_ID"):
        monkeypatch.setenv(name, "offline-test")

    workspace, onelake = FakeSandbox(), FakeOneLake()
    answers: dict[str, Callable[..., Any]] = {
        "pyfabricops.resolve_workspace": workspace.resolve_workspace,
        "pyfabricops.list_items": workspace.list_items,
        "pyfabricops.delete_item": workspace.delete_item,
        "pyfabricops.create_lakehouse": workspace.create_lakehouse,
        f"{_ENGINE}.resolve_workspace": workspace.resolve_workspace,
        f"{_ENGINE}.list_items": workspace.list_items,
        f"{_ENGINE}.list_folders": workspace.list_folders,
        f"{_ENGINE}.create_folder": workspace.create_folder,
        f"{_ENGINE}._request_create_item": workspace.create_item,
        f"{_ENGINE}._request_update_item_definition": (
            workspace.update_definition
        ),
        f"{_ENGINE}._request_move_item": workspace.move_item,
        f"{_ONELAKE}._send": onelake.send,
        f"{_ONELAKE}.resolve_workspace": workspace.resolve_workspace,
        f"{_ONELAKE}.resolve_lakehouse": workspace.resolve_lakehouse,
    }
    with ExitStack() as stack:
        for target in (
            "pyfabricops.clear_token_cache",
            "pyfabricops.set_auth_provider",
            "pyfabricops.setup_logging",
        ):
            stack.enter_context(patch(target))
        stack.enter_context(
            patch(
                f"{_ONELAKE}._get_token",
                return_value={"access_token": "offline"},
            )
        )
        for target, answer in answers.items():
            stack.enter_context(patch(target, side_effect=answer))
        yield workspace, onelake


def _run_script(tmp_path: Path, *args: str) -> int:
    code: int = _load_script().main(
        ["--env-file", str(tmp_path / "no.env"), *args]
    )
    return code


def test_every_step_passes_and_the_run_cleans_up(
    sandbox: tuple[FakeSandbox, FakeOneLake],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Against a workspace and a OneLake that behave, every step passes."""
    workspace, onelake = sandbox

    code = _run_script(tmp_path, "--workspace", "Sandbox")

    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err
    assert "All steps passed." in captured.out
    assert workspace.items == {}
    assert not [url for url in onelake.blobs if url.endswith(".lock")]
    assert sorted(url.rsplit("/", 1)[1] for url in onelake.blobs) == [
        "deploy.journal.json",
        "deploy.json",
        "e2e.json",
    ]


def test_a_workspace_with_other_items_is_refused(
    sandbox: tuple[FakeSandbox, FakeOneLake],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The script never runs next to items it did not create."""
    workspace, _ = sandbox
    workspace.create_lakehouse("Sandbox", "Sales")

    code = _run_script(tmp_path, "--workspace", "Sandbox")

    assert code == 1
    assert "holds items this script did not create" in capsys.readouterr().err
    assert [item["displayName"] for item in workspace.items.values()] == [
        "Sales"
    ]


def test_nothing_runs_without_an_explicit_workspace(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A CI job with Fabric credentials never starts it by accident."""
    monkeypatch.delenv("PYFABRICOPS_E2E_WORKSPACE", raising=False)

    assert _run_script(tmp_path) == 2
    assert "Pass --workspace" in capsys.readouterr().err
