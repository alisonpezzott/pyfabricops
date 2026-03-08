from typing import Any, Dict, List, Literal, Optional, Union

from pandas import DataFrame

from ..api.api import api_request
from ..core.workspaces import resolve_workspace
from ..utils.decorators import df
from ..utils.logging import get_logger
from .lakehouses import resolve_lakehouse

logger = get_logger(__name__)


shortcuts_payloads_targets = {
    'adlsGen2': {
        'connectionId': '{{target_connection_id}}',
        'location': '{{target_location}}',
        'subpath': '{{target_subpath}}',
    },
    'amazonS3': {
        'connectionId': '{{target_connection_id}}',
        'location': '{{target_location}}',
        'subpath': '{{target_subpath}}',
    },
    'azureBlobStorage': {
        'connectionId': '{{target_connection_id}}',
        'location': '{{target_location}}',
        'subpath': '{{target_subpath}}',
    },
    'dataverse': {
        'connectionId': '{{target_connection_id}}',
        'deltaLakeFolder': '{{target_delta_lake_folder}}',
        'environmentDomain': '{{target_environment_domain}}',
        'tableName': '{{target_table_name}}',
    },
    'googleCloudStorage': {
        'connectionId': '{{target_connection_id}}',
        'location': '{{target_location}}',
        'subpath': '{{target_subpath}}',
    },
    'oneLake': {
        'itemId': '{{target_item_id}}',
        'path': '{{target_path}}',
        'workspace_id': '{{target_workspace_id}}',
        'connectionId': '{{target_connection_id}}',
    },
    's3Compatible': {
        'bucket': '{{target_bucket}}',
        'connectionId': '{{target_connection_id}}',
        'location': '{{target_location}}',
        'subpath': '{{target_subpath}}',
    },
}


@df
def list_shortcuts(
    workspace: str,
    lakehouse: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Lists all shortcuts in the specified workspace and lakehouse

    Args:
        workspace (str): The workspace name or ID.
        lakehouse (str): The lakehouse name or ID.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A list of shortcuts, a DataFrame with flattened keys, or None if not found.

    Examples:
        ```python
        list_shortcuts('MyProjectWorkspace', 'MyLakehouse')
        list_shortcuts('MyProjectWorkspace', 'MyLakehouse', df=True)
        ```
    """
    workspace_id = resolve_workspace(workspace)

    lakehouse_id = resolve_lakehouse(workspace_id, lakehouse)

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/items/'
        + lakehouse_id
        + '/shortcuts',
        support_pagination=True,
    )


@df
def get_shortcut(
    workspace: str,
    lakehouse: str,
    shortcut_path: str,
    shortcut_name: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Retrieves a specific shortcut in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        lakehouse (str): The lakehouse name or ID.
        shortcut_path (str): The shortcut path.
        shortcut_name (str): The shortcut name or ID.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The shortcut details, a DataFrame with flattened keys, or None if not found.

    Examples:
        ```python
        get_shortcut('MyProjectWorkspace', 'MyLakehouse', 'Tables', 'MyShortcut')
        get_shortcut('MyProjectWorkspace', 'MyLakehouse', 'Files/Raw', 'MyShortcut', df=True)
        ```
    """
    workspace_id = resolve_workspace(workspace)
    lakehouse_id = resolve_lakehouse(workspace_id, lakehouse)
    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/items/'
        + lakehouse_id
        + '/shortcuts/'
        + shortcut_path
        + '/'
        + shortcut_name,
    )


def delete_shortcut(
    workspace: str, lakehouse: str, shortcut_path: str, shortcut_name: str
) -> None:
    """
    Deletes a specific shortcut in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        lakehouse (str): The lakehouse name or ID.
        shortcut_path (str): The shortcut path.
        shortcut_name (str): The shortcut name or ID.

    Returns:
        None

    Examples:
        ```python
        delete_shortcut('MyProjectWorkspace', 'MyLakehouse', 'Tables', 'MyShortcut')
        delete_shortcut('MyProjectWorkspace', 'MyLakehouse', 'Files/Raw', 'MyShortcut')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    lakehouse_id = resolve_lakehouse(workspace_id, lakehouse)
    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/items/'
        + lakehouse_id
        + '/shortcuts/'
        + shortcut_path
        + '/'
        + shortcut_name,
        method='delete',
    )


@df
def create_shortcut(
    workspace: str,
    lakehouse: str,
    shortcut_path: str,
    shortcut_name: str,
    conflict_policy: Literal[
        'Abort', 'GenerateUniqueName', 'CreateOrOverwrite', 'OverwriteOnly'
    ] = 'Abort',
    target_type: Literal[
        'adlsGen2',
        'amazonS3',
        'azureBlobStorage',
        'dataverse',
        'googleCloudStorage',
        'oneLake',
        's3Compatible',
    ] = 'oneLake',
    *,
    target_connection_id: Optional[str] = None,
    target_location: Optional[str] = None,
    target_subpath: Optional[str] = None,
    target_delta_lake_folder: Optional[str] = None,
    target_environment_domain: Optional[str] = None,
    target_table_name: Optional[str] = None,
    target_item_id: Optional[str] = None,
    target_path: Optional[str] = None,
    target_workspace_id: Optional[str] = None,
    target_bucket: Optional[str] = None,
    custom_target_payload: Optional[dict] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Creates a new shortcut in the specified lakehouse.

    Args:
        workspace (str): The workspace name or ID.
        lakehouse (str): The lakehouse name or ID.
        shortcut_path (str): The path where the shortcut will be created (e.g., 'Tables', 'Files/Raw').
        shortcut_name (str): The name of the shortcut.
        conflict_policy (str, optional): Policy for handling naming conflicts. Defaults to 'Abort'.
        target_type (str, optional): Type of target system. Defaults to 'oneLake'.
        target_connection_id (str, optional): Connection ID for external targets.
        target_location (str, optional): Target location for cloud storage targets.
        target_subpath (str, optional): Subpath within the target location.
        target_delta_lake_folder (str, optional): Delta Lake folder for Dataverse targets.
        target_environment_domain (str, optional): Environment domain for Dataverse targets.
        target_table_name (str, optional): Table name for Dataverse targets.
        target_item_id (str, optional): Item ID for OneLake targets.
        target_path (str, optional): Path for OneLake targets.
        target_workspace_id (str, optional): Workspace ID for OneLake targets.
        target_bucket (str, optional): Bucket name for S3-compatible targets.
        custom_target_payload (dict, optional): Custom target payload to override automatic generation.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The created shortcut information or None if failed.

    Examples:
        ```python
        # Create OneLake shortcut
        create_shortcut(
            workspace='MyWorkspace',
            lakehouse='MyLakehouse',
            shortcut_path='Tables',
            shortcut_name='MyTable',
            target_type='oneLake',
            target_item_id='abc123',
            target_path='/Tables/SourceTable',
            target_workspace_id='def456'
        )

        # Create ADLS Gen2 shortcut
        create_shortcut(
            workspace='MyWorkspace',
            lakehouse='MyLakehouse',
            shortcut_path='Files/External',
            shortcut_name='ExternalData',
            target_type='adlsGen2',
            target_connection_id='conn123',
            target_location='mycontainer',
            target_subpath='/data/raw'
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)

    lakehouse_id = resolve_lakehouse(workspace_id, lakehouse)

    available_conflict_policies = [
        'Abort',
        'GenerateUniqueName',
        'CreateOrOverwrite',
        'OverwriteOnly',
    ]
    if conflict_policy not in available_conflict_policies:
        logger.warning(f'Invalid conflict policy: {conflict_policy}.')
        return None

    payload = {
        'path': shortcut_path,
        'name': shortcut_name,
    }

    if custom_target_payload:
        payload['target'] = custom_target_payload
    else:
        # Get the base template for the target type
        target_template = shortcuts_payloads_targets[target_type].copy()

        # Create mapping of placeholders to actual values
        placeholder_mapping = {
            '{{target_connection_id}}': target_connection_id,
            '{{target_location}}': target_location,
            '{{target_subpath}}': target_subpath,
            '{{target_delta_lake_folder}}': target_delta_lake_folder,
            '{{target_environment_domain}}': target_environment_domain,
            '{{target_table_name}}': target_table_name,
            '{{target_item_id}}': target_item_id,
            '{{target_path}}': target_path,
            '{{target_workspace_id}}': target_workspace_id,
            '{{target_bucket}}': target_bucket,
        }

        # Replace placeholders with actual values and remove None values
        target_payload = {}
        for key, template_value in target_template.items():
            if template_value in placeholder_mapping:
                actual_value = placeholder_mapping[template_value]
                if actual_value is not None:
                    target_payload[key] = actual_value
            else:
                # If it's not a placeholder, use the value as-is
                target_payload[key] = template_value

        payload['target'] = target_payload

    params = {'shortcutConflictPolicy': conflict_policy}

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/items/'
        + lakehouse_id
        + '/shortcuts',
        method='post',
        payload=payload,
        params=params,
    )
