import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, NamedTuple
from urllib.parse import urlencode

import requests

from ..utils.exceptions import (
    AuthenticationError,
    InvalidParameterError,
)
from ..utils.logging import get_logger
from .auth import _get_token
from .scopes import FABRIC_API, GRAPH_API, POWERBI_API

logger = get_logger(__name__)

# A 429 response is retried after the Retry-After seconds the service
# returns, up to _THROTTLE_MAX_RETRIES times. Longer waits are not
# attempted: the 429 goes back to the caller instead.
_THROTTLE_MAX_RETRIES = 3
_THROTTLE_MAX_WAIT_SECONDS = 60.0
_THROTTLE_DEFAULT_WAIT_SECONDS = 10.0

# Consecutive failed LRO status checks (network errors, 5xx) tolerated
# before the operation is reported as failed.
_LRO_MAX_CHECK_FAILURES = 3


@dataclass
class _LroOptions:
    """Polling settings for long-running operations (LRO)."""

    timeout: float = 600.0
    max_poll_interval: float = 5.0


_lro_options = _LroOptions()


def set_lro_options(
    *,
    timeout: float | None = None,
    max_poll_interval: float | None = None,
) -> None:
    """
    Configure how long-running operations (LRO) are polled.

    The first status check runs as soon as the service accepts the request.
    Later checks wait 1 s, 2 s, 4 s and so on, up to ``max_poll_interval``,
    until ``timeout`` seconds have passed. The ``Retry-After`` header of an
    accepted operation is not used as the interval: the Fabric samples show
    30 s, which would add half a minute to every item of a deployment.

    Args:
        timeout (float, optional): Seconds to wait for an operation before
            reporting it as failed. The operation may still complete on the
            service side. Defaults to 600.
        max_poll_interval (float, optional): Maximum seconds between two
            status checks. Defaults to 5.

    Raises:
        InvalidParameterError: If a value is not greater than zero.

    Examples:
        ```python
        set_lro_options(timeout=1800)
        set_lro_options(max_poll_interval=10)
        ```
    """
    for name, value in (
        ("timeout", timeout),
        ("max_poll_interval", max_poll_interval),
    ):
        if value is not None and value <= 0:
            raise InvalidParameterError(f"{name} must be greater than zero.")

    if timeout is not None:
        _lro_options.timeout = float(timeout)
    if max_poll_interval is not None:
        _lro_options.max_poll_interval = float(max_poll_interval)


def _sanitize_headers_for_log(headers: dict[str, str] | None) -> dict:
    """Return a copy of headers with sensitive values redacted for logs."""
    if not headers:
        return {}

    redacted = dict(headers)
    for key in list(redacted.keys()):
        if key.lower() == "authorization":
            auth_value = redacted.get(key)
            if isinstance(auth_value, str) and auth_value.startswith(
                "Bearer "
            ):
                redacted[key] = "Bearer ***REDACTED***"
            else:
                redacted[key] = "***REDACTED***"

    return redacted


class ApiResult(NamedTuple):
    """A named tuple to encapsulate the result of an API request."""

    success: bool
    status_code: int
    data: Any | None = None
    headers: dict | None = None
    error: str | None = None
    request_kwargs: dict | None = None


def _header(headers: Mapping[str, str] | None, name: str) -> str | None:
    """Return a header value, matching the name case-insensitively."""
    if not headers:
        return None

    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return None


def _retry_after_seconds(headers: Mapping[str, str] | None) -> float | None:
    """Return the ``Retry-After`` header in seconds, or None if absent."""
    value = _header(headers, "Retry-After")
    if value is None:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        return None


def _send(**request_kwargs: Any) -> requests.Response:
    """
    Send an HTTP request, waiting out throttling as the service instructs.

    A ``429 Too Many Requests`` is retried after the ``Retry-After`` seconds
    the service returns, up to ``_THROTTLE_MAX_RETRIES`` times. A wait above
    ``_THROTTLE_MAX_WAIT_SECONDS`` is not attempted: the 429 response is
    returned to the caller.
    """
    response = requests.request(**request_kwargs)
    for attempt in range(1, _THROTTLE_MAX_RETRIES + 1):
        if response.status_code != 429:
            break

        wait = _retry_after_seconds(response.headers)
        if wait is None:
            wait = _THROTTLE_DEFAULT_WAIT_SECONDS
        if wait > _THROTTLE_MAX_WAIT_SECONDS:
            logger.warning(
                f"Throttled (429): Retry-After {wait:g}s exceeds the "
                f"{_THROTTLE_MAX_WAIT_SECONDS:g}s limit, not retrying."
            )
            break

        logger.warning(
            f"Throttled (429): retrying in {wait:g}s "
            f"(attempt {attempt}/{_THROTTLE_MAX_RETRIES})."
        )
        time.sleep(wait)
        response = requests.request(**request_kwargs)

    return response


def _base_api(
    endpoint: str,
    *,
    content_type: str = "application/json",
    payload: dict | None = None,
    data: dict | None = None,
    params: dict | None = None,
    audience: Literal["fabric", "powerbi", "graph"] = "fabric",
    credential_type: Literal["spn", "user"] | None = None,
    method: Literal["get", "post", "patch", "delete"] = "get",
    return_raw: bool = False,
    **kwargs,
) -> ApiResult:
    """
    Base API function to the Microsoft Fabric or Power BI API.
    """
    # Base URL selection based on audience
    if audience == "graph":
        base_url = GRAPH_API
    elif audience == "fabric":
        base_url = FABRIC_API
    else:
        base_url = POWERBI_API

    # Construct the full URL
    url = f"{base_url}{endpoint}"

    # Append parameters if provided (supports dict now)
    if params:
        if isinstance(params, dict):
            query_str = urlencode(params)
            url += f"?{query_str}"
        else:
            raise InvalidParameterError(
                "Query parameters must be a dictionary."
            )

    # Validate that only one of payload or data is provided
    if payload is not None and data is not None:
        raise InvalidParameterError(
            "Cannot provide both 'payload' and 'data' parameters. Use one or the other."
        )

    # Initialize payload if None
    if payload is None:
        payload = {}

    # Retrieve the access token
    token = _get_token(audience=audience, credential_type=credential_type)

    # Validate the token and payload
    if not token:
        raise AuthenticationError(
            "Failed to retrieve token. Ensure that the authentication is set up correctly."
        )

    # Extract the access token from the token response
    access_token = token.get("access_token")

    # Build the headers for the request
    headers = {
        "Content-Type": content_type,
        "Authorization": f"Bearer {access_token}",
    }

    # Validate the payload
    if not isinstance(payload, dict):
        raise InvalidParameterError("Payload must be a dictionary.")

    # Request execution - modified to support data
    request_kwargs = {
        "method": method.upper(),
        "url": url,
        "headers": headers,
    }

    # Handle data vs json
    if data is not None:
        request_kwargs["data"] = data
    else:
        request_kwargs["json"] = payload

    # Log the request for debugging
    logger.debug(f"Making {method.upper()} request to {url}")
    logger.debug(f"Headers: {_sanitize_headers_for_log(headers)}")
    if payload and payload != {}:
        logger.debug(f"Payload: {payload}")

    # Request execution with proper error handling
    try:
        response = _send(**request_kwargs)
    except requests.exceptions.ConnectionError as e:
        return ApiResult(
            success=False,
            status_code=503,
            data=None,
            headers=None,
            error=f"Connection error: {str(e)}",
            request_kwargs=request_kwargs,
        )
    except requests.exceptions.RequestException as e:
        return ApiResult(
            success=False,
            status_code=500,
            data=None,
            headers=None,
            error=f"Request failed: {str(e)}",
            request_kwargs=request_kwargs,
        )

    # Log response status
    logger.debug(f"Response status: {response.status_code}")

    if return_raw:
        return response
    else:
        # Parse JSON safely
        try:
            json_data = (
                response.json() if response.ok and response.content else None
            )
        except ValueError:
            json_data = None

        return ApiResult(
            success=response.ok,
            status_code=response.status_code,
            data=json_data,
            headers=dict(response.headers) if response.ok else None,
            error=response.text if not response.ok else None,
            request_kwargs=request_kwargs,
        )


def _pagination_handler(api_result: ApiResult) -> ApiResult:
    """Handle paginated responses with continuation tokens."""
    # Check for continuation token
    if not api_result.data or "continuationToken" not in api_result.data:
        return api_result

    continuation_token = api_result.data.get("continuationToken")
    continuation_uri = api_result.data.get("continuationUri")
    data = list(api_result.data.get("value", []))

    # Get original request kwargs for subsequent requests
    original_kwargs = api_result.request_kwargs or {}
    headers = original_kwargs.get("headers", {})
    base_url = original_kwargs.get("url", "").split("?")[0]

    # Continue fetching data until no continuation token is left
    while continuation_token:
        # Prefer the URI the service returns: it keeps the original query.
        next_url = (
            continuation_uri
            or f"{base_url}?{urlencode({'continuationToken': continuation_token})}"
        )
        try:
            response = _send(
                method="GET",  # Pagination is always GET
                url=next_url,
                headers=headers,
            )
            response.raise_for_status()
            response_data = response.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            logger.error(f"Pagination failed: {str(e)}")
            # Return what we have so far
            break

        data.extend(response_data.get("value", []))
        continuation_token = response_data.get("continuationToken")
        continuation_uri = response_data.get("continuationUri")

    return ApiResult(
        success=True,
        status_code=200,
        data={"value": data},
        headers=api_result.headers,
        error=None,
        request_kwargs=api_result.request_kwargs,
    )


def _lro_error(status: str, state: dict[str, Any]) -> str:
    """Describe a failed LRO from its state payload."""
    error = state.get("error") or {}
    detail = " - ".join(
        str(part)
        for part in (error.get("errorCode"), error.get("message"))
        if part
    )
    message = f"LRO failed with status: {status}"
    return f"{message} ({detail})" if detail else message


def _lro_result(
    state_response: requests.Response,
    operation_url: str,
    headers: dict[str, str] | None,
) -> ApiResult:
    """
    Fetch the result of a succeeded LRO.

    Fabric advertises the result URL in the ``Location`` header of the
    succeeded state, with ``{operation}/result`` as the fallback. Not every
    operation has a result, so a missing one still counts as success.
    """
    result_url = _header(state_response.headers, "Location")
    if not result_url or result_url == operation_url:
        result_url = f"{operation_url}/result"

    try:
        response = _send(method="GET", url=result_url, headers=headers)
    except requests.exceptions.RequestException as e:
        logger.debug(f"LRO succeeded, but its result could not be read: {e}")
        return ApiResult(success=True, status_code=200)

    if response.ok and response.content:
        try:
            return ApiResult(
                success=True,
                status_code=response.status_code,
                data=response.json(),
                headers=dict(response.headers),
            )
        except ValueError as e:
            logger.debug(f"LRO result is not JSON: {e}")

    logger.debug(f"LRO succeeded without a result ({response.status_code}).")
    return ApiResult(success=True, status_code=200)


def _lro_handler(api_result: ApiResult) -> ApiResult:
    """
    Poll a long-running operation (LRO) until it finishes.

    The first status check runs right away; later checks back off from 1 s
    up to the configured maximum interval, until the configured timeout
    (see ``set_lro_options``). On success, the operation result is fetched
    when the operation has one.
    """
    operation_url = _header(api_result.headers, "Location")
    if not operation_url:
        return api_result

    logger.debug(f"Long-running operation detected at {operation_url}")

    headers = (api_result.request_kwargs or {}).get("headers")
    logger.debug(
        f"Headers for LRO request: {_sanitize_headers_for_log(headers)}"
    )

    deadline = time.monotonic() + _lro_options.timeout
    interval = 1.0
    failures = 0

    while True:
        try:
            state_response = _send(
                method="GET", url=operation_url, headers=headers
            )
            state_response.raise_for_status()
            state = state_response.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            failures += 1
            if (
                failures >= _LRO_MAX_CHECK_FAILURES
                or time.monotonic() >= deadline
            ):
                return ApiResult(
                    success=False,
                    status_code=500,
                    error=f"Failed to check LRO status: {str(e)}",
                )
            logger.warning(
                f"LRO status check failed "
                f"({failures}/{_LRO_MAX_CHECK_FAILURES}), retrying: {e}"
            )
            time.sleep(interval)
            interval = min(interval * 2, _lro_options.max_poll_interval)
            continue

        failures = 0
        if not isinstance(state, dict):
            state = {}
        status = state.get("status", "Unknown")
        logger.debug(f"LRO status: {status}")

        if status == "Succeeded":
            return _lro_result(state_response, operation_url, headers)

        if status in ("Failed", "Undefined"):
            return ApiResult(
                success=False,
                status_code=state_response.status_code,
                data=state,
                headers=dict(state_response.headers),
                error=_lro_error(status, state),
            )

        if status not in ("NotStarted", "Running"):
            logger.warning(f"Unknown LRO status: {status}")

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return ApiResult(
                success=False,
                status_code=500,
                error=(
                    f"LRO timed out after {_lro_options.timeout:g}s "
                    f"(last status: {status}); it may still be running."
                ),
            )

        time.sleep(min(interval, remaining))
        interval = min(interval * 2, _lro_options.max_poll_interval)


def api_request(
    endpoint: str,
    *,
    content_type: str = "application/json",
    payload: dict | None = None,
    data: dict | None = None,
    params: dict | None = None,
    audience: Literal["fabric", "powerbi", "graph"] = "fabric",
    credential_type: Literal["spn", "user"] | None = None,
    method: Literal["get", "post", "patch", "delete"] = "get",
    support_pagination: bool | None = False,
    support_lro: bool | None = False,
    return_raw: bool = False,
    return_result: bool = False,
    **kwargs,
) -> list[dict[str, Any]] | dict[str, Any] | ApiResult | None:
    """
    Makes a request to the Microsoft Fabric or Power BI API.
    This function supports various HTTP methods and can handle both JSON payloads and form data.
    It automatically retrieves an access token based on the specified audience and credential type.
    It supports pagination by allowing query parameters to be passed in as a dictionary.
    It also supports long-running operations (LRO) by checking the response headers for a 'Location' header.
    It can return the raw response object or parsed JSON data based on the `return_raw` parameter.
    Throttled requests (429) are retried after the `Retry-After` seconds the service returns.

    Args:
        endpoint (str): The API endpoint to call.
        content_type (str): The content type of the request. Defaults to "application/json".
        payload (Optional[dict]): The JSON payload to send with the request. Defaults to None.
        data (Optional[dict]): The data to send with the request. Defaults to None.
        params (Optional[dict]): Query parameters to append to the URL. Defaults to None.
        audience (Literal["fabric", "powerbi", "graph"]): The API audience to target. Defaults to "fabric".
        credential_type (Literal["spn", "user"]): The type of credentials to use for authentication. Defaults to "spn".
        method (Literal["get", "post", "patch", "delete"]): The HTTP method to use for the request. Defaults to "get".
        support_pagination (bool, optional): Follow continuation tokens and return every page. Defaults to False.
        support_lro (bool, optional): Poll a `202 Accepted` long-running operation until it finishes. Defaults to False.
        return_raw (bool, optional): If True, returns the raw response object. Defaults to False.
        return_result (bool, optional): If True, returns the final `ApiResult`
            (after pagination or LRO polling) instead of its data, so the caller
            can tell a failure from a success without data. Defaults to False.

    Returns:
        The parsed response data, or None on failure. With `return_result=True`,
        the `ApiResult` (NamedTuple) with the following fields:
            success: bool
            status_code: int
            data: Optional[Any] = None
            headers: Optional[dict] = None
            error: Optional[str] = None
            request_kwargs: Optional[dict] = None

    Raises:
        AuthenticationError: If the token retrieval fails.
        InvalidParameterError: If the payload is not a dictionary or if both payload and data are provided.

    Examples:
        ```python
        # Makes a GET request to the 'capacities' endpoint of the Microsoft Fabric API.
        api_request('capacities')

        # Makes a POST request to the 'capacities' endpoint with a JSON payload.
        api_request('capacities', method='post', payload={'name': 'New Capacity'})

        # Makes a DELETE request to the 'capacities' endpoint for the resource with ID '12345'.
        api_request('capacities/12345', method='delete')

        # Makes a GET request to the Power BI API for dataflows in the specified group.
        api_request(audience="powerbi", endpoint=f"/groups/MyProject/dataflows")
        ```
    """
    response = _base_api(
        endpoint=endpoint,
        content_type=content_type,
        payload=payload,
        data=data,
        params=params,
        audience=audience,
        credential_type=credential_type,
        method=method,
        return_raw=return_raw,
        **kwargs,
    )
    # If return_raw is True, return the raw response object
    if return_raw:
        return response

    result = response
    if result.success and support_pagination:
        result = _pagination_handler(result)
    elif result.success and support_lro and result.status_code == 202:
        logger.debug("Long-running operation detected, handling LRO...")
        result = _lro_handler(result)

    if return_result:
        return result

    if not result.success:
        logger.warning(f"{result.status_code}: {result.error}.")
        return None

    if method == "delete" and response.status_code == 200:
        logger.success(f"Deleted {endpoint} successfully.")
        return None

    if support_pagination:
        return (result.data or {}).get("value", [])

    if support_lro and response.status_code == 202 and not result.data:
        logger.success("Long-running operation completed successfully.")
        return None

    # Otherwise, return the parsed data
    return result.data
