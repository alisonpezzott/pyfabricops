import logging
import time
from typing import Literal

from ._connections import resolve_connection
from ._core import api_core_request, lro_handler
from ._decorators import df
from ._workspaces import resolve_workspace

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def github_connect(
    workspace: str,
    connection: str,
    owner_name: str,
    repository_name: str,
    branch_name: str = 'main',
    directory_name: str = '/',
) -> bool:
    """
    Connects a Fabric workspace to a Git repository.

    Args:
        workspace (str): The name or ID of the Fabric workspace.
        connection (str): The name or ID of the Git connection.
        owner_name (str): The name of the owner of the Git repository.
        repository_name (str): The name of the repository of the Git repository.
        branch_name (str): The name of the branch to connect to.
        directory_name (str, optional): The path to the folder where the repository is located. Defaults to "/".

    Returns:
        bool: True if the connection was successful, False otherwise.

    Raises:
        ValueError: If the workspace or connection cannot be resolved.

    Examples:
        ```python
        github_connect(
            workspace='my_workspace',
            connection='my_connection',
            owner_name='my_owner',
            repository_name='my_repository',
            branch_name='main',
            directory_name='/'
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    connection_id = resolve_connection(connection)
    if not connection_id:
        return None

    # Prepare the payload for the Git connection
    payload = {
        'gitProviderDetails': {
            'ownerName': owner_name,
            'gitProviderType': 'GitHub',
            'repositoryName': repository_name,
            'branchName': branch_name,
            'directoryName': directory_name,
        },
        'myGitCredentials': {
            'source': 'ConfiguredConnection',
            'connectionId': connection_id,
        },
    }
    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/git/connect',
        method='post',
        payload=payload,
        return_raw=True,
        credential_type='user',
    )
    if not response.status_code == 200:
        logger.error(
            f"Failed to connect GitHub repository: {response.json().get('errorCode')} - {response.json().get('message')}"
        )
        return False
    else:
        logger.info(
            f"Successfully connected GitHub repository '{repository_name}' to workspace '{workspace_id}'."
        )
        return True


@df
def git_init(
    workspace: str,
    initialize_strategy: Literal[
        'PreferWorkspace', 'PreferRemote', 'None'
    ] = 'PreferWorkspace',
    provider: Literal['GitHub', 'AzureDevOps'] = 'GitHub',
    *,
    df: bool = False,
) -> dict:
    """
    Initializes a Fabric workspace to use Git for version control.

    Args:
        workspace (str): The name or ID of the Fabric workspace.
        initialize_strategy (Literal["PreferWorkspace", "PreferRemote", "None"], optional):
            The strategy to use for initialization. Defaults to "PreferWorkspace".
        provider (Literal["GitHub", "AzureDevOps"], optional):
            The Git provider to use. Defaults to "GitHub".
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        dict: The response data from the API if successful, or None if the workspace cannot be resolved.

    Raises:
        ValueError: If the workspace cannot be resolved.

    Examples:
    ```python
        git_init(
            workspace='my_workspace',
            initialize_strategy='PreferWorkspace',
            provider='GitHub'
        )
    )
    ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    payload = {'initializationStrategy': initialize_strategy}

    response = api_core_request(
        method='post',
        endpoint=f'/workspaces/{workspace_id}/git/initializeConnection',
        payload=payload,
        credential_type='user',
    )

    if not response.status_code in [200, 202]:
        logger.error(
            f'Failed to initialize Git connection: {response.status_code} - {response.error}'
        )
        return False
    elif response.status_code == 202:
        # If the response is a long-running operation, handle it
        lro_response = lro_handler(response)
        if not lro_response.success:
            logger.warning(
                f'{lro_response.status_code}: {lro_response.error}.'
            )
            return None
        else:
            return lro_response.data
    elif response.status_code == 200:
        # If the response is successful, we can process it
        logger.info(f'Successfully initialized Git connection for workspace.')
        return response.data


@df
def git_status(
    workspace: str,
    provider: Literal['GitHub', 'AzureDevOps'] = 'GitHub',
    *,
    df: bool = False,
) -> dict:
    """
    Retrieve the Git status of the workspace.

    Args:
        workspace (str): The name or ID of the Fabric workspace.
        provider (Literal["GitHub", "AzureDevOps"], optional):
            The Git provider to use. Defaults to "GitHub".
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        dict: The Git status of the workspace if successful, or None if the workspace cannot be resolved.

    Raises:
        ValueError: If the workspace cannot be resolved.

    Examples:
        ```python
        git_status(
            workspace='my_workspace',
            provider='GitHub'
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    response = api_core_request(
        method='get',
        endpoint=f'/workspaces/{workspace_id}/git/status',
        credential_type='user',
    )

    if not response.status_code in [200, 202]:
        logger.error(
            f'Failed to get status: {response.status_code} - {response.error}'
        )
        return False
    elif response.status_code == 202:
        # If the response is a long-running operation, handle it
        lro_response = lro_handler(response)
        if not lro_response.success:
            logger.warning(
                f'{lro_response.status_code}: {lro_response.error}.'
            )
            return None
        else:
            return lro_response.data
    elif response.status_code == 200:
        # If the response is successful, we can process it
        logger.info(f'Successfully initialized Git connection for workspace.')
        return response.data


def update_from_git(
    workspace: str,
    conflict_resolution_policy: Literal[
        'PreferRemote', 'PreferWorkspace'
    ] = 'PreferWorkspace',
    allow_override_items: bool = True,
) -> bool:
    """
    Poll the workspace"s Git status and update from Git if not up to date.
    Repeats until remoteCommitHash == workspaceHead or max retries reached.

    Args:
        workspace (str): The target workspace name or Id.
        conflict_resolution_policy (Literal["PreferRemote", "PreferWorkspace"], optional):
            The conflict resolution policy to use. Defaults to "PreferWorkspace".
        allow_override_items (bool, optional): Whether to allow overriding items. Defaults to True.

    Raises:
        SystemExit: Exits with code 1 if max retries are reached without success.

    Returns:
        bool: True if the workspace is up to date, False if it is still updating or an error occurred.

    Examples:
        ```python
        update_from_git(
            workspace='my_workspace',
            conflict_resolution_policy='PreferRemote',
            allow_override_items=False
        )
    ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    # Maximum number of attempts to poll/update the workspace
    MAX_RETRIES = 10

    # Time (in seconds) to wait between retry attempts
    RETRY_INTERVAL = 20

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f'Attempt {attempt}/{MAX_RETRIES}: Checking Git status...')
        status = git_status(workspace_id)

        if not status:
            logger.info('No status retrieved; retrying after delay...')
            time.sleep(RETRY_INTERVAL)
            continue

        remote_commit = status.get('remoteCommitHash') or None
        workspace_head = status.get('workspaceHead') or None
        logger.info(
            f'Remote Commit: {remote_commit} | Workspace Head: {workspace_head}'
        )

        # If already up to date
        if (
            remote_commit
            and workspace_head
            and remote_commit == workspace_head
        ):
            logger.info('Workspace is already up to date.')
            return True

        # Not up to date—prepare updateFromGit request
        logger.info('Workspace out of sync. Issuing updateFromGit request...')
        payload = {
            'remoteCommitHash': remote_commit,
            'workspaceHead': workspace_head,
            'conflictResolution': {
                'conflictResolutionPolicy': conflict_resolution_policy,
                'conflictResolutionType': 'Workspace',
            },
            'options': {'allowOverrideItems': allow_override_items},
        }
        resp = api_core_request(
            method='post',
            endpoint=f'/workspaces/{workspace_id}/git/updateFromGit',
            payload=payload,
            return_raw=True,
        )

        if resp.status_code in [200, 202]:
            logger.info('Update request sent successfully.')
        else:
            logger.error(
                f'Failed to send update request: {resp.json().get("errorCode")} - {resp.json().get("message")}'
            )
            time.sleep(RETRY_INTERVAL)
            continue

        # Wait before re-checking status
        logger.info(
            f'Waiting {RETRY_INTERVAL} seconds before rechecking status...'
        )
        time.sleep(RETRY_INTERVAL)

        # Re-check status after sending update
        status_after = git_status(workspace_id)
        if status_after:
            remote_after = status_after.get('remoteCommitHash') or None
            head_after = status_after.get('workspaceHead') or None
            logger.warning(
                f'Post-update | Remote: {remote_after} | Head: {head_after}'
            )
            if remote_after and head_after and remote_after == head_after:
                logger.info('Update successful. Workspace is now up to date.')
                return True
            else:
                logger.warning('Workspace still not up to date; retrying...')
        else:
            logger.error(
                'Failed to retrieve status after update attempt; retrying...'
            )
            return False
    logger.error('Max retries reached. The workspace may still be updating.')
    return False


@df
def commit_to_git(
    workspace: str,
    mode: Literal['All', 'Selective'] = 'All',
    selective_payload: dict = None,
    *,
    df: bool = False,
) -> dict:
    """
    Commits all changes from a Fabric/Power BI workspace to Git.

    Args:
        workspace (str): The name or ID of the Fabric workspace.
        mode (Literal["All", "Selective"], optional):
            The mode of the commit. "All" commits all changes, "Selective" commits only selected changes. Defaults to "All".
        selective_payload (dict, optional):
            The payload containing the specific changes to commit when in "Selective" mode.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        dict: The response data from the API if successful, or None if the workspace cannot be resolved.

    Raises:
        ValueError: If the workspace cannot be resolved.

    Examples:
        ```python
        commit_to_git(
            workspace='my_workspace',
            mode='Selective'
        )
    ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None
    payload = {'mode': mode}
    if mode == 'Selective' and selective_payload:
        # If in selective mode, include the specific changes to commit
        payload.update(selective_payload)
    response = api_core_request(
        method='post',
        endpoint=f'/workspaces/{workspace_id}/git/commitToGit',
        payload=payload,
        credential_type='user',
    )
    if not response.status_code in [200, 202]:
        logger.error(
            f'Failed to commit changes to git: {response.status_code} - {response.error}'
        )
        return False
    elif response.status_code == 202:
        # If the response is a long-running operation, handle it
        lro_response = lro_handler(response)
        if not lro_response.success:
            logger.warning(
                f'{lro_response.status_code}: {lro_response.error}.'
            )
            return None
        else:
            return lro_response.data
    elif response.status_code == 200:
        # If the response is successful, we can process it
        logger.info(f'Successfully committed changes to git.')
        return response.data


def git_disconnect(workspace: str) -> bool:
    """
    Disconnects the workspace from Git.

    Args:
        workspace (str): The name or ID of the Fabric workspace.

    Returns:
        bool: True if the disconnection was successful, False otherwise.

    Raises:
        ValueError: If the workspace cannot be resolved.

    Examples:
        ```python
        git_disconnect(
            workspace='my_workspace'
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None
    response = api_core_request(
        method='post',
        audience='fabric',
        endpoint=f'/workspaces/{workspace_id}/git/disconnect',
        return_raw=True,
    )
    if response.status_code != 200:
        logger.error(
            f'Failed to disconnect workspace from git: {response.status_code} - {response.error}'
        )
        return False
    logger.info(f'Successfully disconnected workspace from git.')
    return True


@df
def get_git_connection(workspace: str, *, df: bool = False) -> dict:
    """
    Retrieves the Git connections for a Fabric workspace.

    Args:
        workspace (str): The name or ID of the Fabric workspace.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        dict: The Git connections for the workspace if successful, or None if the workspace cannot be resolved.

    Raises:
        ValueError: If the workspace cannot be resolved.

    Examples:
        ```python
        get_git_connection(
            workspace='my_workspace'
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None
    response = api_core_request(
        method='get', endpoint=f'/workspaces/{workspace_id}/git/connection'
    )
    if response.status_code != 200:
        logger.warning(
            f'Failed to retrieve Git connections: {response.status_code} - {response.error}'
        )
        return None
    else:
        return response.data


@df
def get_my_git_credentials(workspace: str, *, df: bool = False) -> dict:
    """
    Retrieves the Git credentials for a Fabric workspace.

    Args:
        workspace (str): The name or ID of the Fabric workspace.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        dict: The Git credentials for the workspace if successful, or None if the workspace cannot be resolved.

    Raises:
        ValueError: If the workspace cannot be resolved.

    Examples:
        ```python
        get_my_git_credentials(
            workspace='my_workspace'
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None
    response = api_core_request(
        method='get',
        endpoint=f'/workspaces/{workspace_id}/git/myGitCredentials',
    )
    if response.status_code != 200:
        logger.warning(
            f'Failed to retrieve Git credentials: {response.status_code} - {response.error}'
        )
        return None
    else:
        return response.data


def update_my_git_connection(
    workspace: str,
    request_body_type: Literal[
        'UpdateGitCredentialsToAutomaticRequest',
        'UpdateGitCredentialsToConfiguredConnectionRequest',
        'UpdateGitCredentialsToNoneRequest',
    ] = 'UpdateGitCredentialsToAutomaticRequest',
    connection_id: str = None,
):
    """
    Updates the Git connection for a Fabric workspace.

    Args:
        workspace (str): The name or ID of the Fabric workspace.
        request_body_type (Literal["UpdateGitCredentialsToAutomaticRequest", "UpdateGitCredentialsToConfiguredConnectionRequest", "UpdateGitCredentialsToNoneRequest"], optional):
            The type of request body to use for the update. Defaults to "UpdateGitCredentialsToAutomaticRequest".

    Returns:
        dict: The response data from the API if successful, or None if the workspace cannot be resolved.

    Raises:
        ValueError: If the workspace cannot be resolved or if the request body type is invalid.

    Examples:
        ```python
        update_my_git_connection(
            workspace='my_workspace',
            request_body_type='UpdateGitCredentialsToAutomaticRequest'
        )
    ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None
    payload_automatic = {'source': 'Automatic'}
    payload_configured = {
        'source': 'ConfiguredConnection',
        'connectionId': connection_id,
    }
    payload_none = {'source': 'None'}
    if request_body_type == 'UpdateGitCredentialsToAutomaticRequest':
        payload = payload_automatic
    elif (
        request_body_type
        == 'UpdateGitCredentialsToConfiguredConnectionRequest'
    ):
        payload = payload_configured
    elif request_body_type == 'UpdateGitCredentialsToNoneRequest':
        payload = payload_none
    response = api_core_request(
        method='patch',
        endpoint=f'/workspaces/{workspace_id}/git/myGitCredentials',
        payload=payload,
    )
    if response.status_code != 200:
        logger.error(
            f'Failed to update Git connection: {response.status_code} - {response.error}'
        )
        return False
    else:
        return response.data


def ado_connect(
    workspace: str,
    organization_name: str,
    project_name: str,
    repository_name: str,
    branch_name: str = 'main',
    directory_name: str = '/',
) -> bool:
    """
    Connects a Fabric workspace to an Azure DevOps repository.

    Args:
        workspace (str): The name of the Fabric workspace.
        organization_name (str): The name of the Azure DevOps organization.
        project_name (str): The name of the Azure DevOps project.
        repository_name (str): The name of the Azure DevOps repository.
        branch_name (str): The name of the branch to connect to.
        directory_name (str, optional): The path to the folder where the repository is located. Defaults to "/".

    Returns:
        bool: True if the connection was successful, False otherwise.

    Raises:
        ValueError: If the workspace cannot be resolved.

    Examples:
        ```python
        ado_connect(
            workspace='my_workspace',
            organization_name='my_organization',
            project_name='my_project',
            repository_name='my_repository',
            branch_name='main',
            directory_name='/'
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None
    payload = {
        'gitProviderDetails': {
            'gitProviderType': 'AzureDevOps',
            'organizationName': organization_name,
            'projectName': project_name,
            'repositoryName': repository_name,
            'branchName': branch_name,
            'directoryName': directory_name,
        }
    }
    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/git/connect',
        method='post',
        payload=payload,
        credential_type='user',
    )
    if not response.status_code == 200:
        logger.error(
            f"Failed to connect Azure DevOps repository: {response.json().get('errorCode')} - {response.json().get('message')}"
        )
        return False
    else:
        logger.info(
            f"Successfully connected Azure DevOps repository '{repository_name}' to workspace '{workspace}'."
        )
        return True
