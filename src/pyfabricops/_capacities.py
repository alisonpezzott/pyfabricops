import pandas

from ._decorators import df
from ._generic_endpoints import _list_generic
from ._logging import get_logger
from ._utils import is_valid_uuid


logger = get_logger(__name__)


@df
def list_capacities(
    df: bool = True,
) -> pandas.DataFrame | list[dict] | None:
    """
    Returns a list of capacities.

    Args:
        df (bool): If True, returns a pandas DataFrame. Defaults to True.

    Returns:
        (pandas.DataFrame | list[dict] | None): A DataFrame with the list of capacities.  
        If `df=False`, returns a list of dictionaries. If no capacities are found, returns None.
    """
    return _list_generic('capacities')

