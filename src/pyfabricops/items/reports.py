import glob
import json
import os
import re

import pandas

from ..api.api import _api_request, _lro_handler, _pagination_handler
from ..utils.decorators import df
from ..core.folders import resolve_folder
from ..utils.logging import get_logger
from ..cicd.reports_support import REPORT_DEFINITION
from ..utils.utils import (
    get_current_branch,
    get_root_path,
    get_workspace_suffix,
    is_valid_uuid,
    pack_item_definition,
    parse_definition_report,
    read_json,
    unpack_item_definition,
    write_json,
)
from ..core.workspaces import (
    _resolve_workspace_path,
    get_workspace,
    resolve_workspace,
)

logger = get_logger(__name__)


@df
def list_reports(
    workspace: str, *, df: bool = False
) -> list | pandas.DataFrame | None:
    """
    Lists all reports in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (list | pandas.DataFrame | None): A list of reports, a DataFrame with flattened keys, or None if not found.

    Examples:
        ```python
        list_reports('MyProjectWorkspace')
        list_reports('MyProjectWorkspace', df=True)
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None
    response = _api_request(endpoint=f'/workspaces/{workspace_id}/reports')
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        response = _pagination_handler(response)
        return response.data.get('value')


def resolve_report(
    workspace: str, report: str, *, silent: bool = False
) -> str | None:
    """
    Resolves a report name to its ID.

    Args:
        workspace (str): The ID of the workspace.
        report (str): The name of the report.

    Returns:
        str|None: The ID of the report, or None if not found.

    Examples:
        ```python
        resolve_report('MyProjectWorkspace', 'SalesReport')
        ```
    """
    if is_valid_uuid(report):
        return report
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    reports = list_reports(workspace, df=False)
    if not reports:
        return None

    for report_ in reports:
        if report_['displayName'] == report:
            return report_['id']
    if not silent:
        logger.warning(f"Report '{report}' not found.")
    return None


@df
def get_report(
    workspace: str, report: str, *, df: bool = False
) -> dict | pandas.DataFrame | None:
    """
    Retrieves a report by its name or ID from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        report (str): The name or ID of the report.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or pandas.DataFrame): The report details if found. If `df=True`, returns a DataFrame with flattened keys.

    Examples:
        ```python
        get_report('MyProjectWorkspace', 'SalesReport')
        get_report('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', df=True)
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    report_id = resolve_report(workspace_id, report)
    if not report_id:
        return None

    response = _api_request(
        endpoint=f'/workspaces/{workspace_id}/reports/{report_id}'
    )

    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


@df
def update_report(
    workspace: str,
    report: str,
    display_name: str = None,
    description: str = None,
    *,
    df: bool = False,
) -> dict | pandas.DataFrame:
    """
    Updates the properties of the specified report.

    Args:
        workspace (str): The workspace name or ID.
        report (str): The name or ID of the report to update.
        display_name (str, optional): The new display name for the report.
        description (str, optional): The new description for the report.
        df (bool, optional): Keyword-only. If True, returns a DataFrame with flattened keys. Defaults to False.

    Returns:
        (dict or None): The updated report details if successful, otherwise None.

    Examples:
        ```python
        update_report('MyProjectWorkspace', 'SalesDataModel', display_name='UpdatedSalesDataModel')
        update_report('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', description='Updated description')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    report_id = resolve_report(workspace_id, report)
    if not report_id:
        return None

    report_ = get_report(workspace_id, report_id)
    if not report_:
        return None

    report_description = report_['description']
    report_display_name = report_['displayName']

    payload = {}

    if report_display_name != display_name and display_name:
        payload['displayName'] = display_name

    if report_description != description and description:
        payload['description'] = description

    response = _api_request(
        endpoint=f'/workspaces/{workspace_id}/reports/{report_id}',
        method='put',
        payload=payload,
    )

    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        return response.data


def delete_report(workspace: str, report: str) -> None:
    """
    Delete a report from the specified workspace.

    Args:
        workspace (str): The name or ID of the workspace to delete.
        report (str): The name or ID of the report to delete.

    Returns:
        None: If the report is successfully deleted.

    Raises:
        ResourceNotFoundError: If the specified workspace is not found.

    Examples:
        ```python
        delete_report('MyProjectWorkspace', 'SalesReport')
        delete_report('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    report_id = resolve_report(workspace_id, report)
    if not report_id:
        return None

    response = _api_request(
        endpoint=f'/workspaces/{workspace_id}/reports/{report_id}',
        method='delete',
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return response.success
    else:
        return response.success


def get_report_definition(workspace: str, report: str) -> dict:
    """
    Retrieves the definition of a report by its name or ID from the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        report (str): The name or ID of the report.

    Returns:
        (dict): The report definition if found, otherwise None.

    Examples:
        ```python
        get_report_definition('MyProjectWorkspace', 'SalesReport')
        get_report_definition('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    # Resolving IDs
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    report_id = resolve_report(workspace_id, report)
    if not report_id:
        return None

    # Requesting
    response = _api_request(
        endpoint=f'/workspaces/{workspace_id}/reports/{report_id}/getDefinition',
        method='post',
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None

    # Check if it's a long-running operation (status 202)
    if response.status_code == 202:
        logger.debug('Long-running operation detected, handling LRO...')
        lro_response = _lro_handler(response)
        if not lro_response.success:
            logger.warning(
                f'{lro_response.status_code}: {lro_response.error}.'
            )
            return None
        return lro_response.data

    # For immediate success (status 200)
    return response.data


def update_report_definition(workspace: str, report: str, path: str):
    """
    Updates the definition of an existing report in the specified workspace.
    If the report does not exist, it returns None.

    Args:
        workspace (str): The workspace name or ID.
        report (str): The name or ID of the report to update.
        path (str): The path to the report definition.

    Returns:
        (dict or None): The updated report details if successful, otherwise None.

    Examples:
        ```python
        update_report_definition('MyProjectWorkspace', 'SalesReport', '/path/to/new/definition')
        update_report_definition('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', '/path/to/new/definition')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    report_id = resolve_report(workspace_id, report)
    if not report_id:
        return None

    definition = pack_item_definition(path)

    params = {'updateMetadata': True}

    response = _api_request(
        endpoint=f'/workspaces/{workspace_id}/reports/{report_id}/updateDefinition',
        method='post',
        payload={'definition': definition},
        params=params,
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None

    # Check if it's a long-running operation (status 202)
    if response.status_code == 202:
        logger.debug('Long-running operation detected, handling LRO...')
        lro_response = _lro_handler(response)
        if not lro_response.success:
            logger.warning(
                f'{lro_response.status_code}: {lro_response.error}.'
            )
            return None
        return lro_response.data

    # For immediate success (status 200)
    return response.data


def create_report(
    workspace: str,
    display_name: str,
    path: str,
    description: str = None,
    folder: str = None,
):
    """
    Creates a new report in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name of the report.
        description (str, optional): A description for the report.
        folder (str, optional): The folder to create the report in.
        path (str): The path to the report definition file.

    Returns:
        (dict): The created report details.

    Examples:
        ```python
        create_report('MyProjectWorkspace', 'SalesReport', '/path/to/definition')
        create_report('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', '/path/to/definition')
        ```
    """
    workspace_id = resolve_workspace(workspace)

    definition = pack_item_definition(path)

    payload = {'displayName': display_name, 'definition': definition}

    if description:
        payload['description'] = description

    if folder:
        folder_id = resolve_folder(workspace_id, folder)
        if not folder_id:
            logger.warning(
                f"Folder '{folder}' not found in workspace {workspace_id}."
            )
        else:
            payload['folderId'] = folder_id

    response = _api_request(
        endpoint=f'/workspaces/{workspace_id}/reports',
        method='post',
        payload=payload,
    )

    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None

    # Check if it's a long-running operation (status 202)
    if response.status_code == 202:
        logger.debug('Long-running operation detected, handling LRO...')
        lro_response = _lro_handler(response)
        if not lro_response.success:
            logger.warning(
                f'{lro_response.status_code}: {lro_response.error}.'
            )
            return None
        return lro_response.data

    # For immediate success (status 200)
    return response.data
