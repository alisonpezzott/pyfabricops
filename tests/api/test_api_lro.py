"""Tests for LRO polling, throttling and pagination in pyfabricops.api.api."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from pyfabricops.api import api
from pyfabricops.api.api import ApiResult, api_request, set_lro_options
from pyfabricops.utils.exceptions import InvalidParameterError

_OPERATION_URL = "https://api.fabric.microsoft.com/v1/operations/op-1"
_RESULT_URL = f"{_OPERATION_URL}/result"


def _response(
    status_code: int,
    body: Any = None,
    headers: dict[str, str] | None = None,
) -> requests.Response:
    """Build a real requests.Response with a JSON body."""
    response = requests.Response()
    response.status_code = status_code
    response._content = b"" if body is None else json.dumps(body).encode()
    response.headers.update(headers or {})
    response.url = "https://api.fabric.microsoft.com/v1/test"
    return response


def _accepted() -> requests.Response:
    """A 202 response pointing to the operation state."""
    return _response(
        202, headers={"Location": _OPERATION_URL, "Retry-After": "30"}
    )


def _api_result(endpoint: str, **kwargs: Any) -> ApiResult:
    """Call api_request with return_result=True and narrow the type."""
    result = api_request(endpoint, return_result=True, **kwargs)
    assert isinstance(result, ApiResult)
    return result


@pytest.fixture(autouse=True)
def lro_options(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Give every test fresh LRO options."""
    monkeypatch.setattr(api, "_lro_options", api._LroOptions())
    yield


@pytest.fixture(autouse=True)
def token() -> Iterator[MagicMock]:
    """Skip authentication."""
    with patch(
        "pyfabricops.api.api._get_token",
        return_value={"access_token": "token"},
    ) as m:
        yield m


@pytest.fixture()
def http() -> Iterator[MagicMock]:
    """Patch the HTTP layer; tests set side_effect to the responses."""
    with patch("pyfabricops.api.api.requests.request") as m:
        yield m


@pytest.fixture()
def clock() -> Iterator[MagicMock]:
    """Patch the time module used by the API layer only."""
    with patch("pyfabricops.api.api.time") as m:
        m.monotonic.return_value = 0.0
        yield m


# ---------------------------------------------------------------------------
# Long-running operations
# ---------------------------------------------------------------------------


def test_lro_already_succeeded_fetches_the_result(
    http: MagicMock, clock: MagicMock
) -> None:
    """An LRO that already succeeded on the first check still returns its result."""
    definition = {"definition": {"parts": [{"path": ".platform"}]}}
    http.side_effect = [
        _accepted(),
        _response(
            200, {"status": "Succeeded"}, headers={"Location": _RESULT_URL}
        ),
        _response(200, definition),
    ]

    result = api_request("/getDefinition", method="post", support_lro=True)

    assert result == definition
    assert http.call_args_list[2].kwargs["url"] == _RESULT_URL
    clock.sleep.assert_not_called()


def test_lro_without_result_counts_as_success(
    http: MagicMock, clock: MagicMock
) -> None:
    """An operation without a result succeeds with no data."""
    http.side_effect = [
        _accepted(),
        _response(200, {"status": "Succeeded"}),
        _response(400, {"errorCode": "OperationHasNoResult"}),
    ]

    result = _api_result("/updateDefinition", method="post", support_lro=True)

    assert result.success is True
    assert result.data is None
    assert http.call_args_list[2].kwargs["url"] == _RESULT_URL


def test_lro_polls_with_backoff_until_succeeded(
    http: MagicMock, clock: MagicMock
) -> None:
    """Checks back off 1 s, 2 s, 4 s instead of waiting Retry-After."""
    http.side_effect = [
        _accepted(),
        _response(200, {"status": "NotStarted"}),
        _response(200, {"status": "Running"}),
        _response(200, {"status": "Running"}),
        _response(
            200, {"status": "Succeeded"}, headers={"Location": _RESULT_URL}
        ),
        _response(200, {"id": "item-1"}),
    ]

    result = api_request("/items", method="post", support_lro=True)

    assert result == {"id": "item-1"}
    assert [c.args[0] for c in clock.sleep.call_args_list] == [1.0, 2.0, 4.0]


def test_lro_backoff_is_capped_by_max_poll_interval(
    http: MagicMock, clock: MagicMock
) -> None:
    """The wait between checks never exceeds max_poll_interval."""
    set_lro_options(max_poll_interval=2)
    http.side_effect = [
        _accepted(),
        _response(200, {"status": "Running"}),
        _response(200, {"status": "Running"}),
        _response(200, {"status": "Running"}),
        _response(200, {"status": "Succeeded"}),
        _response(400),
    ]

    api_request("/items", method="post", support_lro=True)

    assert [c.args[0] for c in clock.sleep.call_args_list] == [1.0, 2.0, 2.0]


def test_failed_lro_is_not_reported_as_success(
    http: MagicMock, clock: MagicMock
) -> None:
    """A failed LRO returns None, not the operation state."""
    state = {
        "status": "Failed",
        "error": {"errorCode": "CorruptedPayload", "message": "Bad part."},
    }
    http.side_effect = [_accepted(), _response(200, state)]

    assert api_request("/items", method="post", support_lro=True) is None


def test_failed_lro_result_describes_the_error(
    http: MagicMock, clock: MagicMock
) -> None:
    """The failure carries the service error code and message."""
    state = {
        "status": "Failed",
        "error": {"errorCode": "CorruptedPayload", "message": "Bad part."},
    }
    http.side_effect = [_accepted(), _response(200, state)]

    result = _api_result("/items", method="post", support_lro=True)

    assert result.success is False
    assert "CorruptedPayload - Bad part." in (result.error or "")


def test_failed_lro_result_gives_the_details_of_the_error(
    http: MagicMock, clock: MagicMock
) -> None:
    """The moreDetails messages follow, without Fabric's <pi> markers."""
    state = {
        "status": "Failed",
        "error": {
            "errorCode": "InvalidInput",
            "message": "The request has an invalid input",
            "moreDetails": [
                {
                    "errorCode": "InvalidParameter",
                    "message": "Bad <pi>A</pi>.",
                },
                {"errorCode": "NoMessage"},
            ],
        },
    }
    http.side_effect = [_accepted(), _response(200, state)]

    result = _api_result("/items", method="post", support_lro=True)

    assert result.error == (
        "LRO failed with status: Failed (InvalidInput - The request has an "
        "invalid input - Bad A.)"
    )


def test_lro_times_out(http: MagicMock, clock: MagicMock) -> None:
    """An operation still running at the deadline is reported as failed."""
    set_lro_options(timeout=10)
    clock.monotonic.side_effect = [0.0, 5.0, 11.0]
    http.side_effect = [
        _accepted(),
        _response(200, {"status": "Running"}),
        _response(200, {"status": "Running"}),
    ]

    result = _api_result("/items", method="post", support_lro=True)

    assert result.success is False
    assert "timed out after 10s" in (result.error or "")
    assert "may still be running" in (result.error or "")


def test_lro_tolerates_a_transient_status_check_failure(
    http: MagicMock, clock: MagicMock
) -> None:
    """One failed status check does not abandon the operation."""
    http.side_effect = [
        _accepted(),
        _response(502),
        _response(
            200, {"status": "Succeeded"}, headers={"Location": _RESULT_URL}
        ),
        _response(200, {"id": "item-1"}),
    ]

    result = api_request("/items", method="post", support_lro=True)

    assert result == {"id": "item-1"}
    clock.sleep.assert_called_once_with(1.0)


def test_lro_gives_up_after_repeated_status_check_failures(
    http: MagicMock, clock: MagicMock
) -> None:
    """Consecutive failed status checks are bounded."""
    http.side_effect = [_accepted()] + [
        _response(502) for _ in range(api._LRO_MAX_CHECK_FAILURES)
    ]

    result = _api_result("/items", method="post", support_lro=True)

    assert result.success is False
    assert "Failed to check LRO status" in (result.error or "")
    assert http.call_count == 1 + api._LRO_MAX_CHECK_FAILURES


def test_set_lro_options_rejects_non_positive_values() -> None:
    """Timeouts and intervals must be greater than zero."""
    with pytest.raises(InvalidParameterError):
        set_lro_options(timeout=0)
    with pytest.raises(InvalidParameterError):
        set_lro_options(max_poll_interval=-1)


# ---------------------------------------------------------------------------
# Throttling (429)
# ---------------------------------------------------------------------------


def test_throttled_request_is_retried_after_retry_after(
    http: MagicMock, clock: MagicMock
) -> None:
    """A 429 is retried after the Retry-After seconds."""
    http.side_effect = [
        _response(429, headers={"Retry-After": "2"}),
        _response(200, {"id": "ws-1"}),
    ]

    assert api_request("/workspaces/ws-1") == {"id": "ws-1"}
    clock.sleep.assert_called_once_with(2.0)


def test_throttled_request_is_not_retried_beyond_the_wait_limit(
    http: MagicMock, clock: MagicMock
) -> None:
    """A Retry-After above the limit returns the 429 without waiting."""
    http.side_effect = [_response(429, headers={"Retry-After": "3600"})]

    assert api_request("/workspaces/ws-1") is None
    assert http.call_count == 1
    clock.sleep.assert_not_called()


def test_throttled_request_gives_up_after_max_retries(
    http: MagicMock, clock: MagicMock
) -> None:
    """Throttling retries are bounded."""
    http.side_effect = [
        _response(429, headers={"Retry-After": "1"})
        for _ in range(api._THROTTLE_MAX_RETRIES + 1)
    ]

    result = _api_result("/workspaces/ws-1")

    assert result.status_code == 429
    assert http.call_count == api._THROTTLE_MAX_RETRIES + 1
    assert clock.sleep.call_count == api._THROTTLE_MAX_RETRIES


def test_throttled_lro_poll_is_retried(
    http: MagicMock, clock: MagicMock
) -> None:
    """Status checks of an LRO are also retried on 429."""
    http.side_effect = [
        _accepted(),
        _response(429, headers={"Retry-After": "3"}),
        _response(
            200, {"status": "Succeeded"}, headers={"Location": _RESULT_URL}
        ),
        _response(200, {"id": "item-1"}),
    ]

    assert api_request("/items", method="post", support_lro=True) == {
        "id": "item-1"
    }
    clock.sleep.assert_called_once_with(3.0)


# ---------------------------------------------------------------------------
# Transient failures
# ---------------------------------------------------------------------------


def test_a_get_is_retried_after_a_transient_failure(
    http: MagicMock, clock: MagicMock
) -> None:
    """Reading is safe to repeat, so a 503 is tried again."""
    http.side_effect = [_response(503), _response(200, {"id": "ws-1"})]

    assert api_request("/workspaces/ws-1") == {"id": "ws-1"}
    clock.sleep.assert_called_once_with(2.0)


def test_a_get_is_retried_after_a_connection_error(
    http: MagicMock, clock: MagicMock
) -> None:
    """A dropped connection is transient too."""
    http.side_effect = [
        requests.exceptions.ConnectionError("reset by peer"),
        _response(200, {"id": "ws-1"}),
    ]

    assert api_request("/workspaces/ws-1") == {"id": "ws-1"}
    assert http.call_count == 2


def test_a_post_is_not_retried_unless_marked_safe(
    http: MagicMock, clock: MagicMock
) -> None:
    """Creating twice could create twice: the failure goes back as it is."""
    http.side_effect = [_response(503)]

    result = _api_result("/items", method="post")

    assert result.status_code == 503
    assert http.call_count == 1
    clock.sleep.assert_not_called()


def test_a_post_marked_safe_is_retried_with_backoff(
    http: MagicMock, clock: MagicMock
) -> None:
    """Waits of 2, then 4 seconds."""
    http.side_effect = [
        _response(500),
        _response(502),
        _response(200, {"id": "item-1"}),
    ]

    result = _api_result("/items/item-1/move", method="post", retry=True)

    assert result.data == {"id": "item-1"}
    assert [c.args[0] for c in clock.sleep.call_args_list] == [2.0, 4.0]


def test_an_error_fabric_marks_retriable_is_retried(
    http: MagicMock, clock: MagicMock
) -> None:
    """Fabric says so in the error body."""
    busy = {"errorCode": "ServiceBusy", "isRetriable": True}
    http.side_effect = [_response(409, busy), _response(200, {"id": "ws-1"})]

    assert api_request("/workspaces/ws-1") == {"id": "ws-1"}


def test_an_error_not_marked_retriable_is_not_retried(
    http: MagicMock, clock: MagicMock
) -> None:
    """A bad request stays bad."""
    invalid = {"errorCode": "InvalidInput", "isRetriable": False}
    http.side_effect = [_response(400, invalid)]

    assert _api_result("/workspaces/ws-1").status_code == 400
    assert http.call_count == 1


def test_a_transient_failure_waits_its_retry_after(
    http: MagicMock, clock: MagicMock
) -> None:
    """The service's Retry-After wins over the backoff."""
    http.side_effect = [
        _response(503, headers={"Retry-After": "7"}),
        _response(200, {"id": "ws-1"}),
    ]

    assert api_request("/workspaces/ws-1") == {"id": "ws-1"}
    clock.sleep.assert_called_once_with(7.0)


def test_transient_retries_give_up_after_three(
    http: MagicMock, clock: MagicMock
) -> None:
    """The last failure goes back to the caller."""
    http.side_effect = [
        _response(503) for _ in range(api._TRANSIENT_MAX_RETRIES + 1)
    ]

    result = _api_result("/workspaces/ws-1")

    assert result.status_code == 503
    assert http.call_count == api._TRANSIENT_MAX_RETRIES + 1
    assert [c.args[0] for c in clock.sleep.call_args_list] == [2.0, 4.0, 8.0]


def test_a_connection_error_that_persists_is_reported(
    http: MagicMock, clock: MagicMock
) -> None:
    """After the retries, as before: a failed result, not an exception."""
    http.side_effect = requests.exceptions.ConnectionError("down")

    result = _api_result("/workspaces/ws-1")

    assert (result.success, result.status_code) == (False, 503)
    assert http.call_count == api._TRANSIENT_MAX_RETRIES + 1


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def test_pagination_follows_the_continuation_uri(
    http: MagicMock, clock: MagicMock
) -> None:
    """The next page comes from continuationUri, which keeps the query."""
    next_uri = (
        "https://api.fabric.microsoft.com/v1/workspaces/ws-1/items"
        "?type=Notebook&continuationToken=abc"
    )
    http.side_effect = [
        _response(
            200,
            {
                "value": [{"id": "1"}],
                "continuationToken": "abc",
                "continuationUri": next_uri,
            },
        ),
        _response(200, {"value": [{"id": "2"}]}),
    ]

    result = api_request("/workspaces/ws-1/items", support_pagination=True)

    assert result == [{"id": "1"}, {"id": "2"}]
    assert http.call_args_list[1].kwargs["url"] == next_uri


def test_pagination_without_continuation_uri_encodes_the_token(
    http: MagicMock, clock: MagicMock
) -> None:
    """Without continuationUri the token is URL-encoded."""
    http.side_effect = [
        _response(200, {"value": [{"id": "1"}], "continuationToken": "a+b="}),
        _response(200, {"value": [{"id": "2"}]}),
    ]

    result = api_request("/workspaces/ws-1/items", support_pagination=True)

    assert result == [{"id": "1"}, {"id": "2"}]
    assert (
        http.call_args_list[1]
        .kwargs["url"]
        .endswith("/workspaces/ws-1/items?continuationToken=a%2Bb%3D")
    )
