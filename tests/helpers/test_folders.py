"""Tests for pyfabricops.helpers.folders — folder hierarchy (issue #72)."""

from __future__ import annotations

from unittest.mock import call, patch

import pytest

from pyfabricops.helpers.folders import create_folders_from_path_string

_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"

_EMPRESA1_ID = "aaaaaaaa-0000-0000-0000-000000000001"
_EMPRESA2_ID = "bbbbbbbb-0000-0000-0000-000000000001"
_COMERCIAL_E1_ID = "cccccccc-0000-0000-0000-000000000001"
_COMERCIAL_E2_ID = "dddddddd-0000-0000-0000-000000000001"


@pytest.fixture()
def mock_resolve_workspace():
    """Patch resolve_workspace to return the workspace ID unchanged."""
    with patch(
        "pyfabricops.helpers.folders.resolve_workspace",
        side_effect=lambda w: w,
    ) as m:
        yield m


# ---------------------------------------------------------------------------
# create_folders_from_path_string
# ---------------------------------------------------------------------------


def test_create_folders_existing_path_resolves_in_order(
    mock_resolve_workspace,
) -> None:
    """All folders already exist: resolve_folder is called with correct parent scope."""
    resolve_side_effects = [
        _EMPRESA1_ID,  # resolve "Empresa 1" under root (None)
        _COMERCIAL_E1_ID,  # resolve "COMERCIAL" under Empresa 1
    ]
    with (
        patch(
            "pyfabricops.helpers.folders.resolve_folder",
            side_effect=resolve_side_effects,
        ) as mock_resolve,
        patch("pyfabricops.helpers.folders.create_folder") as mock_create,
    ):
        create_folders_from_path_string(_WORKSPACE_ID, "Empresa 1/COMERCIAL")

    # Verify parent_folder_id scoping: first call has no parent, second has Empresa 1 id
    assert mock_resolve.call_args_list == [
        call(_WORKSPACE_ID, "Empresa 1", parent_folder_id=None),
        call(_WORKSPACE_ID, "COMERCIAL", parent_folder_id=_EMPRESA1_ID),
    ]
    mock_create.assert_not_called()


def test_create_folders_duplicate_names_different_parents(
    mock_resolve_workspace,
) -> None:
    """Duplicate folder names at different hierarchy levels resolve to correct IDs."""
    # Simulate "Empresa 2/COMERCIAL" where both folders already exist
    resolve_side_effects = [
        _EMPRESA2_ID,  # resolve "Empresa 2" under root (None)
        _COMERCIAL_E2_ID,  # resolve "COMERCIAL" under Empresa 2
    ]
    with (
        patch(
            "pyfabricops.helpers.folders.resolve_folder",
            side_effect=resolve_side_effects,
        ) as mock_resolve,
        patch("pyfabricops.helpers.folders.create_folder"),
    ):
        create_folders_from_path_string(_WORKSPACE_ID, "Empresa 2/COMERCIAL")

    assert mock_resolve.call_args_list == [
        call(_WORKSPACE_ID, "Empresa 2", parent_folder_id=None),
        call(_WORKSPACE_ID, "COMERCIAL", parent_folder_id=_EMPRESA2_ID),
    ]


def test_create_folders_creates_missing_folder_with_correct_parent(
    mock_resolve_workspace,
) -> None:
    """A missing subfolder is created with the correct parent_folder_id."""
    # "Empresa 1" exists, "COMERCIAL" does not
    resolve_side_effects = [
        _EMPRESA1_ID,  # "Empresa 1" exists
        None,  # "COMERCIAL" does not exist under Empresa 1
    ]
    with (
        patch(
            "pyfabricops.helpers.folders.resolve_folder",
            side_effect=resolve_side_effects,
        ),
        patch(
            "pyfabricops.helpers.folders.create_folder",
            return_value={"id": _COMERCIAL_E1_ID},
        ) as mock_create,
    ):
        create_folders_from_path_string(_WORKSPACE_ID, "Empresa 1/COMERCIAL")

    mock_create.assert_called_once_with(
        _WORKSPACE_ID,
        "COMERCIAL",
        parent_folder=_EMPRESA1_ID,
        df=False,
    )


def test_create_folders_all_new_folders_chained_correctly(
    mock_resolve_workspace,
) -> None:
    """When all folders are new they are created in order with chained parent IDs."""
    resolve_side_effects = [None, None]
    create_side_effects = [
        {"id": _EMPRESA1_ID},
        {"id": _COMERCIAL_E1_ID},
    ]
    with (
        patch(
            "pyfabricops.helpers.folders.resolve_folder",
            side_effect=resolve_side_effects,
        ),
        patch(
            "pyfabricops.helpers.folders.create_folder",
            side_effect=create_side_effects,
        ) as mock_create,
    ):
        create_folders_from_path_string(_WORKSPACE_ID, "Empresa 1/COMERCIAL")

    assert mock_create.call_args_list == [
        call(_WORKSPACE_ID, "Empresa 1", parent_folder=None, df=False),
        call(_WORKSPACE_ID, "COMERCIAL", parent_folder=_EMPRESA1_ID, df=False),
    ]


def test_create_folders_none_path_returns_none(mock_resolve_workspace) -> None:
    """create_folders_from_path_string returns None for a None path."""
    result = create_folders_from_path_string(_WORKSPACE_ID, None)
    assert result is None
