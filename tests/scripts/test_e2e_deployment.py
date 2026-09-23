"""Offline run of scripts/e2e_deployment.py against an in-memory workspace."""

from __future__ import annotations

import base64
import importlib.util
import json
import shutil
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import patch

import pytest

from pyfabricops.api.api import ApiResult

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "e2e_deployment.py"
_ENGINE = "pyfabricops.helpers.deployment"
_WORKSPACE_ID = "00000000-0000-0000-0000-0000000000e2"


def _load_script() -> ModuleType:
    """Import the script as a module, as it is not in a package."""
    spec = importlib.util.spec_from_file_location("e2e_deployment", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Dataclasses look their module up in sys.modules while it loads.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeWorkspace:
    """A workspace in memory: items, folders, and Fabric's pipeline check."""

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self.folders: dict[str, dict[str, Any]] = {}

    def resolve_workspace(self, workspace: str) -> str:
        return _WORKSPACE_ID

    def list_items(
        self, workspace: str, *, df: bool | None = True
    ) -> list[dict[str, Any]]:
        return [
            {key: value for key, value in item.items() if key != "definition"}
            for item in self.items.values()
        ]

    def list_folders(
        self, workspace: str, *, df: bool | None = True
    ) -> list[dict[str, Any]]:
        return list(self.folders.values())

    def create_folder(
        self,
        workspace: str,
        name: str,
        *,
        parent_folder: str | None = None,
        df: bool | None = True,
    ) -> dict[str, Any]:
        folder_id = str(uuid.uuid4())
        folder: dict[str, Any] = {
            "id": folder_id,
            "displayName": name,
            "parentFolderId": parent_folder,
        }
        self.folders[folder_id] = folder
        return folder

    def create_item(
        self,
        workspace_id: str,
        *,
        display_name: str,
        item_type: str,
        item_definition: dict[str, Any],
        folder_id: str | None,
    ) -> ApiResult:
        rejected = self._reject(item_type, item_definition)
        if rejected is not None:
            return rejected
        item_id = str(uuid.uuid4())
        self.items[item_id] = {
            "id": item_id,
            "type": item_type,
            "displayName": display_name,
            "folderId": folder_id,
            "definition": item_definition,
        }
        return ApiResult(True, 201, data={"id": item_id})

    def update_definition(
        self, workspace_id: str, item_id: str, item_definition: dict[str, Any]
    ) -> ApiResult:
        item = self.items[item_id]
        rejected = self._reject(item["type"], item_definition)
        if rejected is not None:
            return rejected
        item["definition"] = item_definition
        return ApiResult(True, 200)

    def move_item(
        self, workspace_id: str, item_id: str, folder_id: str
    ) -> ApiResult:
        self.items[item_id]["folderId"] = folder_id
        return ApiResult(True, 200)

    def delete_item(self, workspace: str, item: str) -> None:
        self.items.pop(item, None)

    def delete_folder(self, workspace: str, folder: str) -> None:
        self.folders.pop(folder, None)

    @staticmethod
    def _reject(
        item_type: str, definition: dict[str, Any]
    ) -> ApiResult | None:
        """Refuse a pipeline whose content is not JSON, as Fabric does."""
        if item_type != "DataPipeline":
            return None
        for part in definition["parts"]:
            if part["path"] == "pipeline-content.json":
                try:
                    json.loads(base64.b64decode(part["payload"]))
                except ValueError:
                    error = {
                        "errorCode": "InvalidDefinition",
                        "message": "pipeline-content.json is not valid JSON.",
                    }
                    return ApiResult(False, 400, error=json.dumps(error))
        return None


@pytest.fixture()
def fake(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[FakeWorkspace]:
    """Stand an in-memory workspace in for Fabric, wherever it is called."""
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    for name in ("FAB_CLIENT_ID", "FAB_CLIENT_SECRET", "FAB_TENANT_ID"):
        monkeypatch.setenv(name, "offline-test")

    def _copy_to_staging(path: str) -> str:
        staging = tmp_path / "stg" / Path(path).name
        if staging.exists():
            shutil.rmtree(staging)
        shutil.copytree(path, staging)
        return str(staging)

    workspace = FakeWorkspace()
    with (
        patch("pyfabricops.clear_token_cache"),
        patch("pyfabricops.set_auth_provider"),
        patch("pyfabricops.setup_logging"),
        patch("pyfabricops.copy_to_staging", side_effect=_copy_to_staging),
        patch(
            "pyfabricops.resolve_workspace",
            side_effect=workspace.resolve_workspace,
        ),
        patch("pyfabricops.list_items", side_effect=workspace.list_items),
        patch("pyfabricops.list_folders", side_effect=workspace.list_folders),
        patch("pyfabricops.delete_item", side_effect=workspace.delete_item),
        patch(
            "pyfabricops.delete_folder", side_effect=workspace.delete_folder
        ),
        patch(
            f"{_ENGINE}.resolve_workspace",
            side_effect=workspace.resolve_workspace,
        ),
        patch(f"{_ENGINE}.list_items", side_effect=workspace.list_items),
        patch(f"{_ENGINE}.list_folders", side_effect=workspace.list_folders),
        patch(f"{_ENGINE}.create_folder", side_effect=workspace.create_folder),
        patch(
            f"{_ENGINE}._request_create_item",
            side_effect=workspace.create_item,
        ),
        patch(
            f"{_ENGINE}._request_update_item_definition",
            side_effect=workspace.update_definition,
        ),
        patch(
            f"{_ENGINE}._request_move_item", side_effect=workspace.move_item
        ),
    ):
        yield workspace


def _run_script(tmp_path: Path, *args: str) -> int:
    code: int = _load_script().main(
        ["--env-file", str(tmp_path / "no.env"), *args]
    )
    return code


def test_every_step_passes_and_the_run_cleans_up(
    fake: FakeWorkspace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Against a workspace that behaves, all eight steps pass."""
    code = _run_script(tmp_path, "--workspace", "Sandbox")

    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err
    assert "All steps passed." in captured.out
    assert "[FAIL]" not in captured.err
    assert fake.items == {}
    assert fake.folders == {}
    assert not (tmp_path / "stg").exists(), "the staging copy is left"


def test_a_workspace_with_other_items_is_refused(
    fake: FakeWorkspace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The script never runs next to items it did not create."""
    fake.items["sales"] = {
        "id": "sales",
        "type": "Report",
        "displayName": "Sales",
        "folderId": None,
    }

    code = _run_script(tmp_path, "--workspace", "Sandbox")

    assert code == 1
    assert "Sales.Report" in capsys.readouterr().err
    assert list(fake.items) == ["sales"]


def test_a_token_cached_for_another_identity_is_dropped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The cache is cleared before the service principal authenticates."""
    for name in ("FAB_CLIENT_ID", "FAB_CLIENT_SECRET", "FAB_TENANT_ID"):
        monkeypatch.setenv(name, "offline-test")
    calls: list[str] = []

    with (
        patch(
            "pyfabricops.clear_token_cache",
            side_effect=lambda: calls.append("clear"),
        ),
        patch(
            "pyfabricops.set_auth_provider",
            side_effect=lambda *args, **kwargs: calls.append("provider"),
        ),
    ):
        _load_script()._authenticate(str(tmp_path / "no.env"))

    assert calls == ["clear", "provider"]


def test_nothing_runs_without_an_explicit_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Credentials alone, as in CI, do not start the script."""
    monkeypatch.delenv("PYFABRICOPS_E2E_WORKSPACE", raising=False)

    assert _run_script(tmp_path) == 2
