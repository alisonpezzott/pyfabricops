import logging


def enable_notebook_logging(level=logging.INFO):
    """
    Enable basic notebook logging.

    Args:
        level (int): The logging level to set. Defaults to logging.INFO.

    Returns:
        None

    Examples:
        ```python
        enable_notebook_logging(logging.DEBUG)
        ```
    """
    logging.basicConfig(
        level=level, format='%(name)s %(levelname)s: %(message)s'
    )
