"""Tests for the active value set of a variable library."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from pyfabricops.api.api import ApiResult
from pyfabricops.items.variable_libraries import (
    get_active_value_set,
    set_active_value_set,
)
from pyfabricops.utils.exceptions import RequestError, ResourceNotFoundError

_MODULE = "pyfabricops.items.variable_libraries"

WORKSPACE = "00000000-0000-4000-8000-000000000001"
LIBRARY = "00000000-0000-4000-8000-000000000002"
ENDPOINT = f"/workspaces/{WORKSPACE}/VariableLibraries/{LIBRARY}"


def library(active: str | None) -> ApiResult:
    """A variable library read back, with its active value set."""
    properties = {"activeValueSetName": active} if active else {}
    return ApiResult(True, 200, data={"id": LIBRARY, "properties": properties})


def failed() -> ApiResult:
    """A request that failed."""
    return ApiResult(False, 400, error="Bad request")


@pytest.fixture()
def api() -> Iterator[MagicMock]:
    """api_request, with the workspace and the library resolved."""
    with (
        patch(f"{_MODULE}.resolve_workspace", return_value=WORKSPACE),
        patch(f"{_MODULE}.resolve_variable_library", return_value=LIBRARY),
        patch(f"{_MODULE}.api_request") as api_request,
    ):
        yield api_request


class TestGetActiveValueSet:
    def test_returns_the_active_value_set(self, api: MagicMock) -> None:
        api.return_value = library("Production")

        assert get_active_value_set("PRD", "variables") == "Production"
        api.assert_called_once_with(ENDPOINT, return_result=True)

    def test_returns_none_on_the_default_values(self, api: MagicMock) -> None:
        api.return_value = library(None)

        assert get_active_value_set("PRD", "variables") is None

    def test_raises_when_the_library_cannot_be_read(
        self, api: MagicMock
    ) -> None:
        api.return_value = failed()

        with pytest.raises(RequestError, match="Bad request"):
            get_active_value_set("PRD", "variables")

    def test_raises_when_the_library_is_not_found(self) -> None:
        with (
            patch(f"{_MODULE}.resolve_workspace", return_value=WORKSPACE),
            patch(f"{_MODULE}.resolve_variable_library", return_value=None),
            pytest.raises(ResourceNotFoundError, match="variables"),
        ):
            get_active_value_set("PRD", "variables")


class TestSetActiveValueSet:
    def test_makes_it_active_and_reads_it_back(self, api: MagicMock) -> None:
        api.side_effect = [
            library(None),
            ApiResult(True, 200),
            library("Production"),
        ]

        assert set_active_value_set("PRD", "v", "Production") == "Production"
        assert api.call_args_list[1].kwargs == {
            "method": "patch",
            "payload": {"properties": {"activeValueSetName": "Production"}},
            "return_result": True,
        }

    def test_sends_nothing_when_it_is_active_already(
        self, api: MagicMock
    ) -> None:
        api.return_value = library("Production")

        assert set_active_value_set("PRD", "v", "Production") == "Production"
        api.assert_called_once()

    def test_returns_what_is_read_back(self, api: MagicMock) -> None:
        api.side_effect = [
            library("Test"),
            ApiResult(True, 200),
            library("Test"),
        ]

        assert set_active_value_set("PRD", "v", "Production") == "Test"

    def test_raises_when_the_change_fails(self, api: MagicMock) -> None:
        api.side_effect = [library(None), failed()]

        with pytest.raises(RequestError, match="Production"):
            set_active_value_set("PRD", "v", "Production")
