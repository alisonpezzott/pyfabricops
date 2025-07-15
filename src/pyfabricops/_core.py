import logging
import time
from typing import Any, Literal, NamedTuple, Optional
from urllib.parse import urlencode

import requests

from ._auth import _get_token
from ._exceptions import AuthenticationError, InvalidParameterError
from ._scopes import FABRIC_API, POWERBI_API

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class ApiResult(NamedTuple):
    success: bool
    status_code: int
    data: Optional[Any] = None
    headers: Optional[dict] = None
    error: Optional[str] = None
    request_kwargs: Optional[dict] = None


def api_core_request(
    endpoint: str,
    *,  # Force keyword-only arguments after endpoint
    content_type: str = 'application/json',
    payload: Optional[dict] = None,
    data: Optional[dict] = None,
    params: Optional[dict] = None,
    audience: Literal['fabric', 'powerbi'] = 'fabric',
    credential_type: Literal['spn', 'user'] = 'spn',
    method: Literal['get', 'post', 'patch', 'delete', 'put'] = 'get',
    return_raw: bool = False,
    timeout: int = 30,
):
    """
    Makes a request to the Microsoft Fabric or Power BI API.
    This function supports various HTTP methods and can handle both JSON payloads and form data.
    It automatically retrieves an access token based on the specified audience and credential type.
    It supports pagination by allowing query parameters to be passed in as a dictionary.
    It also supports long-running operations (LRO) by checking the response headers for a 'Location' header.
    It can return the raw response object or parsed JSON data based on the `return_raw` parameter.

    Args:
        endpoint (str): The API endpoint to call.
        content_type (str): The content type of the request. Defaults to "application/json".
        payload (Optional[dict]): The JSON payload to send with the request. Defaults to None.
        data (Optional[dict]): The data to send with the request. Defaults to None.
        params (Optional[dict]): Query parameters to append to the URL. Defaults to None.
        audience (Literal["fabric", "powerbi"]): The API audience to target. Defaults to "fabric".
        credential_type (Literal["spn", "user"]): The type of credentials to use for authentication. Defaults to "spn".
        method (Literal["get", "post", "patch", "delete", "put"]): The HTTP method to use for the request. Defaults to "get".
        return_raw (bool, optional): If True, returns the raw response object. Defaults to False.
        timeout (int): Request timeout in seconds. Defaults to 30.

    Returns:
        ApiResult (NamedTuple): The response object from the request.
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
        api_core_request('capacities')

        # Makes a POST request to the 'capacities' endpoint with a JSON payload.
        api_core_request('capacities', method='post', payload={'name': 'New Capacity'})

        # Makes a DELETE request to the 'capacities' endpoint for the resource with ID '12345'.
        api_core_request('capacities/12345', method='delete')

        # Makes a GET request to the Power BI API for dataflows in the specified group.
        api_core_request(audience="powerbi", endpoint=f"/groups/MyProject/dataflows")

        # Makes a request with custom timeout.
        api_core_request('capacities', timeout=60)
        ```
    """
    # Base URL selection based on audience
    base_url = FABRIC_API if audience == 'fabric' else POWERBI_API

    # Construct the full URL
    url = f'{base_url}{endpoint}'

    # Append parameters if provided (supports dict now)
    if params:
        if isinstance(params, dict):
            query_str = urlencode(params)
            url += f'?{query_str}'
        else:
            raise InvalidParameterError(
                'Query parameters must be a dictionary.'
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
            'Failed to retrieve token. Ensure that the authentication is set up correctly.'
        )

    # Extract the access token from the token response
    access_token = token.get('access_token')

    # Build the headers for the request
    headers = {
        'Content-Type': content_type,
        'Authorization': f'Bearer {access_token}',
    }

    # Validate the payload
    if not isinstance(payload, dict):
        raise InvalidParameterError('Payload must be a dictionary.')

    # Request execution - modified to support data
    request_kwargs = {
        'method': method.upper(),
        'url': url,
        'headers': headers,
        'timeout': timeout,
    }

    # Handle data vs json
    if data is not None:
        request_kwargs['data'] = data
    else:
        request_kwargs['json'] = payload

    # Log the request for debugging
    logger.info(f'Making {method.upper()} request to {url}')
    logger.debug(f'Headers: {headers}')
    if payload and payload != {}:
        logger.debug(f'Payload: {payload}')

    # Request execution with proper error handling
    try:
        response = requests.request(**request_kwargs)
    except requests.exceptions.Timeout:
        return ApiResult(
            success=False,
            status_code=408,
            data=None,
            headers=None,
            error=f'Request timeout after {timeout} seconds',
            request_kwargs=request_kwargs,
        )
    except requests.exceptions.ConnectionError as e:
        return ApiResult(
            success=False,
            status_code=503,
            data=None,
            headers=None,
            error=f'Connection error: {str(e)}',
            request_kwargs=request_kwargs,
        )
    except requests.exceptions.RequestException as e:
        return ApiResult(
            success=False,
            status_code=500,
            data=None,
            headers=None,
            error=f'Request failed: {str(e)}',
            request_kwargs=request_kwargs,
        )

    # Log response status
    logger.debug(f'Response status: {response.status_code}')

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


def pagination_handler(api_result: NamedTuple) -> ApiResult:
    """Handle paginated responses with continuation tokens."""
    # Check for continuation token
    if not api_result.data or 'continuationToken' not in api_result.data:
        return api_result

    continuation_token = api_result.data.get('continuationToken')
    data = api_result.data.get('value', [])

    # Get original request kwargs for subsequent requests
    original_kwargs = api_result.request_kwargs.copy()
    headers = original_kwargs.get('headers', {})

    # Continue fetching data until no continuation token is left
    while continuation_token:
        try:
            # Update URL with continuation token
            base_url = original_kwargs['url'].split('?')[
                0
            ]  # Remove existing params
            new_url = f'{base_url}?continuationToken={continuation_token}'

            response = requests.request(
                method='GET',  # Pagination is always GET
                url=new_url,
                headers=headers,
            )
            response.raise_for_status()

            response_data = response.json()
            new_data = response_data.get('value', [])
            data.extend(new_data)
            continuation_token = response_data.get('continuationToken')

        except Exception as e:
            logger.error(f'Pagination failed: {str(e)}')
            # Return what we have so far
            break

    return ApiResult(
        success=True,
        status_code=200,
        data={'value': data},
        headers=api_result.headers,
        error=None,
        request_kwargs=api_result.request_kwargs,
    )


def lro_handler(api_result: NamedTuple) -> ApiResult:
    """Handle long-running operations (LRO)."""
    # Check if is a long-running operation (LRO)
    if 'location' not in api_result.headers:
        return api_result

    location = api_result.headers['Location']
    logger.debug(f'Long-running operation detected at {location}')

    headers = api_result.request_kwargs.get('headers')
    logger.debug(f'Headers for LRO request: {headers}')

    # Request execution
    try:
        state = requests.request(method='GET', url=location, headers=headers)
        logger.debug(f'State of LRO request: {state.json()}')
        status = state.json().get('status')
    except Exception as e:
        return ApiResult(
            success=False,
            status_code=500,
            data=None,
            headers=None,
            error=f'Failed to check LRO status: {str(e)}',
            request_kwargs=None,
        )

    if status in ['Succeeded', 'Failed', 'Undefined']:
        try:
            response = requests.request(
                method='GET',
                url=f'{location}/result',
                headers=headers,
            )
            return ApiResult(
                success=response.ok,
                status_code=response.status_code,
                data=response.json() if response.ok else None,
                headers=response.headers if response.ok else None,
                error=response.text if not response.ok else None,
                request_kwargs=None,
            )
        except Exception as e:
            return ApiResult(
                success=False,
                status_code=500,
                data=None,
                headers=None,
                error=f'Failed to get LRO result: {str(e)}',
                request_kwargs=None,
            )

    elif status in ['Running', 'NotStarted']:
        MAX_RETRIES = 10
        RETRY_INTERVAL = 5
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                state = requests.request(
                    method='GET', url=location, headers=headers
                )
                status = state.json().get('status')

                if status in ['Failed', 'Undefined']:
                    return ApiResult(
                        success=False,
                        status_code=state.status_code,
                        data=state.json() if state.ok else None,
                        headers=state.headers if state.ok else None,
                        error=state.text
                        if not state.ok
                        else f'LRO failed with status: {status}',
                        request_kwargs=None,
                    )

                if status == 'Succeeded':
                    response = requests.request(
                        method='GET',
                        url=f'{location}/result',
                        headers=headers,
                    )
                    return ApiResult(
                        success=response.ok,
                        status_code=response.status_code,
                        data=response.json() if response.ok else None,
                        headers=response.headers if response.ok else None,
                        error=response.text if not response.ok else None,
                        request_kwargs=None,
                    )

                time.sleep(RETRY_INTERVAL)

            except Exception as e:
                return ApiResult(
                    success=False,
                    status_code=500,
                    data=None,
                    headers=None,
                    error=f'LRO polling failed at attempt {attempt}: {str(e)}',
                    request_kwargs=None,
                )

        return ApiResult(
            success=False,
            status_code=state.status_code,
            data=None,
            headers=None,
            error='Max retries exceeded.',
            request_kwargs=None,
        )
