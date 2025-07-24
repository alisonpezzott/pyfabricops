from ..core.capacities import list_capacities
from ..utils.logging import get_logger


logger = get_logger(__name__)


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
