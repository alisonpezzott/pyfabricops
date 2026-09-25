"""Tests for the examples folder: the sample workspace plans as documented."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from pyfabricops.helpers.deployment_plan import DeploymentPlan
from pyfabricops.helpers.items import plan_all_items

_EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
_SAMPLE = _EXAMPLES / "sample-workspace"
_ENGINE = "pyfabricops.helpers.deployment"
_GUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
# The logical IDs made up for the sample, and the workspace ID Fabric writes
# for an item of the same workspace.
_MADE_UP_IDS = {
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
    "33333333-3333-4333-8333-333333333333",
    "44444444-4444-4444-8444-444444444444",
    "55555555-5555-4555-8555-555555555555",
    "66666666-6666-4666-8666-666666666666",
    "00000000-0000-0000-0000-000000000000",
}

# The source distribution leaves the examples out.
pytestmark = pytest.mark.skipif(
    not _SAMPLE.is_dir(), reason="examples/ is not in this copy"
)


@pytest.fixture()
def empty_workspace() -> Iterator[None]:
    """A workspace that holds nothing yet."""
    with (
        patch(
            f"{_ENGINE}.resolve_workspace",
            return_value="00000000-0000-0000-0000-000000000001",
        ),
        patch(f"{_ENGINE}.list_items", return_value=[]),
        patch(f"{_ENGINE}.list_folders", return_value=[]),
    ):
        yield


def _plan() -> DeploymentPlan:
    return plan_all_items("Sample", str(_SAMPLE), start_path=str(_SAMPLE))


def test_the_sample_is_created_in_dependency_order(
    empty_workspace: None,
) -> None:
    """Utils comes before LoadOrders, which runs it, though not by name."""
    assert [
        (a.action.value, a.item_type, a.display_name, a.folder_path)
        for a in _plan().actions
    ] == [
        ("CREATE", "Lakehouse", "Bronze", "Data"),
        ("CREATE", "Notebook", "Utils", "Data"),
        ("CREATE", "Notebook", "LoadOrders", "Data"),
        ("CREATE", "DataPipeline", "DailyLoad", "Data"),
        ("CREATE", "SemanticModel", "Sales", "Reports"),
        ("CREATE", "Report", "Sales", "Reports"),
    ]


def test_each_sample_item_needs_what_the_readme_says(
    empty_workspace: None,
) -> None:
    """The notebook needs its lakehouse and Utils; the report its model."""
    needs = {
        (a.item_type, a.display_name): set(a.needs) for a in _plan().actions
    }

    assert needs == {
        ("Lakehouse", "Bronze"): set(),
        ("Notebook", "Utils"): set(),
        ("Notebook", "LoadOrders"): {
            ("Lakehouse", "Bronze"),
            ("Notebook", "Utils"),
        },
        ("DataPipeline", "DailyLoad"): set(),
        ("SemanticModel", "Sales"): set(),
        ("Report", "Sales"): {("SemanticModel", "Sales")},
    }


def test_the_pipeline_placeholders_are_warned_about_until_replaced(
    empty_workspace: None,
) -> None:
    """The notebook ID only exists once the notebook is deployed."""
    (pipeline,) = [a for a in _plan().actions if a.item_type == "DataPipeline"]

    assert pipeline.detail == (
        "Warning: Activity 'Load orders' refers to workspace "
        "'#{workspace_id}#', which is not an ID (a placeholder left "
        "unreplaced?)."
    )


def test_the_examples_replace_every_placeholder_of_the_sample() -> None:
    """
    A placeholder added to the sample must be handled by the examples that
    stage it: the deployments and the reconciliation.
    """
    placeholder = re.compile(r"#\{\w+\}#")
    in_sample = {
        match
        for path in _SAMPLE.rglob("*")
        if path.is_file()
        for match in placeholder.findall(path.read_text(encoding="utf-8"))
    }

    assert in_sample == {
        "#{environment}#",
        "#{workspace_id}#",
        "#{load_orders_notebook_id}#",
    }
    for script in (
        "03-deploy-full/deploy.py",
        "04-deploy-selective/deploy.py",
        "07-reconcile/reconcile.py",
    ):
        text = (_EXAMPLES / script).read_text(encoding="utf-8")
        assert in_sample <= set(placeholder.findall(text)), script


def test_the_examples_hold_no_real_id() -> None:
    """Only the IDs made up for the sample, never one from a workspace."""
    found = {
        match
        for path in _EXAMPLES.rglob("*")
        if path.is_file()
        for match in _GUID.findall(
            path.read_text(encoding="utf-8", errors="ignore")
        )
    }

    assert found <= _MADE_UP_IDS
