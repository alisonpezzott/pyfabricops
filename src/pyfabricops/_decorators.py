import logging
from functools import wraps

import pandas as pd

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def df(func):
    """
    This decorator checks if the output is a JSON-like structure and converts it to a DataFrame.
    If the output is None, it returns None. If the output is already a DataFrame, it returns it as is.
    If the output is a JSON-like structure (dict or list of dicts), it flattens it and converts it to a DataFrame.

    Args:
        df(boolean): True to convert output to DataFrame, False to keep as is. Default is False.

    Returns:
        function: The wrapped function that returns a DataFrame or None.

    Examples:
        ```python
        list_capacities(df=True)
        ```
    """

    @wraps(func)
    def _wrapper(*args, **kwargs):
        df = kwargs.pop('df', False)
        result = func(*args, **kwargs)

        if result is None:
            return None

        if df:
            return _json_df(result)
        else:
            return result

    return _wrapper


def _flatten_json(data, parent_key='', sep='_'):
    """
    Helper function to flatten nested JSON.

    Args:
        data (dict): JSON to flatten.
        parent_key (str): Parent key (used for recursion).
        sep (str): Separator for flattened keys.

    Returns:
        list[dict]: List of flattened dictionaries.
    """
    items = []
    for k, v in data.items():
        new_key = f'{parent_key}{sep}{k}' if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_json(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def _json_df(data):
    """
    Converts various types of JSON to a DataFrame.

    Args:
        data (dict | list): The JSON to be converted. Can be a simple dictionary,
        a nested dictionary, or a list of dictionaries.

    Returns:
        pd.DataFrame: The resulting DataFrame.
    """
    if not data:
        return None

    if isinstance(data, dict):

        # If it"s a simple dictionary
        if all(not isinstance(v, (dict, list)) for v in data.values()):
            return pd.DataFrame([data])

        # If it"s a dictionary with nested levels
        else:
            flattened_data = _flatten_json(data)
            return pd.DataFrame([flattened_data])

    elif isinstance(data, list):

        # If it"s a list of dictionaries
        if all(isinstance(item, dict) for item in data):
            flattened_list = [_flatten_json(item) for item in data]
            return pd.DataFrame(flattened_list)
        else:
            raise ValueError(
                'The list contains items that are not dictionaries.'
            )

    else:
        raise TypeError(
            'Input type must be a dictionary or a list of dictionaries.'
        )
