"""Tests for refresh_semantic_model_and_wait."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pyfabricops.api.api import ApiResult
from pyfabricops.helpers.semantic_models import refresh_semantic_model_and_wait
from pyfabricops.utils.exceptions import RequestError, ResourceNotFoundError

_MODULE = "pyfabricops.helpers.semantic_models"

WORKSPACE = "00000000-0000-4000-8000-000000000001"
MODEL = "00000000-0000-4000-8000-000000000002"
ENDPOINT = f"/groups/{WORKSPACE}/datasets/{MODEL}/refreshes"

STARTED = ApiResult(True, 202)


def history(*entries: tuple[str, str]) -> ApiResult:
    """The refresh history, as (requestId, status), latest first."""
    return ApiResult(
        True,
        200,
        data={"value": [{"requestId": r, "status": s} for r, s in entries]},
    )


@pytest.fixture()
def api() -> Iterator[MagicMock]:
    """api_request, with the model resolved and no real waiting."""
    clock = iter(range(0, 100_000, 15))
    with (
        patch(f"{_MODULE}.resolve_workspace", return_value=WORKSPACE),
        patch(f"{_MODULE}.resolve_semantic_model", return_value=MODEL),
        patch(f"{_MODULE}.time.sleep"),
        patch(f"{_MODULE}.time.monotonic", side_effect=lambda: next(clock)),
        patch(f"{_MODULE}.api_request") as api_request,
    ):
        yield api_request


def posts(api: MagicMock) -> list[Any]:
    """The calls that started a refresh."""
    return [c for c in api.call_args_list if c.kwargs.get("method") == "post"]


def test_waits_for_the_new_refresh_to_end(api: MagicMock) -> None:
    api.side_effect = [
        history(("old", "Completed")),
        STARTED,
        history(("old", "Completed")),
        history(("new", "Unknown")),
        history(("new", "Completed")),
    ]

    ended = refresh_semantic_model_and_wait("PRD", "Sales")

    assert ended == {"requestId": "new", "status": "Completed"}
    assert posts(api)[0].args == (ENDPOINT,)
    assert posts(api)[0].kwargs["payload"] == {
        "notifyOption": "NoNotification"
    }
    assert posts(api)[0].kwargs["audience"] == "powerbi"


def test_a_failed_refresh_is_returned(api: MagicMock) -> None:
    api.side_effect = [history(), STARTED, history(("new", "Failed"))]

    ended = refresh_semantic_model_and_wait("PRD", "Sales")

    assert ended["status"] == "Failed"


def test_options_make_an_enhanced_refresh(api: MagicMock) -> None:
    api.side_effect = [history(), STARTED, history(("new", "Completed"))]

    refresh_semantic_model_and_wait(
        "PRD", "Sales", options={"type": "Full", "commitMode": "Transactional"}
    )

    assert posts(api)[0].kwargs["payload"] == {
        "notifyOption": "NoNotification",
        "type": "Full",
        "commitMode": "Transactional",
    }


def test_a_running_refresh_is_waited_for_first(api: MagicMock) -> None:
    api.side_effect = [
        history(("running", "Unknown")),
        history(("running", "Unknown")),
        history(("running", "Completed")),
        STARTED,
        history(("new", "Completed")),
    ]

    ended = refresh_semantic_model_and_wait("PRD", "Sales")

    assert ended["requestId"] == "new"
    # The refresh started only after the running one ended.
    assert api.call_args_list.index(posts(api)[0]) == 3


def test_raises_when_the_refresh_does_not_start(api: MagicMock) -> None:
    api.side_effect = [history(), ApiResult(False, 400, error="No capacity")]

    with pytest.raises(RequestError, match="No capacity"):
        refresh_semantic_model_and_wait("PRD", "Sales")


def test_raises_when_the_history_cannot_be_read(api: MagicMock) -> None:
    api.side_effect = [ApiResult(False, 403, error="Forbidden")]

    with pytest.raises(RequestError, match="Forbidden"):
        refresh_semantic_model_and_wait("PRD", "Sales")


def test_raises_on_timeout(api: MagicMock) -> None:
    api.side_effect = [history(), STARTED] + [history(("new", "Unknown"))] * 20

    with pytest.raises(TimeoutError):
        refresh_semantic_model_and_wait("PRD", "Sales", timeout=100)


def test_raises_when_the_model_is_not_found() -> None:
    with (
        patch(f"{_MODULE}.resolve_workspace", return_value=WORKSPACE),
        patch(f"{_MODULE}.resolve_semantic_model", return_value=None),
        pytest.raises(ResourceNotFoundError, match="Sales"),
    ):
        refresh_semantic_model_and_wait("PRD", "Sales")
