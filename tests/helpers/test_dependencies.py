"""Tests for the local catalog and references in helpers.dependencies."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pyfabricops.helpers.dependencies import (
    LocalCatalog,
    ReferenceScan,
    scan_references,
)
from pyfabricops.helpers.dependency_graph import Dependency

_TYPES = ("Lakehouse", "Environment", "SemanticModel", "Notebook", "Report")
SALES_REPORT = ("Report", "Sales")
SALES_MODEL = ("SemanticModel", "Sales")
LOAD = ("Notebook", "Load")
CLEAN = ("Notebook", "Clean")
GOLD = ("Lakehouse", "Gold")


def _item(root: Path, relative: str, logical_id: str | None = None) -> Path:
    """Write an item folder with its .platform."""
    folder = root / relative
    folder.mkdir(parents=True)
    name, item_type = folder.name.rsplit(".", 1)
    platform: dict[str, Any] = {
        "metadata": {"type": item_type, "displayName": name},
    }
    if logical_id:
        platform["config"] = {"version": "2.0", "logicalId": logical_id}
    (folder / ".platform").write_text(json.dumps(platform), encoding="utf-8")
    return folder


def _report(root: Path, relative: str, reference: dict[str, Any]) -> Path:
    """Write a report whose definition.pbir holds a dataset reference."""
    folder = _item(root, relative)
    pbir = {"version": "4.0", "datasetReference": reference}
    (folder / "definition.pbir").write_text(json.dumps(pbir), encoding="utf-8")
    return folder


def _scan(root: Path, *keys: tuple[str, str]) -> ReferenceScan:
    return scan_references(LocalCatalog.read(str(root), _TYPES), keys)


def _connection(catalog: str) -> dict[str, Any]:
    """A byConnection reference with an initial catalog."""
    return {
        "byConnection": {
            "connectionString": (
                'Data Source="powerbi://api.powerbi.com/v1.0/myorg/Dev";'
                f"Initial Catalog={catalog};Access Mode=readonly"
            )
        }
    }


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


def test_the_catalog_lists_items_by_identity_and_folder(
    tmp_path: Path,
) -> None:
    """Type from the folder, name and logical ID from .platform."""
    model = _item(tmp_path, "Models/Sales.SemanticModel", "lid-sales")
    (tmp_path / "Broken.Notebook").mkdir()

    catalog = LocalCatalog.read(str(tmp_path), _TYPES)

    item = catalog.get(SALES_MODEL)
    assert item is not None
    assert (item.logical_id, Path(item.path)) == ("lid-sales", model)
    assert catalog.at(str(model)) == item
    assert catalog.get(("Notebook", "Broken")) is None


# ---------------------------------------------------------------------------
# Report -> SemanticModel
# ---------------------------------------------------------------------------


def test_a_report_by_path_depends_on_its_semantic_model(
    tmp_path: Path,
) -> None:
    """The relative path is resolved from the report folder."""
    _item(tmp_path, "Models/Sales.SemanticModel")
    _report(
        tmp_path,
        "Reports/Sales.Report",
        {"byPath": {"path": "../../Models/Sales.SemanticModel"}},
    )

    scan = _scan(tmp_path, SALES_REPORT)

    assert scan.dependencies == (
        Dependency(SALES_REPORT, SALES_MODEL, "definition.pbir byPath"),
    )
    assert dict(scan.broken) == {}


def test_a_report_by_path_to_a_missing_model_is_broken(
    tmp_path: Path,
) -> None:
    """The planner blocks it rather than deploying a report without data."""
    _report(
        tmp_path, "Sales.Report", {"byPath": {"path": "../Gone.SemanticModel"}}
    )

    scan = _scan(tmp_path, SALES_REPORT)

    assert scan.dependencies == ()
    assert dict(scan.broken) == {
        SALES_REPORT: (
            "definition.pbir points to ../Gone.SemanticModel, which is not "
            "a semantic model of the source.",
        )
    }


def test_a_report_by_path_to_another_item_type_is_broken(
    tmp_path: Path,
) -> None:
    """Only a semantic model can hold a report's data."""
    _item(tmp_path, "Sales.Notebook")
    _report(
        tmp_path, "Sales.Report", {"byPath": {"path": "../Sales.Notebook"}}
    )

    assert SALES_REPORT in _scan(tmp_path, SALES_REPORT).broken


def test_a_report_by_connection_depends_on_the_local_model_of_that_name(
    tmp_path: Path,
) -> None:
    """The initial catalog names the model, quoted or not, in any case."""
    _item(tmp_path, "Sales.SemanticModel")
    _report(tmp_path, "Sales.Report", _connection('"Sales"'))

    scan = _scan(tmp_path, SALES_REPORT)

    assert scan.dependencies == (
        Dependency(SALES_REPORT, SALES_MODEL, "definition.pbir byConnection"),
    )


def test_a_report_by_connection_to_a_model_outside_the_source_is_left_out(
    tmp_path: Path,
) -> None:
    """A shared model of another workspace is neither deployed nor broken."""
    _report(tmp_path, "Sales.Report", _connection("Finance"))

    scan = _scan(tmp_path, SALES_REPORT)

    assert (scan.dependencies, dict(scan.broken)) == ((), {})


def test_an_unreadable_report_definition_gives_no_references(
    tmp_path: Path,
) -> None:
    """Its deployment reports the problem; the scan does not guess."""
    folder = _item(tmp_path, "Sales.Report")
    (folder / "definition.pbir").write_text("{not json", encoding="utf-8")
    _item(tmp_path, "Other.Report")

    scan = _scan(tmp_path, SALES_REPORT, ("Report", "Other"))

    assert (scan.dependencies, dict(scan.broken)) == ((), {})


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


def test_the_scan_starts_from_the_selection_only(tmp_path: Path) -> None:
    """Items outside the selection and what they need are not read."""
    _item(tmp_path, "Sales.SemanticModel")
    _report(
        tmp_path,
        "Sales.Report",
        {"byPath": {"path": "../Sales.SemanticModel"}},
    )
    _report(
        tmp_path, "Other.Report", {"byPath": {"path": "../Gone.SemanticModel"}}
    )

    scan = _scan(tmp_path, SALES_REPORT, ("Report", "Missing"))

    assert [d.target for d in scan.dependencies] == [SALES_MODEL]
    assert dict(scan.broken) == {}


def test_types_without_references_to_read_give_none(tmp_path: Path) -> None:
    """Semantic model sources are not read yet."""
    _item(tmp_path, "Sales.SemanticModel")

    scan = _scan(tmp_path, SALES_MODEL)

    assert (scan.dependencies, dict(scan.broken)) == ((), {})


# ---------------------------------------------------------------------------
# Notebook -> Lakehouse, Environment, Notebook
# ---------------------------------------------------------------------------


def _notebook(
    root: Path,
    relative: str,
    metadata: dict[str, Any] | None = None,
    cells: tuple[str, ...] = (),
    *,
    language: str = "py",
    comment: str = "#",
) -> Path:
    """Write a notebook in the Fabric source format of its language."""
    folder = _item(root, relative)
    lines = [f"{comment} Fabric notebook source", ""]
    lines += [f"{comment} METADATA ********************", ""]
    meta = json.dumps(metadata or {"dependencies": {}}, indent=2)
    lines += [f"{comment} META {line}" for line in meta.splitlines()]
    for cell in cells:
        lines += ["", f"{comment} CELL ********************", "", cell]
        lines += ["", f"{comment} METADATA ********************", ""]
        lines += [f'{comment} META {{"language": "{language}"}}']
    (folder / f"notebook-content.{language}").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return folder


def _lakehouse(default: str, name: str) -> dict[str, Any]:
    """Notebook metadata with a default lakehouse."""
    return {
        "dependencies": {
            "lakehouse": {
                "default_lakehouse": default,
                "default_lakehouse_name": name,
                "default_lakehouse_workspace_id": "<workspace-id>",
            }
        }
    }


def _vias(scan: ReferenceScan) -> list[tuple[str, str]]:
    """Each dependency as (target name, via)."""
    return [(d.target[1], d.via) for d in scan.dependencies]


def test_a_notebook_needs_its_default_lakehouse_by_logical_id(
    tmp_path: Path,
) -> None:
    """The logical ID wins over the name."""
    _item(tmp_path, "Gold.Lakehouse", "lid-gold")
    _item(tmp_path, "Other.Lakehouse")
    _notebook(tmp_path, "Load.Notebook", _lakehouse("lid-gold", "Other"))

    assert _vias(_scan(tmp_path, LOAD)) == [
        ("Gold", "notebook default lakehouse")
    ]


def test_a_notebook_needs_its_default_lakehouse_by_name(
    tmp_path: Path,
) -> None:
    """A physical ID matches no local item, so the name decides."""
    _item(tmp_path, "Gold.Lakehouse", "lid-gold")
    _notebook(tmp_path, "Load.Notebook", _lakehouse("<lakehouse-id>", "Gold"))

    assert _vias(_scan(tmp_path, LOAD)) == [
        ("Gold", "notebook default lakehouse, by name")
    ]


def test_a_default_lakehouse_outside_the_source_is_left_out(
    tmp_path: Path,
) -> None:
    """A shared lakehouse of another workspace is neither deployed nor broken."""
    _notebook(
        tmp_path, "Load.Notebook", _lakehouse("<lakehouse-id>", "Shared")
    )

    scan = _scan(tmp_path, LOAD)

    assert (scan.dependencies, dict(scan.broken)) == ((), {})


def test_a_notebook_needs_its_environment_by_logical_id(
    tmp_path: Path,
) -> None:
    """Only a logical ID names a local environment; there is no name."""
    _item(tmp_path, "Spark.Environment", "lid-spark")
    environment = {"environmentId": "lid-spark", "workspaceId": "<id>"}
    _notebook(
        tmp_path,
        "Load.Notebook",
        {"dependencies": {"environment": environment}},
    )
    _notebook(
        tmp_path,
        "Clean.Notebook",
        {"dependencies": {"environment": {"environmentId": "<env-id>"}}},
    )

    assert _vias(_scan(tmp_path, LOAD)) == [("Spark", "notebook environment")]
    assert _scan(tmp_path, CLEAN).dependencies == ()


def test_run_refers_to_other_notebooks_by_name(tmp_path: Path) -> None:
    """Quoted or not, raw or as MAGIC; resource scripts are not notebooks."""
    _notebook(tmp_path, "Clean.Notebook")
    _notebook(tmp_path, "Shared Utils.Notebook")
    _notebook(
        tmp_path,
        "Load.Notebook",
        cells=(
            "%run Clean",
            '# MAGIC %run "Shared Utils"',
            "%run -b script_file.py",
            "%run helpers.py",
            "%run Missing",
            '%run Clean { "parameterInt": 1 }',
        ),
    )

    assert _vias(_scan(tmp_path, LOAD)) == [
        ("Clean", "%run"),
        ("Shared Utils", "%run"),
    ]


def test_sql_notebooks_are_read_too(tmp_path: Path) -> None:
    """The metadata comments start with -- in a Spark SQL notebook."""
    _item(tmp_path, "Gold.Lakehouse")
    _notebook(
        tmp_path,
        "Load.Notebook",
        _lakehouse("<lakehouse-id>", "Gold"),
        cells=("SELECT 1",),
        language="sql",
        comment="--",
    )

    assert [d.target for d in _scan(tmp_path, LOAD).dependencies] == [GOLD]


def test_ipynb_notebooks_are_read_too(tmp_path: Path) -> None:
    """The metadata and the cell sources come from the JSON."""
    _item(tmp_path, "Gold.Lakehouse")
    _notebook(tmp_path, "Clean.Notebook")
    folder = _item(tmp_path, "Load.Notebook")
    ipynb = {
        "metadata": _lakehouse("<lakehouse-id>", "Gold"),
        "cells": [{"cell_type": "code", "source": ["%run Clean\n", "x = 1"]}],
    }
    (folder / "notebook-content.ipynb").write_text(
        json.dumps(ipynb), encoding="utf-8"
    )

    assert [d.target for d in _scan(tmp_path, LOAD).dependencies] == [
        GOLD,
        CLEAN,
    ]


def test_the_scan_follows_what_run_notebooks_need(tmp_path: Path) -> None:
    """Load runs Clean, which writes to Gold: both are needed."""
    _item(tmp_path, "Gold.Lakehouse")
    _notebook(tmp_path, "Clean.Notebook", _lakehouse("<id>", "Gold"))
    _notebook(tmp_path, "Load.Notebook", cells=("%run Clean",))

    scan = _scan(tmp_path, LOAD)

    assert [(d.source, d.target) for d in scan.dependencies] == [
        (LOAD, CLEAN),
        (CLEAN, GOLD),
    ]


def test_a_notebook_without_dependencies_needs_nothing(
    tmp_path: Path,
) -> None:
    """No lakehouse, no environment, no %run: nothing to read."""
    _notebook(
        tmp_path,
        "Load.Notebook",
        {"kernel_info": {"name": "synapse_pyspark"}, "dependencies": {}},
        cells=("print(1)",),
    )

    assert _scan(tmp_path, LOAD).dependencies == ()
