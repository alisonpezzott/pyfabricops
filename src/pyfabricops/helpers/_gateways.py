from ..core.gateways import get_gateway, list_gateways


def get_gateway_id(gateway: str) -> str | None:
    """
    Retrieves the ID of a gateway by its ID or name.

    Args:
        gateway_id (str): The ID or name of the gateway.

    Returns:
        str | None: The ID of the gateway if found, otherwise None.

    Examples:
        ```python
        get_gateway_id('MyGateway')
        get_gateway_id('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    gateways = list_gateways(df=False)
    if not gateways:
        return None

    for gtw in gateways:
        if gtw['displayName'] == gateway:
            return gtw['id']

    return None


def get_gateway_public_key(gateway_id: str) -> dict | None:
    """
    Extracts the public key of a gateway by its ID.

    Args:
        gateway_id (str): The ID of the gateway to retrieve the public key from.

    Returns:
        dict: The public key details if found, otherwise None.

    Examples:
        ```python
        get_gateway_public_key('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    response = get_gateway(gateway_id, df=False)
    if not response:
        return None

    return response.get('publicKey')
