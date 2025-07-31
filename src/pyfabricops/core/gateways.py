from typing import Any, Dict, List, Optional, Union

from pandas import DataFrame

from ..api.api import api_request
from ..utils.decorators import df
from ..utils.logging import get_logger
from ..utils.utils import is_valid_uuid

logger = get_logger(__name__)


@df
def list_gateways(
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Lists all available gateways.

    Args:
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): The list of gateways.

    Examples:
        ```python
        list_gateways()
        ```
    """
    return api_request('/gateways', support_pagination=True)


def get_gateway_id(gateway_name: str) -> Union[str, None]:
    """
    Retrieves the ID of a gateway by its name.

    Args:
        gateway_name (str): The name of the gateway.

    Returns:
        str | None: The ID of the gateway if found, otherwise None.
    """
    gateways = list_gateways(df=False)
    for _gateway in gateways:
        if _gateway['displayName'] == gateway_name:
            return _gateway['id']
    logger.warning(f"Gateway '{gateway_name}' not found.")
    return None


def resolve_gateway(gateway: str) -> Union[str, None]:
    """
    Resolves a gateway name to its ID.

    Args:
        gateway (str): The name of the gateway.

    Returns:
        str | None: The ID of the gateway if found, otherwise None.
    """
    if is_valid_uuid(gateway):
        return gateway
    else:
        return get_gateway_id(gateway)


@df
def get_gateway(
    gateway: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Retrieves the details of a gateway by its ID.

    Args:
        gateway (str): The name or ID of the gateway to retrieve.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The gateway details if found, otherwise None.

    Examples:
        ```python
        get_gateway('123e4567-e89b-12d3-a456-426614174000')
        get_gateway('my-gateway')
        ```
    """
    gateway_id = resolve_gateway(gateway)
    if not gateway_id:
        return None
    return api_request(
        '/gateways/' + gateway_id,
    )


def get_gateway_public_key(gateway: str) -> dict | None:
    """
    Extracts the public key of a gateway by its ID.

    Args:
        gateway (str): The ID of the gateway to retrieve the public key from.

    Returns:
        dict: The public key details if found, otherwise None.

    Examples:
        ```python
        get_gateway_public_key('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    response = get_gateway(gateway, df=False)
    if not response:
        return None

    return response.get('publicKey')
