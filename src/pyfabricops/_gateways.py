import logging

import pandas

from ._core import api_core_request, pagination_handler
from ._decorators import df
from ._utils import is_valid_uuid

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


@df
def list_gateways(*, df: bool = False) -> list | pandas.DataFrame:
    """
    Lists all available gateways.

    Args:
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (list or pandas.DataFrame): The list of gateways.

    Examples:
        ```python
        list_gateways()
        list_gateways(df=True)
        ```
    """
    response = api_core_request(endpoint='/gateways', method='get')
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        response = pagination_handler(response)
        return response.data.get('value')


@df
def get_gateway(gateway: str, *, df: bool = False) -> dict | pandas.DataFrame:
    """
    Retrieves the details of a gateway by its ID.

    Args:
        gateway (str): The ID of the gateway to retrieve.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame): The gateway details if found, otherwise None.

    Examples:
        ```python
        get_gateway('MyGateway')
        get_gateway('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    gateway_id = resolve_gateway(gateway)
    if not gateway_id:
        return None
    response = api_core_request(endpoint=f'/gateways/{gateway_id}')
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


def get_gateway_public_key(gateway: str) -> dict:
    """
    Extracts the public key of a gateway by its ID.

    Args:
        gateway (str): The ID of the gateway to retrieve the public key from.

    Returns:
        Dict: The public key details if found, otherwise None.

    Examples:
        ```python
        get_gateway_public_key('MyGateway')
        get_gateway_public_key('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    gateway_id = resolve_gateway(gateway)
    if not gateway_id:
        return None

    response = get_gateway(gateway_id)

    return response.get('publicKey')


def resolve_gateway(gateway: str, *, silent: bool = False) -> str:
    """
    Resolves a gateway name to its ID.

    Args:
        gateway (str): The name or ID of the gateway.
        silent (bool, optional): If True, suppresses warnings. Defaults to False.

    Returns:
        str: The ID of the gateway, or None if not found.

    Examples:
        ```python
        resolve_gateway('MyGateway')
        resolve_gateway('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    if is_valid_uuid(gateway):
        return gateway
    gateways = list_gateways(df=False)
    if not gateways:
        return None

    for gtw in gateways:
        if gtw['displayName'] == gateway:
            return gtw['id']

    # If we get here, gateway was not found
    if not silent:
        logger.warning(f"Gateway '{gateway}' not found.")
    return None
