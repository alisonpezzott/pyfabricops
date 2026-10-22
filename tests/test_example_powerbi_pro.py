"""Tests for the Deploy-PowerBI-Pro example: its sample and its script."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

from pyfabricops.helpers.deployment_plan import DeploymentPlan
from pyfabricops.helpers.items import plan_all_items

_EXAMPLE = (
    Path(__file__).resolve().parent.parent / "examples" / "Deploy-PowerBI-Pro"
)
_SAMPLE = _EXAMPLE / "fabric-workspace"
_ENGINE = "pyfabricops.helpers.deployment"
_PRD = "99999999-0000-4000-8000-000000000001"
_EXPRESSIONS = Path("Main.SemanticModel", "definition", "expressions.tmdl")

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


def test_the_engine_creates_the_model_before_its_reports(
    empty_workspace: None,
) -> None:
    """Both reports need the model, by path."""
    actions = _plan().actions

    assert [
        (a.action.value, a.item_type, a.display_name) for a in actions
    ] == [
        ("CREATE", "SemanticModel", "Main"),
        ("CREATE", "Report", "Main"),
        ("CREATE", "Report", "Secondary"),
    ]
    assert {a.display_name: set(a.needs) for a in actions if a.needs} == {
        "Main": {("SemanticModel", "Main")},
        "Secondary": {("SemanticModel", "Main")},
    }


@pytest.fixture()
def script(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """The deploy.py of the example, which reads no .env here."""
    spec = importlib.util.spec_from_file_location(
        "powerbi_pro_deploy", _EXAMPLE / "deploy.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # A dataclass looks its module up in sys.modules.
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    return module


def _staged(tmp_path: Path) -> Path:
    """A copy of the sample, as deploy.py stages it."""
    staging = tmp_path / "staging" / "fabric-workspace"
    shutil.copytree(_SAMPLE, staging)
    return staging


def _environment(tmp_path: Path, name: str, content: object) -> None:
    folder = tmp_path / "environments"
    folder.mkdir(exist_ok=True)
    (folder / f"{name}.json").write_text(json.dumps(content), encoding="utf-8")


def test_an_environment_gives_its_workspace_and_parameters(
    script: ModuleType,
) -> None:
    environment = script.read_environment("PRD")

    assert environment.workspace == "Power-BI-Pro-PRD"
    assert environment.parameters == {
        "Main": {
            "Server": "your-prd-server.database.windows.net",
            "Database": "adventureworkslt",
        }
    }


def test_an_unknown_environment_names_the_known_ones(
    script: ModuleType,
) -> None:
    with pytest.raises(SystemExit, match="Known: DEV, PRD"):
        script.read_environment("QA")


def test_an_environment_without_a_workspace_or_with_another_key_stops(
    script: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _environment(tmp_path, "QA", {"parameter": {}})
    monkeypatch.setattr(script, "ENVIRONMENTS", tmp_path / "environments")

    with pytest.raises(SystemExit) as stopped:
        script.read_environment("QA")

    assert str(stopped.value).splitlines() == [
        "QA.json: unknown key parameter.",
        "QA.json: no workspace.",
    ]


def test_the_staged_models_get_the_parameters_of_the_environment(
    script: ModuleType, tmp_path: Path
) -> None:
    """The repository keeps the values of DEV; the staged copy those of PRD."""
    before = (_SAMPLE / _EXPRESSIONS).read_bytes()
    staging = _staged(tmp_path)
    items = script.read_items(staging)
    parameters = script.read_parameters(script.read_environment("PRD"), items)

    script.apply_parameters(items, parameters)

    (model,) = script.models(items)
    assert script.Expressions(model).values() == {
        "Server": "your-prd-server.database.windows.net",
        "Database": "adventureworkslt",
    }
    assert (_SAMPLE / _EXPRESSIONS).read_bytes() == before


def test_the_parameters_of_dev_are_those_desktop_opens_with(
    script: ModuleType,
) -> None:
    items = script.read_items(_SAMPLE)
    (model,) = script.models(items)

    assert (
        script.Expressions(model).values()
        == script.read_environment("DEV").parameters["Main"]
    )


def test_every_parameter_of_every_model_and_no_other(
    script: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No model keeps a value of DEV by omission."""
    parameters = {"Main": {"Server": "x", "Port": "1"}, "Other": {}}
    _environment(tmp_path, "QA", {"workspace": "QA", "parameters": parameters})
    monkeypatch.setattr(script, "ENVIRONMENTS", tmp_path / "environments")
    items = script.read_items(_staged(tmp_path))

    with pytest.raises(SystemExit) as stopped:
        script.read_parameters(script.read_environment("QA"), items)

    assert str(stopped.value).splitlines() == [
        "QA.json: no semantic model Other in the repository.",
        "QA.json: no value for Database of Main.SemanticModel.",
        "QA.json: Main.SemanticModel has no parameter Port.",
    ]


def test_a_parameter_that_is_not_text_stops_the_run(
    script: ModuleType, tmp_path: Path
) -> None:
    staging = _staged(tmp_path)
    expressions = staging / _EXPRESSIONS
    expressions.write_text(
        expressions.read_text(encoding="utf-8")
        + "\nexpression Rows = 10 meta [IsParameterQuery = true, "
        "Type = type number]\n",
        encoding="utf-8",
    )
    (model,) = script.models(script.read_items(staging))

    with pytest.raises(SystemExit, match="parameter Rows is not text"):
        script.Expressions(model).values()


def test_the_staged_copy_leaves_out_what_git_ignores_and_the_layout(
    script: ModuleType, tmp_path: Path
) -> None:
    """The data cache of Desktop, and what the service does not keep."""
    repository = tmp_path / "repository"
    source = repository / "fabric-workspace"
    shutil.copytree(_SAMPLE, source)
    shutil.copy(_EXAMPLE / ".gitignore", repository / ".gitignore")
    cache = Path("Main.SemanticModel", ".pbi", "cache.abf")
    (source / cache).write_bytes(b"data")
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    staging = tmp_path / "staging" / "fabric-workspace"
    shutil.copytree(source, staging)

    script.drop_local_files(source, staging, script.read_items(staging))

    assert not (staging / cache).exists()
    assert not (staging / "Main.SemanticModel" / "diagramLayout.json").exists()
    assert (
        staging / "Main.SemanticModel" / ".pbi" / "editorSettings.json"
    ).exists()
    assert (staging / _EXPRESSIONS).exists()


def test_an_item_a_pro_workspace_cannot_hold_stops_the_run(
    script: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "repository" / "fabric-workspace"
    shutil.copytree(_SAMPLE, source)
    lakehouse = source / "bronze.Lakehouse"
    lakehouse.mkdir()
    (lakehouse / ".platform").write_text(
        json.dumps(
            {"metadata": {"type": "Lakehouse", "displayName": "bronze"}}
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q", str(source.parent)], check=True)
    monkeypatch.setattr(script.pf, "resolve_workspace", lambda name: _PRD)

    with pytest.raises(SystemExit, match="holds no Lakehouse"):
        script.main(["--environment", "PRD", "--source", str(source)])


def test_every_pipeline_runs_the_environment_of_its_branch() -> None:
    """The files give the workspaces; the pipelines only pick the file."""
    pipelines = {
        name: (_EXAMPLE / name).read_text(encoding="utf-8")
        for name in (
            "azure-pipelines.yml",
            "azure-pipelines-reconcile.yml",
            ".github/workflows/deploy.yml",
            ".github/workflows/reconcile.yml",
        )
    }

    for text in pipelines.values():
        assert "--environment" in text
        assert "--state-branch pyfabricops/state" in text
        assert '"pyfabricops>=0.8.1,<0.9.0"' in text
        assert "--workspace" not in text
    for name in ("azure-pipelines.yml", "azure-pipelines-reconcile.yml"):
        # Picked when the pipeline is compiled, never edited at queue time.
        assert "parameters:" not in pipelines[name]
        assert (
            "variables['Build.SourceBranch'], 'refs/heads/main'"
            in (pipelines[name])
        )
        assert "persistCredentials: true" in pipelines[name]
    assert "contents: write" in pipelines[".github/workflows/deploy.yml"]
    assert "contents: read" in pipelines[".github/workflows/reconcile.yml"]
