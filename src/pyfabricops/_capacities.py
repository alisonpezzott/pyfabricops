import logging

from ._core import api_core_request, pagination_handler
from ._decorators import df
from ._exceptions import ResourceNotFoundError
from ._utils import is_valid_uuid

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


@df
def list_capacities(*, df=True):
    """
    Lists all available capacities.

    Args:
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame): The list of capacities. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        list_capacities()
        list_capacities(df=True) # Returns a DataFrame with flattened keys
        ```
    """
    response = api_core_request(endpoint='/capacities')
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        response = pagination_handler(response)
    return response.data.get('value')


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
