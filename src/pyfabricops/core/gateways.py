from pandas import DataFrame
from typing import Optional, List, Dict, Union

from ..utils.decorators import df
from ..api.api import (
    _list_request,
    _get_request,
)
from ..utils.logging import get_logger
from ..utils.utils import is_valid_uuid

logger = get_logger(__name__)


@df
def list_gateways(
    df: Optional[bool] = True
) -> Union[DataFrame, List[Dict[str, str]], None]:
    """
    Lists all available gateways.

    Args:
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.  
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, str]], None]): The list of gateways.

    Examples:
        ```python
        list_gateways()
        ```
    """
    return _list_request('gateways')
 

@df
def _get_gateway(
    gateway_id: str, 
    *, 
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, str], None]:
    """
    Retrieves the details of a gateway by its ID.

    Args:
        gateway_id (str): The ID of the gateway to retrieve.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.  
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, str], None]): The gateway details if found, otherwise None.

    Examples:
        ```python
        get_gateway('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    return _get_request('gateways', gateway_id,)  


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
) -> Union[DataFrame, Dict[str, str], None]:
    """
    Retrieves the details of a gateway by its ID.

    Args:
        gateway (str): The name or ID of the gateway to retrieve.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.  
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, str], None]): The gateway details if found, otherwise None.

    Examples:
        ```python
        get_gateway('123e4567-e89b-12d3-a456-426614174000')
        get_gateway('my-gateway')
        ```
    """
    return _get_request('gateways', resolve_gateway(gateway))   
