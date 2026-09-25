"""Tests for export_all_* continuing after an item fails."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any
from unittest.mock import patch

from pyfabricops.helpers.items import export_all_items
from pyfabricops.helpers.notebooks import export_all_notebooks

_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


def _definition(content: str) -> dict[str, Any]:
    """An item definition with one part."""
    payload = base64.b64encode(content.encode()).decode()
    return {
        "definition": {
            "parts": [
                {
                    "path": "notebook-content.py",
                    "payload": payload,
                    "payloadType": "InlineBase64",
                }
            ]
        }
    }


def test_export_all_notebooks_skips_items_without_definition(
    tmp_path: Path,
) -> None:
    """A notebook that cannot be read no longer aborts the export."""
    notebooks = [
        {"id": "1", "displayName": "Broken"},
        {"id": "2", "displayName": "Orders"},
    ]
    module = "pyfabricops.helpers.notebooks"
    with (
        patch(f"{module}.resolve_workspace", return_value=_WORKSPACE_ID),
        patch(f"{module}.list_notebooks", return_value=notebooks),
        patch(f"{module}.resolve_folder_from_id_to_path", return_value=None),
        patch(
            f"{module}.get_notebook_definition",
            side_effect=[None, _definition("print('orders')")],
        ),
    ):
        export_all_notebooks("Sales-DEV", tmp_path)

    exported = tmp_path / "Orders.Notebook" / "notebook-content.py"
    assert exported.read_text(encoding="utf-8") == "print('orders')"
    assert not (tmp_path / "Broken.Notebook").exists()


def test_export_all_items_continues_after_unreadable_item(
    tmp_path: Path,
) -> None:
    """export_all_items skips an unreadable item and exports the rest."""
    items = [
        {"id": "1", "type": "Notebook", "displayName": "Broken"},
        {"id": "2", "type": "Notebook", "displayName": "Orders"},
        {"id": "3", "type": "SQLEndpoint", "displayName": "Bronze"},
    ]
    by_id = {item["id"]: item for item in items}
    module = "pyfabricops.helpers.items"
    with (
        patch(f"{module}.resolve_workspace", return_value=_WORKSPACE_ID),
        patch(f"{module}.list_items", return_value=items),
        patch(
            f"{module}.get_item",
            side_effect=lambda workspace, item_id, df: by_id[item_id],
        ),
        patch(
            f"{module}.get_item_definition",
            side_effect=[None, _definition("print('orders')")],
        ) as get_definition,
    ):
        export_all_items("Sales-DEV", str(tmp_path))

    exported = tmp_path / "Orders.Notebook" / "notebook-content.py"
    assert exported.read_text(encoding="utf-8") == "print('orders')"
    assert not (tmp_path / "Broken.Notebook").exists()
    assert get_definition.call_count == 2
