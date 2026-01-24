from typing import Any, Dict, List, Optional, Union

from pandas import DataFrame

from ..api.api import api_request
from ..core.folders import resolve_folder
from ..core.workspaces import resolve_workspace
from ..utils.decorators import df
from ..utils.logging import get_logger
from ..utils.utils import is_valid_uuid

logger = get_logger(__name__)


@df
def list_reports(
    workspace: str,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Returns a list of reports in a specified workspace.

    Args:
        workspace_id (str): The ID of the workspace.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, List[Dict[str, Any]], None]): A list of reports or a DataFrame if df is True.
    """
    return api_request(
        endpoint='/workspaces/' + resolve_workspace(workspace) + '/reports',
        support_pagination=True,
    )


def get_report_id(workspace: str, report_name: str) -> Union[str, None]:
    """
    Retrieves the ID of a report by its name from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        report_name (str): The name of the report.

    Returns:
        (Optional[str]): The ID of the report if found, otherwise None.

    Examples:
        ```python
        get_report_id('123e4567-e89b-12d3-a456-426614174000', 'SalesDataModel')
        ```
    """
    reports = list_reports(workspace=resolve_workspace(workspace), df=False)
    for report in reports:
        if report.get('displayName') == report_name:
            return report.get('id')
    return None


def resolve_report(
    workspace: str,
    report: str,
) -> Union[str, None]:
    if is_valid_uuid(report):
        return report
    else:
        return get_report_id(workspace, report)


@df
def get_report(
    workspace: str, report: str, *, df: Optional[bool] = True
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Retrieves a report by its name or ID from the specified workspace.

    Args:
        workspace_id (str): The workspace ID.
        report_id (str): The ID of the report.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The report details if found. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        get_report('123e4567-e89b-12d3-a456-426614174000', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    report_id = resolve_report(workspace, report)
    return api_request(
        endpoint='/workspaces/' + workspace_id + '/reports/' + report_id,
    )


@df
def create_report(
    workspace: str,
    display_name: str,
    item_definition: Dict[str, Any],
    *,
    description: Optional[str] = None,
    folder: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Creates a new report in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name of the report.
        item_definition (Dict[str, Any]): The definition of the report.
        description (Optional[str]): A description for the report.
        folder (Optional[str]): The ID of the folder to create the report in.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The created report details.

    Examples:
        ```python
        create_report(
            workspace_id='123e4567-e89b-12d3-a456-426614174000',
            display_name='SalesDataModel',
            item_definition= {}, # Definition dict of the report
            description='A report for sales data',
            folder_id='456e7890-e12b-34d5-a678-9012345678901',
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)

    payload = {'displayName': display_name, 'definition': item_definition}

    if description:
        payload['description'] = description

    if folder:
        folder_id = resolve_folder(folder, workspace_id=workspace_id)
        if folder_id:
            payload['folderId'] = folder_id

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/reports',
        method='post',
        payload=payload,
        support_lro=True,
    )


@df
def update_report(
    workspace: str,
    report: str,
    *,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    df: Optional[bool] = False,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Updates the properties of the specified report.

    Args:
        workspace (str): The workspace name or ID.
        report (str): The ID of the report to update.
        display_name (str, optional): The new display name for the report.
        description (str, optional): The new description for the report.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The updated report details if successful, otherwise None.

    Examples:
        ```python
        update_report(
            workspace_id='123e4567-e89b-12d3-a456-426614174000',
            report_id='456e7890-e12b-34d5-a678-9012345678901',
            display_name='UpdatedDisplayName',
            description='Updated description'
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)
    report_id = resolve_report(workspace, report)

    payload = {}

    if display_name:
        payload['displayName'] = display_name

    if description:
        payload['description'] = description

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/reports/' + report_id,
        method='patch',
        payload=payload,
    )


def delete_report(workspace: str, report: str) -> None:
    """
    Delete a report from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        report (str): The name or ID of the report to delete.

    Returns:
        None

    Examples:
        ```python
        delete_report('123e4567-e89b-12d3-a456-426614174000', '456e7890-e12b-34d5-a678-9012345678901')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    report_id = resolve_report(workspace, report)

    return api_request(
        endpoint='/workspaces/' + workspace_id + '/reports/' + report_id,
        method='delete',
    )


def get_report_definition(
    workspace: str, report: str
) -> Union[Dict[str, Any], None]:
    """
    Retrieves the definition of a report by its name or ID from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        report (str): The name or ID of the report.

    Returns:
        ( Union[Dict[str, Any], None]): The report definition if found, otherwise None.

    Examples:
        ```python
        get_report_definition(
            workspace_id='123e4567-e89b-12d3-a456-426614174000',
            report_id='456e7890-e12b-34d5-a678-9012345678901',
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)

    report_id = resolve_report(workspace, report)

    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/reports/'
        + report_id
        + '/getDefinition',
        method='post',
        support_lro=True,
    )


@df
def update_report_definition(
    workspace: str,
    report: str,
    item_definition: Dict[str, Any],
    *,
    df: Optional[bool] = True,
) -> Union[Dict[str, Any], None]:
    """
    Updates the definition of an existing report in the specified workspace.
    If the report does not exist, it returns None.

    Args:
        workspace (str): The workspace name or ID.
        report (str): The name or ID of the report to update.
        item_definition (Dict[str, Any]): The new definition for the report.
        df (Optional[bool]): If True or not provided, returns a DataFrame with flattened keys.
            If False, returns a list of dictionaries.

    Returns:
        (Union[Dict[str, Any], None]): The updated report details if successful, otherwise None.

    Examples:
        ```python
        update_report(
            workspace_id='123e4567-e89b-12d3-a456-426614174000',
            report_id='456e7890-e12b-34d5-a678-9012345678901',
            item_definition={...} # New definition dict of the report
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)
    report_id = resolve_report(workspace, report)
    params = {'updateMetadata': True}
    payload = {'definition': item_definition}
    return api_request(
        endpoint='/workspaces/'
        + workspace_id
        + '/reports/'
        + report_id
        + '/updateDefinition',
        method='post',
        payload=payload,
        params=params,
        support_lro=True,
    )
