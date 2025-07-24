from typing import List, Optional, Union, Dict
from pandas import DataFrame


from ._decorators import df
from ._generic_endpoints import _list_generic
from ._logging import get_logger
from ._utils import is_valid_uuid


logger = get_logger(__name__)


@df
def list_capacities(
    df: bool = True,
) -> Union[DataFrame, List[Dict[str, str]], None]:
    """
    Returns a list of capacities.

    Args:
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.  
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, str]], None]): A DataFrame with the list of capacities.  
        If `df=False`, returns a list of dictionaries. If no capacities are found, returns None.
    """
    return _list_generic('capacities')

