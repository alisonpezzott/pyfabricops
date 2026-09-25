"""Tests for the comparable form of definitions in pyfabricops.helpers.drift."""

from __future__ import annotations

import ast
import base64
import inspect
import json
import sys
from typing import Any

from pyfabricops.helpers import content_hash, drift
from pyfabricops.helpers.drift import comparable_parts, differing_parts

_NOTEBOOK = "# Fabric notebook source\n\n# CELL ****\n\nprint('hello')\n"
_MODEL = (
    "model Model\n"
    "\tculture: en-US\n"
    "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
)


def _definition(files: dict[str, str | bytes]) -> dict[str, Any]:
    """A definition as pack_item_definition builds it."""
    return {
        "parts": [
            {
                "path": path,
                "payload": base64.b64encode(
                    content.encode("utf-8")
                    if isinstance(content, str)
                    else content
                ).decode("ascii"),
                "payloadType": "InlineBase64",
            }
            for path, content in files.items()
        ]
    }


def _differ(
    source: dict[str, str | bytes], workspace: dict[str, str | bytes]
) -> tuple[str, ...]:
    return differing_parts(
        comparable_parts(_definition(source)),
        comparable_parts(_definition(workspace)),
    )


def _platform(logical_id: str, description: str = "Raw data.") -> str:
    return json.dumps(
        {
            "metadata": {
                "type": "Lakehouse",
                "displayName": "Bronze",
                "description": description,
            },
            "config": {"version": "2.0", "logicalId": logical_id},
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# What Fabric rewrites by itself
# ---------------------------------------------------------------------------


def test_line_endings_and_the_end_of_a_text_part_are_no_difference() -> None:
    """Fabric may return CRLF, or no newline at the end of a file."""
    workspace = _NOTEBOOK.replace("\n", "\r\n").rstrip() + "\r\n\r\n"

    assert (
        _differ(
            {"notebook-content.py": _NOTEBOOK},
            {"notebook-content.py": workspace},
        )
        == ()
    )


def test_json_layout_and_key_order_are_no_difference() -> None:
    """A lakehouse's metadata comes back on one line."""
    assert (
        _differ(
            {"lakehouse.metadata.json": '{\n  "defaultSchema": "dbo"\n}\n'},
            {"lakehouse.metadata.json": '{"defaultSchema":"dbo"}'},
        )
        == ()
    )


def test_the_logical_id_fabric_assigns_is_no_difference() -> None:
    """Fabric gives each item a logical ID of its own."""
    assert (
        _differ(
            {".platform": _platform("11111111-1111-4111-8111-111111111111")},
            {".platform": _platform("22222222-2222-4222-8222-222222222222")},
        )
        == ()
    )


def test_a_description_changed_in_the_workspace_is_a_difference() -> None:
    """The rest of .platform is compared as it is."""
    logical_id = "11111111-1111-4111-8111-111111111111"

    assert _differ(
        {".platform": _platform(logical_id)},
        {".platform": _platform(logical_id, description="Edited by hand.")},
    ) == (".platform",)


def test_a_report_is_compared_by_the_model_it_points_to() -> None:
    """By path in Git, by connection in the workspace: the same model."""
    by_path = json.dumps(
        {
            "version": "4.0",
            "datasetReference": {"byPath": {"path": "../Sales.SemanticModel"}},
        }
    )
    by_connection = json.dumps(
        {
            "version": "4.0",
            "datasetReference": {
                "byConnection": {
                    "connectionString": "Data Source=powerbi://api.powerbi."
                    "com/v1.0/myorg/Sales-PRD;initial catalog=Sales;"
                    "integrated security=ClaimsToken;semanticmodelid=<id>"
                }
            },
        }
    )
    source = comparable_parts(
        _definition({"definition.pbir": by_path}), semantic_model="Sales"
    )

    def workspace(model: str | None) -> dict[str, bytes]:
        return comparable_parts(
            _definition({"definition.pbir": by_connection}),
            semantic_model=model,
        )

    assert differing_parts(source, workspace("Sales")) == ()
    assert differing_parts(source, workspace("Finance")) == (
        "definition.pbir",
    )
    assert differing_parts(source, workspace(None)) == ("definition.pbir",)


def test_the_ref_lines_fabric_adds_to_a_model_are_no_difference() -> None:
    """Fabric lists the tables of model.tmdl, to keep their order."""
    workspace = _MODEL + "\nref table Orders\n\nref table Customers\n\n"

    assert (
        _differ(
            {"definition/model.tmdl": _MODEL},
            {"definition/model.tmdl": workspace},
        )
        == ()
    )


# ---------------------------------------------------------------------------
# What is a difference
# ---------------------------------------------------------------------------


def test_a_change_made_in_the_workspace_is_a_difference() -> None:
    """A cell edited by hand shows in the part that holds it."""
    edited = _NOTEBOOK.replace("hello", "edited by hand")

    assert _differ(
        {"notebook-content.py": _NOTEBOOK, ".platform": "{}"},
        {"notebook-content.py": edited, ".platform": "{}"},
    ) == ("notebook-content.py",)


def test_a_model_property_changed_is_a_difference() -> None:
    """Only ref lines are left out of model.tmdl."""
    edited = _MODEL.replace("en-US", "pt-BR")

    assert _differ(
        {"definition/model.tmdl": _MODEL},
        {"definition/model.tmdl": edited},
    ) == ("definition/model.tmdl",)


def test_a_part_on_one_side_only_is_a_difference() -> None:
    """Each missing or extra part is named, in path order."""
    assert _differ(
        {"b.json": '{"x": 1}', "a.json": '{"x": 1}'},
        {"b.json": '{"x": 1}', "c.json": '{"x": 1}'},
    ) == ("a.json", "c.json")


def test_an_empty_part_fabric_adds_is_no_difference() -> None:
    """A lakehouse sent without shortcuts comes back with an empty list."""
    assert (
        _differ(
            {"lakehouse.metadata.json": "{}"},
            {
                "lakehouse.metadata.json": "{}",
                "shortcuts.metadata.json": "[]\n",
            },
        )
        == ()
    )


def test_shortcuts_removed_by_hand_are_a_difference() -> None:
    """An empty part still differs from one that holds something."""
    shortcut = '[{"name": "Sales", "path": "Tables"}]'

    assert _differ(
        {"shortcuts.metadata.json": shortcut},
        {"shortcuts.metadata.json": "[]"},
    ) == ("shortcuts.metadata.json",)
    assert _differ({"shortcuts.metadata.json": shortcut}, {}) == (
        "shortcuts.metadata.json",
    )


def test_a_platform_file_on_one_side_only_is_left_out() -> None:
    """Not every item type returns its .platform."""
    assert (
        _differ(
            {".platform": _platform("<id>"), "notebook-content.py": _NOTEBOOK},
            {"notebook-content.py": _NOTEBOOK},
        )
        == ()
    )


def test_bytes_that_are_not_text_are_compared_as_they_are() -> None:
    """An image, say, is equal or not, byte for byte."""
    image = b"\x89PNG\r\n\x1a\n\xff\x00"

    assert _differ({"logo.png": image}, {"logo.png": image}) == ()
    assert _differ({"logo.png": image}, {"logo.png": image + b"\x01"}) == (
        "logo.png",
    )


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


def test_the_comparison_cannot_reach_the_fabric_api() -> None:
    """
    The module imports only the standard library, and the content hash,
    which imports only the standard library itself.
    """
    for module, allowed in ((drift, {"content_hash"}), (content_hash, set())):
        imported: set[str] = set()
        for node in ast.walk(ast.parse(inspect.getsource(module))):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    assert node.level == 1 and node.module in allowed
                    continue
                imported.add(node.module or "")

        assert {name.split(".")[0] for name in imported} <= (
            sys.stdlib_module_names
        )
