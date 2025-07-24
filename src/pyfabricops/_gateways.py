import pandas

from ._core import api_core_request, pagination_handler
from ._decorators import df
from ._generic_endpoints import (
    _list_generic,
    _get_generic,
    _delete_generic,
    _patch_generic,
    _post_generic
)
from ._logging import get_logger
from ._utils import is_valid_uuid

logger = get_logger(__name__)


@df
def list_gateways(*, df: bool = False) -> pandas.DataFrame | list[dict] | None:
    """
    Lists all available gateways.

    Args:
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (pandas.DataFrame | list[dict] | None): The list of gateways.

    Examples:
        ```python
        list_gateways()
        ```
    """
    return _list_generic('gateways')
 

@df
def get_gateway(
    gateway_id: str, 
    *, 
    df: bool = False
) -> pandas.DataFrame | dict | None:
    """
    Retrieves the details of a gateway by its ID.

    Args:
        gateway_id (str): The ID of the gateway to retrieve.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (pandas.DataFrame | dict | None): The gateway details if found, otherwise None.

    Examples:
        ```python
        get_gateway('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    return _get_generic('gateways', gateway_id,)  

