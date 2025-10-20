from typing import Any, Dict, List, Literal, Optional, Union
from venv import create

from pandas import DataFrame

from pyfabricops.utils.exceptions import OptionNotAvailableError

from ..api.api import api_request
from ..core.workspaces import resolve_workspace
from ..utils.decorators import df
from ..utils.logging import get_logger
from ..utils.utils import is_valid_uuid

logger = get_logger(__name__)


@df
def list_deployment_pipelines(
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    List deployment pipelines

    Args:
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A list of deployment pipelines.

    Examples:
        ```python
        list_deployment_pipelines()
        ```
    """
    return api_request(
        '/deploymentPipelines',
        support_pagination=True,
    )


def get_deployment_pipeline_id(pipeline_name: str) -> Union[str, None]:
    """
    Retrieves the ID of a deployment pipeline by its name.

    Args:
        pipeline_name (str): The name of the deployment pipeline.

    Returns:
        str | None: The ID of the deployment pipeline if found, otherwise None.
    """
    pipelines = list_deployment_pipelines(df=False)
    for _pipeline in pipelines:
        if _pipeline['displayName'] == pipeline_name:
            return _pipeline['id']

    logger.warning(f"Deployment pipeline '{pipeline_name}' not found.")
    return None


def resolve_deployment_pipeline(pipeline: str) -> Union[str, None]:
    """
    Resolves a deployment pipeline to its ID.

    Args:
        pipeline (str): The name or id of the deployment pipeline.

    Returns:
        str | None: The ID of the deployment pipeline if found, otherwise None.
    """
    if is_valid_uuid(pipeline):
        return pipeline
    else:
        return get_deployment_pipeline_id(pipeline)


@df
def get_deployment_pipeline(
    pipeline: str, df: Optional[bool] = True
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Returns the specified deployment pipeline.

    Args:
        pipeline (str): The name or ID of the deployment pipeline to retrieve.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
                If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]) The details of the deployment pipeline if found, otherwise None. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        get_deployment_pipeline('123e4567-e89b-12d3-a456-426614174000')
        get_deployment_pipeline('MyProjectPipeline')
        get_deployment_pipeline('MyProjectPipeline', df=False) # Returns as list
        ```
    """
    return api_request(
        '/deploymentPipelines/' + resolve_deployment_pipeline(pipeline)
    )


def resolve_deployment_pipeline_stage(
    pipeline: str, stage_name: str
) -> Union[str, None]:
    """
    Resolves a deployment pipeline stage to its ID.

    Args:
        pipeline (str): The name or id of the deployment pipeline.
        stage_name (str): The name of the deployment pipeline stage.

    Returns:
        str | None: The ID of the deployment pipeline stage if found, otherwise None.
    """
    pipeline_id = resolve_deployment_pipeline(pipeline)
    if not pipeline_id:
        return None
    pipeline_details = get_deployment_pipeline(pipeline, df=False)
    for stage in pipeline_details.get('stages', []):
        if stage['displayName'] == stage_name:
            return stage['id']

    logger.warning(
        f"Stage '{stage_name}' not found in deployment pipeline '{pipeline}'."
    )
    return None


@df
def create_deployment_pipeline(
    display_name: str,
    stages: List[Dict[str, Any]],
    *,
    description: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Creates a new deployment pipeline.

    Args:
        display_name (str): The display name of the deployment pipeline.
        stages (List[Dict[str, Any]]): A list of stages for the deployment pipeline.
        description (Optional[str]): An optional description for the deployment pipeline.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): The details of the created deployment pipeline.

    Examples:
        ```python
        create_deployment_pipeline(
            display_name='My Deployment Pipeline',
            stages=[
                {
                    "displayName": "Development",
                    "description": "Development stage description",
                    "isPublic": false
                },
                {
                    "displayName": "Test",
                    "description": "Test stage description",
                    "isPublic": false
                },
                {
                    "displayName": "Production",
                    "description": "Production stage description",
                    "isPublic": true
                }
            ],
            description='This is my deployment pipeline',
            df=True
        )
        ```
    """
    payload = {
        'displayName': display_name,
        'stages': stages,
    }
    if description:
        payload['description'] = description
    return api_request(
        '/deploymentPipelines',
        method='POST',
        payload=payload,
    )


def assign_workspace_to_stage(
    workspace: str,
    pipeline: str,
    stage: str,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Assigns a workspace to a deployment pipeline stage.

    Args:
        pipeline (str): The name or ID of the deployment pipeline.
        stage (str): The name or ID of the stage within the deployment pipeline.
        workspace (str): The name or ID of the workspace to assign.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): The updated details of the deployment pipeline stage.

    Examples:
        ```python
        assign_workspace_to_stage(
            workspace='My Workspace',
            pipeline='My Deployment Pipeline',
            stage='Development'
        )
        ```
    """
    pipeline_id = resolve_deployment_pipeline(pipeline)
    if not pipeline_id:
        return None
    stage_id = resolve_deployment_pipeline_stage(pipeline, stage)
    if not stage_id:
        return None
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    return api_request(
        f'/deploymentPipelines/{pipeline_id}/stages/{stage_id}/assignWorkspace',
        method='POST',
        payload={'workspaceId': workspace_id},
    )


def unassign_workspace_to_stage(
    pipeline: str,
    stage: str,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Unassigns a workspace from a deployment pipeline stage.

    Args:
        pipeline (str): The name or ID of the deployment pipeline.
        stage (str): The name or ID of the stage within the deployment pipeline.
        workspace (str): The name or ID of the workspace to unassign.
    """
    pipeline_id = resolve_deployment_pipeline(pipeline)
    if not pipeline_id:
        return None
    stage_id = resolve_deployment_pipeline_stage(pipeline, stage)
    if not stage_id:
        return None

    return api_request(
        f'/deploymentPipelines/{pipeline_id}/stages/{stage_id}/unassignWorkspace',
        method='POST',
    )


@df
def add_deployment_pipeline_role_assignment(
    pipeline: str,
    user_uuid: str,
    user_type: Literal[
        'User', 'Group', 'ServicePrincipal', 'ServicePrincipalProfile'
    ] = 'User',
    role: Literal['Admin', 'Contributor', 'Member', 'Viewer'] = 'Admin',
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Adds a permission to a deployment pipeline for a user.

    Args:
        pipeline (str): The ID or name of the deployment pipeline.
        user_uuid (str): The UUID of the user.
        user_type (str): The type of user (options: User, Group, ServicePrincipal, ServicePrincipalProfile).
        role (str): The role to assign (options: admin, member, contributor, viewer).
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The role assignment details if successful.

    Raises:
        ResourceNotFoundError: If the specified deployment pipeline is not found.
        OptionNotAvailableError: If the user type or role is invalid.

    Examples:
        ```python
        add_deployment_pipeline_role_assignment(
            '123e4567-e89b-12d3-a456-426614174000',
            'FefEFewf-feF-1234-5678-9abcdef01234', user_type='User', role='Admin'
        )
        ```
    """
    if user_type not in [
        'User',
        'Group',
        'ServicePrincipal',
        'ServicePrincipalProfile',
    ]:
        raise OptionNotAvailableError(
            f'Invalid user type: {user_type}. Must be one of: User, Group, ServicePrincipal, ServicePrincipalProfile'
        )
    if role not in ['Admin', 'Contributor', 'Member', 'Viewer']:
        raise OptionNotAvailableError(
            f'Invalid role: {role}. Must be one of: Admin, Contributor, Member, Viewer'
        )
    payload = {'principal': {'id': user_uuid, 'type': user_type}, 'role': role}

    return api_request(
        '/deploymentPipelines/'
        + resolve_deployment_pipeline(pipeline)
        + '/roleAssignments',
        payload=payload,
        method='post',
    )


@df
def list_deployment_pipeline_role_assignments(
    pipeline: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Lists all role assignments for a deployment pipeline.

    Args:
        pipeline (str): The name or ID of the deployment pipeline to list role assignments for.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A list of role assignments.

    Examples:
        ```python
        list_deployment_pipeline_role_assignments('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    return api_request(
        '/deploymentPipelines/'
        + resolve_deployment_pipeline(pipeline)
        + '/roleAssignments',
        method='GET',
        support_pagination=True,
    )


@df
def deploy_stage_content(
    pipeline: str,
    source_stage: str,
    target_stage: str,
    *,
    items: Optional[List[Dict[str, Any]]] = None,
    note: Optional[str] = None,
    options: Optional[Dict[str, Any]] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Deploys content to a specified stage in a deployment pipeline.

    Args:
        pipeline (str): The name or ID of the deployment pipeline.
        source_stage (str): The name or ID of the source stage within the deployment pipeline.
        target_stage (str): The name or ID of the target stage within the deployment pipeline.
        items (Optional[List[str]]): A list of item IDs to deploy. If not provided, all items will be deployed.
        note (Optional[str]): An optional note for the deployment.
        options (Optional[Dict[str, Any]]): Additional deployment options.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): The deployment result.

    Examples:
        ```python
        deploy_stage_content(
            '123e4567-e89b-12d3-a456-426614174000',
            'develop',
            'staging',
        )

        deploy_stage_content(
            pipeline = '123e4567-e89b-12d3-a456-426614174000',
            source_stage = 'develop',
            target_stage = 'staging',
            items = [
                {
                "sourceItemId": "1a201f2a-d1d8-45c0-8c61-1676338517de",
                "itemType": "SemanticModel"
                },
                {
                "sourceItemId": "2d225191-65f8-4ec3-b77d-06100602b1f7",
                "itemType": "Report"
                }
            ],
            note = "Deploying selected items from develop to staging",
            options = {"allowCrossRegionDeployment": True}
        )
        ```
    """
    pipeline_id = resolve_deployment_pipeline(pipeline)
    if not pipeline_id:
        return None
    source_stage_id = resolve_deployment_pipeline_stage(
        pipeline_id, source_stage
    )
    if not source_stage_id:
        return None
    target_stage_id = resolve_deployment_pipeline_stage(
        pipeline_id, target_stage
    )
    if not target_stage_id:
        return None

    payload = {
        'sourceStageId': source_stage_id,
        'targetStageId': target_stage_id,
    }

    if items:
        payload['items'] = items
    if note:
        payload['note'] = note
    if options:
        payload['options'] = options

    return api_request(
        '/deploymentPipelines/'
        + resolve_deployment_pipeline(pipeline)
        + '/deploy',
        method='POST',
        payload=payload,
        support_lro=True,
    )


@df
def list_deployment_pipeline_operations(
    pipeline: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Lists all operations for a deployment pipeline.

    Args:
        pipeline (str): The name or ID of the deployment pipeline to list operations for.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A list of deployment pipeline operations.
    """
    pipeline_id = resolve_deployment_pipeline(pipeline)
    if not pipeline_id:
        return None

    return api_request(
        '/deploymentPipelines/' + pipeline_id + '/operations',
        method='GET',
        support_pagination=True,
    )


@df
def get_deployment_pipeline_operation(
    pipeline: str,
    operation_id: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Gets a specific operation for a deployment pipeline.

    Args:
        pipeline (str): The name or ID of the deployment pipeline.
        operation_id (str): The ID of the operation to retrieve.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a dictionary.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The requested deployment pipeline operation.
    """
    pipeline_id = resolve_deployment_pipeline(pipeline)
    if not pipeline_id:
        return None

    return api_request(
        '/deploymentPipelines/' + pipeline_id + '/operations/' + operation_id,
        method='GET',
    )


@df
def update_deployment_pipeline(
    pipeline: str,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Updates a deployment pipeline's details.

    Args:
        pipeline (str): The name or ID of the deployment pipeline to update.
        display_name (Optional[str]): The new display name for the deployment pipeline.
        description (Optional[str]): The new description for the deployment pipeline.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a dictionary.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The updated deployment pipeline details.

    Examples:
        ```python
        updated_pipeline = update_deployment_pipeline(
            pipeline="my-pipeline",
            display_name="My Updated Pipeline",
            description="This is an updated description."
        )
        ```
    """
    pipeline_id = resolve_deployment_pipeline(pipeline)
    if not pipeline_id:
        return None

    payload = {}
    if display_name:
        payload['displayName'] = display_name
    if description:
        payload['description'] = description

    return api_request(
        '/deploymentPipelines/' + pipeline_id,
        method='PATCH',
        payload=payload,
    )


def update_deployment_pipeline_stage(
    pipeline: str,
    stage: str,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    is_public: Optional[bool] = None,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Updates a deployment pipeline stage's details.

    Args:
        pipeline (str): The name or ID of the deployment pipeline.
        stage (str): The name or ID of the stage within the deployment pipeline.
        display_name (Optional[str]): The new display name for the stage.
        description (Optional[str]): The new description for the stage.
        is_public (Optional[bool]): Whether the stage is public or not.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The updated deployment pipeline stage details.
    """
    pipeline_id = resolve_deployment_pipeline(pipeline)
    if not pipeline_id:
        return None
    stage_id = resolve_deployment_pipeline_stage(pipeline, stage)
    if not stage_id:
        return None

    payload = {}
    if display_name:
        payload['displayName'] = display_name
    if description:
        payload['description'] = description
    if is_public is not None:
        payload['isPublic'] = is_public

    return api_request(
        f'/deploymentPipelines/{pipeline_id}/stages/{stage_id}',
        method='PATCH',
        payload=payload,
    )


def delete_deployment_pipeline(
    pipeline: str,
) -> None:
    """
    Deletes a deployment pipeline.

    Args:
        pipeline (str): The name or ID of the deployment pipeline to delete.

    Returns:
        None

    Examples:
        ```python
        delete_deployment_pipeline('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    pipeline_id = resolve_deployment_pipeline(pipeline)
    if not pipeline_id:
        return None

    api_request(
        '/deploymentPipelines/' + pipeline_id,
        method='DELETE',
    )


def delete_deployment_pipeline_role_assignment(
    pipeline: str,
    role_assignment_id: str,
) -> None:
    """
    Deletes a role assignment from a deployment pipeline.

    Args:
        pipeline (str): The name or ID of the deployment pipeline.
        role_assignment_id (str): The ID of the role assignment to delete.

    Returns:
        None

    Examples:
        ```python
        delete_deployment_pipeline_role_assignment(
            '123e4567-e89b-12d3-a456-426614174000',
            'role-assignment-uuid'
        )
        ```
    """
    pipeline_id = resolve_deployment_pipeline(pipeline)
    if not pipeline_id:
        return None

    api_request(
        '/deploymentPipelines/'
        + pipeline_id
        + '/roleAssignments/'
        + role_assignment_id,
        method='DELETE',
    )
