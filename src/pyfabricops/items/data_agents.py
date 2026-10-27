from typing import cast

from ..api.api import ApiResult, api_request
from ..core.workspaces import resolve_workspace
from ..utils.exceptions import RequestError, ResourceNotFoundError
from ..utils.logging import get_logger
from ..utils.utils import is_valid_uuid
from .items import list_items

logger = get_logger(__name__)


def publish_data_agent(
    workspace: str, data_agent: str, description: str | None = None
) -> None:
    """
    Publishes the draft of a data agent, so that its users get it.

    A data agent keeps a draft and a published configuration, and an
    unpublished one cannot be used. Deploying its definition sends the
    configuration but does not publish it for sure, so publish it after the
    deployment. The publish API is in preview.

    Args:
        workspace (str): The workspace name or ID.
        data_agent (str): The name or ID of the data agent.
        description (str, optional): The description of what is published.
            Defaults to none.

    Raises:
        ResourceNotFoundError: If the workspace or the data agent is not
            found.
        RequestError: If the data agent cannot be published.

    Examples:
        ```python
        publish_data_agent('Sales-PRD', 'SalesAgent', 'Deployed by CI')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        raise ResourceNotFoundError(f"Workspace '{workspace}' not found.")
    data_agent_id = _resolve_data_agent(workspace_id, data_agent)
    payload = (
        {"publishedDescription": description}
        if description is not None
        else {}
    )
    result = cast(
        ApiResult,
        api_request(
            f"/workspaces/{workspace_id}/dataAgents/{data_agent_id}"
            "/staging/publish",
            method="post",
            payload=payload,
            support_lro=True,
            return_result=True,
        ),
    )
    if not result.success:
        raise RequestError(
            f"Could not publish data agent '{data_agent}': {result.error}"
        )
    logger.success(f"Data agent '{data_agent}' published.")


def _resolve_data_agent(workspace_id: str, data_agent: str) -> str:
    """The ID of a data agent, given by name or ID."""
    if is_valid_uuid(data_agent):
        return data_agent
    items = list_items(workspace_id, df=False)
    if items is None:
        raise RequestError(
            f"Could not list the items of workspace '{workspace_id}'."
        )
    for item in items:
        if item["type"] == "DataAgent" and item["displayName"] == data_agent:
            return str(item["id"])
    raise ResourceNotFoundError(
        f"Data agent '{data_agent}' not found in workspace '{workspace_id}'."
    )
