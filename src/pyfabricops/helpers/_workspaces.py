from .._logging import get_logger
from .._workspaces import list_workspaces


logger = get_logger(__name__)


def get_workspace_id(workspace: str) -> str | None:
    """
    Retrieves the ID of a workspace by its name.

    Args:
        workspace (str): The name of the workspace.

    Returns:
        str | None: The ID of the workspace if found, otherwise None.
    """
    workspaces = list_workspaces(df=False)
    for _workspace in workspaces:
        if _workspace['displayName'] == workspace:
            return _workspace['id']
        logger.warning(f"Workspace '{workspace}' not found.")
    return None
