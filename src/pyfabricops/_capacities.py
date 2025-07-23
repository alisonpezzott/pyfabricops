import logging

import pandas

from ._core import api_core_request, pagination_handler
from ._decorators import df
from ._exceptions import ResourceNotFoundError
from ._generic_endpoints import _list_generic
from ._logging import get_logger
from ._utils import is_valid_uuid

logger = get_logger(__name__)


@df
def list_capacities(
    df: bool = True, **kwargs
) -> list | pandas.DataFrame | None:
    """
    Returns a list of capacities.

    Args:
        df (bool): If True, returns a pandas DataFrame. Defaults to True.
        **kwargs: Additional keyword arguments for the API request.

    Returns:
        list | pandas.DataFrame | None: A list of capacities or a DataFrame if df is True.
    """
    return _list_generic('capacities', df=df, **kwargs)


@df
def get_capacity(capacity: str, *, df=True):
    """
    Retrieves the details of a capacity.

    Args:
        capacity (str): The ID or name of the capacity to retrieve.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame): The details of the specified capacity. If `df=True`, returns a DataFrame with flattened keys.

    Raises:
        ResourceNotFoundError: If the specified capacity is not found.

    Examples:
        ```python
        get_capacity('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    caps = list_capacities(df=False)
    if not caps:
        return None

    if is_valid_uuid(capacity):
        for cap in caps:
            if cap['id'] == capacity:
                return cap
        logger.warning(f'Capacity with id {capacity} not found.')
        return None

    else:
        for cap in caps:
            if cap['displayName'] == capacity:
                return cap
        logger.warning(f'Capacity with name {capacity} not found.')
        return None
