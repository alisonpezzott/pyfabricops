"""Offline run of scripts/e2e_deployment.py against an in-memory workspace."""

from __future__ import annotations

import base64
import importlib.util
import json
import shutil
import sys
import uuid
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import patch

import pytest

import pyfabricops
from pyfabricops.api.api import ApiResult

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "e2e_deployment.py"
_PACKAGE = Path(pyfabricops.__file__).resolve().parent
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
        self, workspace_id: str, item_id: str, folder_id: str | None
    ) -> ApiResult:
        self.items[item_id]["folderId"] = folder_id
        return ApiResult(True, 200)

    def delete_item(self, workspace: str, item: str) -> None:
        self.items.pop(item, None)

    def request_delete(self, workspace_id: str, item_id: str) -> ApiResult:
        if self.items.pop(item_id, None) is None:
            body = {"errorCode": "ItemNotFound", "message": "Not found."}
            return ApiResult(False, 404, error=json.dumps(body))
        return ApiResult(True, 200)

    def delete_folder(self, workspace: str, folder: str) -> None:
        self.folders.pop(folder, None)

    def get_item_definition(
        self, workspace: str, item: str, *, format: str | None = None
    ) -> dict[str, Any] | None:
        """Answer as the getDefinition API does."""
        stored = self.items.get(item)
        return None if stored is None else {"definition": stored["definition"]}

    def read_definition(self, workspace_id: str, item_id: str) -> ApiResult:
        """What the engine gets when it reads a definition."""
        return ApiResult(
            True, 200, data=self.get_item_definition(workspace_id, item_id)
        )

    # What a person does by hand, through the functions pyfabricops exports.

    def edit_item(
        self,
        workspace: str,
        item: str,
        item_definition: dict[str, Any],
        df: bool | None = True,
    ) -> None:
        self.items[item]["definition"] = item_definition

    def move_by_hand(
        self, workspace: str, item: str, target_folder: str | None = None
    ) -> None:
        self.items[item]["folderId"] = target_folder

    def create_by_hand(
        self,
        workspace: str,
        display_name: str,
        item_definition: dict[str, Any],
        *,
        item_type: str | None = None,
        df: bool | None = True,
    ) -> None:
        self.create_item(
            workspace,
            display_name=display_name,
            item_type=str(item_type),
            item_definition=item_definition,
            folder_id=None,
        )

    @staticmethod
    def _reject(
        item_type: str, definition: dict[str, Any]
    ) -> ApiResult | None:
        """
        Refuse what Fabric refuses: a pipeline whose content is not JSON,
        and a report that points to its semantic model by path.
        """
        for part in definition["parts"]:
            where = (item_type, part["path"])
            content = base64.b64decode(part["payload"]).decode(
                errors="replace"
            )
            if where == ("DataPipeline", "pipeline-content.json"):
                try:
                    json.loads(content)
                    continue
                except ValueError:
                    message = "pipeline-content.json is not valid JSON."
            elif (
                where == ("Report", "definition.pbir") and "byPath" in content
            ):
                message = (
                    "Fabric REST API only supports byConnection references."
                )
            else:
                continue
            error = {"errorCode": "InvalidDefinition", "message": message}
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

    workspace = FakeWorkspace()
    # Where the script and the engine reach Fabric, and what answers there.
    answers: dict[str, Callable[..., Any]] = {
        "pyfabricops.resolve_workspace": workspace.resolve_workspace,
        "pyfabricops.list_items": workspace.list_items,
        "pyfabricops.list_folders": workspace.list_folders,
        "pyfabricops.delete_item": workspace.delete_item,
        "pyfabricops.delete_folder": workspace.delete_folder,
        "pyfabricops.get_item_definition": workspace.get_item_definition,
        "pyfabricops.update_item_definition": workspace.edit_item,
        "pyfabricops.move_item": workspace.move_by_hand,
        "pyfabricops.create_item": workspace.create_by_hand,
        f"{_ENGINE}._request_item_definition": workspace.read_definition,
        f"{_ENGINE}.resolve_workspace": workspace.resolve_workspace,
        f"{_ENGINE}.list_items": workspace.list_items,
        f"{_ENGINE}.list_folders": workspace.list_folders,
        f"{_ENGINE}.create_folder": workspace.create_folder,
        f"{_ENGINE}._request_create_item": workspace.create_item,
        f"{_ENGINE}._request_update_item_definition": (
            workspace.update_definition
        ),
        f"{_ENGINE}._request_move_item": workspace.move_item,
        f"{_ENGINE}._request_delete_item": workspace.request_delete,
    }
    with ExitStack() as stack:
        for target in (
            "pyfabricops.clear_token_cache",
            "pyfabricops.set_auth_provider",
            "pyfabricops.setup_logging",
        ):
            stack.enter_context(patch(target))
        for target, answer in answers.items():
            stack.enter_context(patch(target, side_effect=answer))
        yield workspace


def _listing(folder: Path) -> list[str]:
    """Every path under a folder, to tell whether something was written."""
    if not folder.exists():
        return []
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*"))


def _run_script(tmp_path: Path, *args: str) -> int:
    code: int = _load_script().main(
        ["--env-file", str(tmp_path / "no.env"), *args]
    )
    return code


def test_every_step_passes_and_the_run_cleans_up(
    fake: FakeWorkspace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Against a workspace that behaves, every step passes."""
    package_staging = _PACKAGE / "utils" / "_stg"
    before = _listing(package_staging)

    code = _run_script(tmp_path, "--workspace", "Sandbox")

    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err
    assert "All steps passed." in captured.out
    assert "[FAIL]" not in captured.err
    assert fake.items == {}
    assert fake.folders == {}
    assert _listing(package_staging) == before, "the run staged in the package"


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
