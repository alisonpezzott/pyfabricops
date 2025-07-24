from .._folders import list_folders
from .._logging import get_logger


logger = get_logger(__name__)


def get_folder_id(workspace_id: str, folder_name: str) -> str | None:
    """
    Retrieves the ID of a folder by its name.

    Args:
        folder (str): The name of the folder.

    Returns:
        str | None: The ID of the folder if found, otherwise None.
    """
    folders = list_folders(workspace_id=workspace_id, df=False)
    for _folder in folders:
        if _folder['displayName'] == folder_name:
            return _folder['id']
    logger.warning(f"Folder '{folder_name}' not found.")
    return None
