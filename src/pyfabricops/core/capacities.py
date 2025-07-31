from typing import Any, Dict, List, Optional, Union

from pandas import DataFrame

from ..api.api import api_request
from ..utils.decorators import df
from ..utils.logging import get_logger
from ..utils.utils import is_valid_uuid

logger = get_logger(__name__)


@df
def list_capacities(
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Returns a list of capacities.

    Args:
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A DataFrame with the list of capacities.
        If `df=False`, returns a list of dictionaries. If no capacities are found, returns None.
    """
    return api_request('/capacities', support_pagination=True)


def get_capacity_id(capacity_name: str) -> str | None:
    """
    Retrieves the ID of a capacity by its name.

    Args:
        capacity_name (str): The name of the capacity.

    Returns:
        str | None: The ID of the capacity if found, otherwise None.
    """
    capacities = list_capacities(df=False)

    for _capacity in capacities:
        if _capacity['displayName'] == capacity_name:
            return _capacity['id']

    logger.warning(f"Capacity '{capacity_name}' not found.")
    return None


def resolve_capacity(capacity: str) -> str | None:
    """
    Resolves a capacity name to its ID.

    Args:
        capacity (str): The name of the capacity.

    Returns:
        str | None: The ID of the capacity if found, otherwise None.
    """
    if is_valid_uuid(capacity):
        return capacity
    else:
        return get_capacity_id(capacity)
