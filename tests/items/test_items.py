"""Tests for pyfabricops.items.items request payloads."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from pyfabricops.items.items import create_item, get_item_definition

_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
_ITEM_ID = "00000000-0000-0000-0000-000000000002"


@pytest.fixture()
def api_request() -> Iterator[MagicMock]:
    """Patch the API call made by the item functions."""
    with patch(
        "pyfabricops.items.items.api_request", return_value={"id": _ITEM_ID}
    ) as m:
        yield m


def test_get_item_definition_requests_the_given_format(
    api_request: MagicMock,
) -> None:
    """format is sent as a query parameter."""
    get_item_definition(_WORKSPACE_ID, _ITEM_ID, format="TMDL")

    assert api_request.call_args.kwargs["params"] == {"format": "TMDL"}


def test_get_item_definition_uses_the_service_default_format(
    api_request: MagicMock,
) -> None:
    """Without format, no query parameter is sent."""
    get_item_definition(_WORKSPACE_ID, _ITEM_ID)

    assert api_request.call_args.kwargs["params"] is None


def test_create_item_sends_the_item_type(api_request: MagicMock) -> None:
    """item_type becomes the required type property."""
    create_item(
        _WORKSPACE_ID,
        "Orders",
        {"parts": []},
        item_type="Notebook",
        df=False,
    )

    payload = api_request.call_args.kwargs["payload"]
    assert payload["type"] == "Notebook"
    assert payload["displayName"] == "Orders"


def test_create_item_without_item_type_keeps_the_old_payload(
    api_request: MagicMock,
) -> None:
    """Callers that do not pass item_type get the same payload as before."""
    create_item(_WORKSPACE_ID, "Orders", {"parts": []}, df=False)

    assert "type" not in api_request.call_args.kwargs["payload"]
