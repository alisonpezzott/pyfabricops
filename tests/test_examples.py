"""Tests for the examples folder: the sample, and the script that deploys it."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

import pyfabricops as pf
from pyfabricops.helpers.deployment_plan import DeploymentPlan
from pyfabricops.helpers.items import plan_all_items

_EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
_EXAMPLE = _EXAMPLES / "Adventure-Works-LT"
_SAMPLE = _EXAMPLE / "fabric-workspace"
_ENGINE = "pyfabricops.helpers.deployment"
_GUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
_EMPTY = "00000000-0000-0000-0000-000000000000"
# The empty GUID, which Fabric writes for the workspace of an item of the
# same workspace, and the IDs made up for the sample (see its README).
_MADE_UP = re.compile(rf"{_EMPTY}|00000000-0000-4000-8000-\d{{12}}")
_DEV = "00000000-0000-4000-8000-000000000001"
_PRD = "99999999-0000-4000-8000-000000000001"
_ARGS = ["--source-workspace", "DEV", "--workspace", "PRD"]
_ARGS += ["--value-set", "Production"]

# The source distribution leaves the examples out.
pytestmark = pytest.mark.skipif(
    not _SAMPLE.is_dir(), reason="examples/ is not in this copy"
)


@pytest.fixture()
def empty_workspace() -> Iterator[None]:
    """A workspace that holds nothing yet."""
    with (
        patch(f"{_ENGINE}.resolve_workspace", return_value=_PRD),
        patch(f"{_ENGINE}.list_items", return_value=[]),
        patch(f"{_ENGINE}.list_folders", return_value=[]),
    ):
        yield


def _plan() -> DeploymentPlan:
    return plan_all_items("PRD", str(_SAMPLE), start_path=str(_SAMPLE))


def test_the_engine_creates_the_sample_in_dependency_order(
    empty_workspace: None,
) -> None:
    """The item types in the order of DEPLOY_ORDER."""
    assert [
        (a.action.value, a.item_type, a.display_name) for a in _plan().actions
    ] == [
        ("CREATE", "VariableLibrary", "variables"),
        ("CREATE", "Lakehouse", "bronze"),
        ("CREATE", "Lakehouse", "gold"),
        ("CREATE", "Lakehouse", "silver"),
        ("CREATE", "Notebook", "silver_to_gold"),
        ("CREATE", "DataPipeline", "orchestrator"),
        ("CREATE", "SemanticModel", "sm_adventure_works_lt"),
        ("CREATE", "Report", "rp_adventure_works_lt"),
    ]


def test_the_engine_reads_what_the_notebook_and_the_report_need(
    empty_workspace: None,
) -> None:
    """The notebook needs gold, by name; the report its model, by path."""
    needs = {
        (a.item_type, a.display_name): set(a.needs)
        for a in _plan().actions
        if a.needs
    }

    assert needs == {
        ("Notebook", "silver_to_gold"): {("Lakehouse", "gold")},
        ("Report", "rp_adventure_works_lt"): {
            ("SemanticModel", "sm_adventure_works_lt")
        },
    }


@dataclass
class _Call:
    """A run of the engine, as the fake saw it."""

    operation: str
    item_types: list[str]
    # Whether the run was given a deployment state.
    state: bool
    # What was sent for each item: the text of each file, by its path.
    sent: dict[tuple[str, str], dict[str, str]] = field(default_factory=dict)


class _Fabric:
    """
    The two workspaces the script sees, and what it sends.

    DEV holds the items of the sample, with the IDs its README gives. PRD
    starts empty, and holds each item once a run sends it.
    """

    def __init__(self, sample: Path) -> None:
        self.dev: dict[tuple[str, str], dict[str, Any]] = {}
        for key, logical in _identities(sample).items():
            # The ID of item NN in DEV is 2NN, as its logical ID is 1NN.
            number = int(logical.rsplit("-", 1)[1]) + 100
            self.dev[key] = self._item(key, _made_up(number), logical)
        self.prd: dict[tuple[str, str], dict[str, Any]] = {}
        self.logical_ids = True
        self.calls: list[_Call] = []
        self.active_value_set: str | None = None
        self.changes: list[Any] = []

    @staticmethod
    def _item(
        key: tuple[str, str], item_id: str, logical_id: str | None
    ) -> dict[str, Any]:
        return {
            "type": key[0],
            "displayName": key[1],
            "id": item_id,
            "logicalId": logical_id,
        }

    def resolve_workspace(self, name: str) -> str | None:
        return {"DEV": _DEV, "PRD": _PRD}.get(name)

    def list_items(
        self, workspace: str, df: bool | None = True
    ) -> list[dict[str, Any]]:
        return list((self.dev if workspace == _DEV else self.prd).values())

    def _send(
        self, operation: str, path: str, kwargs: dict[str, Any]
    ) -> SimpleNamespace:
        types = kwargs.get("item_types")
        call = _Call(operation, types or [], bool(kwargs.get("state_backend")))
        for platform in sorted(Path(path).rglob(".platform")):
            (key,) = _identities(platform.parent.parent, platform).keys()
            if types is not None and key[0] not in types:
                continue
            call.sent[key] = {
                file.relative_to(platform.parent).as_posix(): file.read_text(
                    encoding="utf-8"
                )
                for file in platform.parent.rglob("*")
                if file.is_file()
            }
            if operation != "reconcile" and key not in self.prd:
                number = len(self.prd) + 1
                self.prd[key] = self._item(
                    key,
                    f"99999999-0000-4000-8000-{number:012d}",
                    f"77777777-0000-4000-8000-{number:012d}"
                    if self.logical_ids
                    else None,
                )
        self.calls.append(call)
        return SimpleNamespace(results=list(call.sent), ok=True, describe=str)

    def deploy_all_items(
        self, workspace: str, path: str, **kwargs: Any
    ) -> SimpleNamespace:
        assert workspace == _PRD
        return self._send("deploy", path, kwargs)

    def restore_items(
        self, workspace: str, path: str, **kwargs: Any
    ) -> SimpleNamespace:
        assert workspace == _PRD
        return self._send("restore", path, kwargs)

    def reconcile_items(
        self, workspace: str, path: str, **kwargs: Any
    ) -> SimpleNamespace:
        assert workspace == _PRD
        return self._send("reconcile", path, kwargs)

    def api_request(
        self, endpoint: str, *, method: str = "get", **kwargs: Any
    ) -> SimpleNamespace:
        if method == "patch":
            self.changes.append(kwargs["payload"])
            properties = kwargs["payload"]["properties"]
            self.active_value_set = properties["activeValueSetName"]
        data = {"properties": {"activeValueSetName": self.active_value_set}}
        return SimpleNamespace(success=True, data=data, error=None)

    def last(self, key: tuple[str, str], file: str) -> str:
        """The text of a file, as a run last sent it."""
        for call in reversed(self.calls):
            if key in call.sent:
                return call.sent[key][file]
        raise AssertionError(f"{key} was never sent")

    def runs(self, item_type: str) -> list[tuple[list[str], bool]]:
        """The items each run of a type sent, and whether with the state."""
        return [
            (sorted(name for _, name in call.sent), call.state)
            for call in self.calls
            if call.item_types == [item_type]
        ]


def _made_up(number: int) -> str:
    return f"00000000-0000-4000-8000-{number:012d}"


def _identities(folder: Path, *platforms: Path) -> dict[tuple[str, str], str]:
    """The logical ID of each item, by type and display name."""
    found = {}
    for platform in platforms or sorted(folder.glob("*/.platform")):
        content = json.loads(platform.read_text(encoding="utf-8"))
        metadata = content["metadata"]
        key = (metadata["type"], metadata["displayName"])
        found[key] = content["config"]["logicalId"]
    return found


@pytest.fixture()
def fabric(monkeypatch: pytest.MonkeyPatch) -> _Fabric:
    """A fake of the Fabric calls of the script."""
    fake = _Fabric(_SAMPLE)
    for name in (
        "resolve_workspace",
        "list_items",
        "deploy_all_items",
        "restore_items",
        "reconcile_items",
        "api_request",
    ):
        monkeypatch.setattr(pf, name, getattr(fake, name))
    monkeypatch.setattr(
        pf, "plan_all_items", lambda *a, **k: SimpleNamespace(describe=str)
    )
    monkeypatch.setattr(pf, "set_auth_provider", lambda *a, **k: None)
    return fake


@pytest.fixture()
def script(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """The deploy.py of the example, which reads no .env here."""
    spec = importlib.util.spec_from_file_location(
        "adventure_works_deploy", _EXAMPLE / "deploy.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # A dataclass looks its module up in sys.modules.
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    return module


def _deploy(script: ModuleType, tmp_path: Path, *extra: str) -> int:
    state = ["--state-dir", str(tmp_path / "state")]
    code: int = script.main([*_ARGS, *state, *extra])
    return code


def test_a_deployment_sends_no_id_of_the_source_workspace(
    script: ModuleType, fabric: _Fabric, tmp_path: Path
) -> None:
    """The notebook, the model and the pipeline get the IDs of PRD."""
    assert _deploy(script, tmp_path) == 0

    notebook = fabric.last(
        ("Notebook", "silver_to_gold"), "notebook-content.py"
    )
    model = fabric.last(
        ("SemanticModel", "sm_adventure_works_lt"),
        "definition/expressions.tmdl",
    )
    pipeline = fabric.last(
        ("DataPipeline", "orchestrator"), "pipeline-content.json"
    )
    dev_ids = {_DEV} | {
        value
        for item in fabric.dev.values()
        for value in (item["id"], item["logicalId"])
    }
    for text in (notebook, model, pipeline):
        assert not dev_ids & set(_GUID.findall(text))

    prd = {key: item["id"] for key, item in fabric.prd.items()}
    gold, silver = prd[("Lakehouse", "gold")], prd[("Lakehouse", "silver")]
    assert f'"default_lakehouse": "{gold}"' in notebook
    assert f'"default_lakehouse_workspace_id": "{_PRD}"' in notebook
    assert f'"id": "{silver}"' in notebook
    assert f"onelake.dfs.fabric.microsoft.com/{_PRD}/{gold}" in model
    assert prd[("Lakehouse", "bronze")] in pipeline
    assert prd[("Notebook", "silver_to_gold")] in pipeline
    assert _EMPTY not in pipeline


def test_the_variable_library_goes_as_it_is(
    script: ModuleType, fabric: _Fabric, tmp_path: Path
) -> None:
    """Its value sets hold the connection of each environment."""
    assert _deploy(script, tmp_path) == 0

    library = _SAMPLE / "variables.VariableLibrary"
    for file in ("variables.json", "valueSets/Production.json"):
        assert fabric.last(("VariableLibrary", "variables"), file) == (
            library / file
        ).read_text(encoding="utf-8")


def test_the_value_set_of_the_target_is_made_active(
    script: ModuleType, fabric: _Fabric, tmp_path: Path
) -> None:
    """It is no part of the definition, so the script sets it."""
    assert _deploy(script, tmp_path) == 0

    assert fabric.changes == [
        {"properties": {"activeValueSetName": "Production"}}
    ]
    assert fabric.active_value_set == "Production"


def test_the_value_set_is_needed_with_variable_libraries(
    script: ModuleType, fabric: _Fabric
) -> None:
    with pytest.raises(SystemExit, match="--value-set"):
        script.main(["--source-workspace", "DEV", "--workspace", "PRD"])


def test_bronze_goes_before_the_shortcut_of_silver(
    script: ModuleType, fabric: _Fabric, tmp_path: Path
) -> None:
    """Silver gets the logical ID of bronze in PRD, in the same workspace."""
    assert _deploy(script, tmp_path) == 0

    assert fabric.runs("Lakehouse") == [
        (["bronze", "gold"], False),
        (["bronze", "gold", "silver"], True),
    ]
    (shortcut,) = json.loads(
        fabric.last(("Lakehouse", "silver"), "shortcuts.metadata.json")
    )
    assert shortcut["target"]["oneLake"] == {
        "path": "Tables/SalesLT",
        "itemId": fabric.prd[("Lakehouse", "bronze")]["logicalId"],
        "workspaceId": _EMPTY,
        "artifactType": "Lakehouse",
    }


def test_a_target_without_a_logical_id_gets_its_id_and_workspace(
    script: ModuleType, fabric: _Fabric, tmp_path: Path
) -> None:
    fabric.logical_ids = False

    assert _deploy(script, tmp_path) == 0

    (shortcut,) = json.loads(
        fabric.last(("Lakehouse", "silver"), "shortcuts.metadata.json")
    )
    target = shortcut["target"]["oneLake"]
    assert target["itemId"] == fabric.prd[("Lakehouse", "bronze")]["id"]
    assert target["workspaceId"] == _PRD


def _copy_of_the_sample(tmp_path: Path) -> Path:
    source = tmp_path / "fabric-workspace"
    shutil.copytree(_SAMPLE, source)
    return source


def test_a_pipeline_goes_after_the_pipeline_it_runs(
    script: ModuleType, fabric: _Fabric, tmp_path: Path
) -> None:
    """The orchestrator runs a child pipeline by logical ID."""
    source = _copy_of_the_sample(tmp_path)
    child = source / "child.DataPipeline"
    child.mkdir()
    platform = {
        "metadata": {"type": "DataPipeline", "displayName": "child"},
        "config": {"version": "2.0", "logicalId": _made_up(109)},
    }
    (child / ".platform").write_text(json.dumps(platform), encoding="utf-8")
    (child / "pipeline-content.json").write_text(
        json.dumps({"properties": {"activities": []}}), encoding="utf-8"
    )
    orchestrator = source / "orchestrator.DataPipeline/pipeline-content.json"
    content = json.loads(orchestrator.read_text(encoding="utf-8"))
    content["properties"]["activities"].append(
        {
            "name": "run_child",
            "type": "InvokePipeline",
            "typeProperties": {
                "pipelineId": _made_up(109),
                "workspaceId": _EMPTY,
            },
        }
    )
    orchestrator.write_text(json.dumps(content), encoding="utf-8")

    assert _deploy(script, tmp_path, "--source", str(source)) == 0

    assert fabric.runs("DataPipeline") == [
        (["child"], False),
        (["child", "orchestrator"], True),
    ]
    child_id = fabric.prd[("DataPipeline", "child")]["id"]
    assert child_id in fabric.last(
        ("DataPipeline", "orchestrator"), "pipeline-content.json"
    )


def test_an_item_that_refers_to_a_later_type_is_never_sent(
    script: ModuleType, fabric: _Fabric, tmp_path: Path
) -> None:
    """A notebook cannot get the ID of a pipeline, deployed after it."""
    source = _copy_of_the_sample(tmp_path)
    notebook = source / "silver_to_gold.Notebook/notebook-content.py"
    pipeline_id = fabric.dev[("DataPipeline", "orchestrator")]["logicalId"]
    notebook.write_text(
        notebook.read_text(encoding="utf-8") + f"\n# {pipeline_id}\n",
        encoding="utf-8",
    )

    assert _deploy(script, tmp_path, "--source", str(source)) == 1

    assert fabric.runs("Notebook") == []


def test_reconcile_compares_the_translated_items_and_the_value_set(
    script: ModuleType, fabric: _Fabric, tmp_path: Path
) -> None:
    """It changes nothing, and fails when the value set is not active."""
    assert _deploy(script, tmp_path) == 0
    fabric.calls.clear()

    assert _deploy(script, tmp_path, "--reconcile") == 0
    (call,) = fabric.calls
    gold = fabric.prd[("Lakehouse", "gold")]["id"]
    assert call.operation == "reconcile" and call.state
    assert (
        gold
        in call.sent[("Notebook", "silver_to_gold")]["notebook-content.py"]
    )

    fabric.active_value_set = None
    assert _deploy(script, tmp_path, "--reconcile") == 1
    assert len(fabric.changes) == 1


def test_restore_goes_type_by_type_and_sets_the_value_set_back(
    script: ModuleType, fabric: _Fabric, tmp_path: Path
) -> None:
    assert _deploy(script, tmp_path, "--restore") == 0

    sent = [call for call in fabric.calls if call.sent]
    assert {call.operation for call in sent} == {"restore"}
    assert sent[-1].item_types == ["DataPipeline"]
    assert fabric.active_value_set == "Production"


def test_the_repository_is_never_changed(
    script: ModuleType, fabric: _Fabric, tmp_path: Path
) -> None:
    before = {p: p.read_bytes() for p in _SAMPLE.rglob("*") if p.is_file()}

    assert _deploy(script, tmp_path) == 0

    assert before == {
        p: p.read_bytes() for p in _SAMPLE.rglob("*") if p.is_file()
    }


def test_the_examples_hold_no_real_id() -> None:
    """Only the IDs made up for the sample, never one from a workspace."""
    found = {
        match.lower()
        for path in _EXAMPLES.rglob("*")
        # Credentials of a local run, which Git ignores.
        if path.is_file() and path.name != ".env"
        for match in _GUID.findall(
            path.read_text(encoding="utf-8", errors="ignore")
        )
    }

    assert {guid for guid in found if not _MADE_UP.fullmatch(guid)} == set()
