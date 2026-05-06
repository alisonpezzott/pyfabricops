"""Tests for pyfabricops.core.folders — folder hierarchy (issue #72)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pyfabricops.core.folders import get_folder_id, resolve_folder

_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"

_FOLDERS = [
    {
        "id": "aaaaaaaa-0000-0000-0000-000000000001",
        "displayName": "Empresa 1",
        "parentFolderId": None,
    },
    {
        "id": "bbbbbbbb-0000-0000-0000-000000000001",
        "displayName": "Empresa 2",
        "parentFolderId": None,
    },
    {
        "id": "cccccccc-0000-0000-0000-000000000001",
        "displayName": "COMERCIAL",
        "parentFolderId": "aaaaaaaa-0000-0000-0000-000000000001",  # under Empresa 1
    },
    {
        "id": "dddddddd-0000-0000-0000-000000000001",
        "displayName": "COMERCIAL",
        "parentFolderId": "bbbbbbbb-0000-0000-0000-000000000001",  # under Empresa 2
    },
]


@pytest.fixture()
def mock_list_folders():
    """Patch list_folders to return a controlled folder list."""
    with patch(
        "pyfabricops.core.folders.list_folders",
        return_value=_FOLDERS,
    ) as m:
        yield m


@pytest.fixture()
def mock_resolve_workspace():
    """Patch resolve_workspace to return the workspace ID unchanged."""
    with patch(
        "pyfabricops.core.folders.resolve_workspace",
        side_effect=lambda w: w,
    ) as m:
        yield m


# ---------------------------------------------------------------------------
# get_folder_id
# ---------------------------------------------------------------------------


def test_get_folder_id_unique_name_returns_id(
    mock_list_folders, mock_resolve_workspace
) -> None:
    """get_folder_id returns the correct ID for a uniquely named folder."""
    result = get_folder_id(_WORKSPACE_ID, "Empresa 1")
    assert result == "aaaaaaaa-0000-0000-0000-000000000001"


def test_get_folder_id_no_parent_filter_returns_first_match(
    mock_list_folders, mock_resolve_workspace
) -> None:
    """get_folder_id without parent_folder_id returns the first COMERCIAL found."""
    result = get_folder_id(_WORKSPACE_ID, "COMERCIAL")
    # First occurrence is the one under Empresa 1
    assert result == "cccccccc-0000-0000-0000-000000000001"


def test_get_folder_id_with_parent_folder_id_returns_correct_folder(
    mock_list_folders, mock_resolve_workspace
) -> None:
    """get_folder_id scoped to Empresa 2 returns Empresa 2's COMERCIAL."""
    result = get_folder_id(
        _WORKSPACE_ID,
        "COMERCIAL",
        parent_folder_id="bbbbbbbb-0000-0000-0000-000000000001",
    )
    assert result == "dddddddd-0000-0000-0000-000000000001"


def test_get_folder_id_with_parent_folder_id_empresa1(
    mock_list_folders, mock_resolve_workspace
) -> None:
    """get_folder_id scoped to Empresa 1 returns Empresa 1's COMERCIAL."""
    result = get_folder_id(
        _WORKSPACE_ID,
        "COMERCIAL",
        parent_folder_id="aaaaaaaa-0000-0000-0000-000000000001",
    )
    assert result == "cccccccc-0000-0000-0000-000000000001"


def test_get_folder_id_returns_none_when_name_not_found(
    mock_list_folders, mock_resolve_workspace
) -> None:
    """get_folder_id returns None when no folder matches the name."""
    result = get_folder_id(_WORKSPACE_ID, "FINANCEIRO")
    assert result is None


def test_get_folder_id_with_parent_filter_no_match_returns_none(
    mock_list_folders, mock_resolve_workspace
) -> None:
    """get_folder_id returns None when name exists but not under the given parent."""
    # "Empresa 1" is a root folder, not a child of Empresa 2
    result = get_folder_id(
        _WORKSPACE_ID,
        "Empresa 1",
        parent_folder_id="bbbbbbbb-0000-0000-0000-000000000001",
    )
    assert result is None


# ---------------------------------------------------------------------------
# resolve_folder
# ---------------------------------------------------------------------------


def test_resolve_folder_returns_uuid_directly(mock_resolve_workspace) -> None:
    """resolve_folder returns the UUID as-is without calling get_folder_id."""
    valid_uuid = "cccccccc-0000-0000-0000-000000000001"
    with patch("pyfabricops.core.folders.get_folder_id") as mock_get:
        result = resolve_folder(_WORKSPACE_ID, valid_uuid)
    assert result == valid_uuid
    mock_get.assert_not_called()


def test_resolve_folder_delegates_to_get_folder_id_by_name(
    mock_resolve_workspace,
) -> None:
    """resolve_folder delegates name resolution to get_folder_id."""
    with patch(
        "pyfabricops.core.folders.get_folder_id",
        return_value="cccccccc-0000-0000-0000-000000000001",
    ) as mock_get:
        result = resolve_folder(_WORKSPACE_ID, "COMERCIAL")
    assert result == "cccccccc-0000-0000-0000-000000000001"
    mock_get.assert_called_once_with(
        _WORKSPACE_ID, "COMERCIAL", parent_folder_id=None
    )


def test_resolve_folder_propagates_parent_folder_id(
    mock_resolve_workspace,
) -> None:
    """resolve_folder passes parent_folder_id through to get_folder_id."""
    parent_id = "bbbbbbbb-0000-0000-0000-000000000001"
    with patch(
        "pyfabricops.core.folders.get_folder_id",
        return_value="dddddddd-0000-0000-0000-000000000001",
    ) as mock_get:
        result = resolve_folder(
            _WORKSPACE_ID, "COMERCIAL", parent_folder_id=parent_id
        )
    assert result == "dddddddd-0000-0000-0000-000000000001"
    mock_get.assert_called_once_with(
        _WORKSPACE_ID, "COMERCIAL", parent_folder_id=parent_id
    )
