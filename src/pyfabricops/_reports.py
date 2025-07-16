import glob
import json
import os
import re

import pandas
from requests import get

from ._core import api_core_request, lro_handler, pagination_handler
from ._decorators import df
from ._folders import resolve_folder
from ._logging import get_logger
from ._utils import (
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
from ._workspaces import (
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
    response = api_core_request(endpoint=f'/workspaces/{workspace_id}/reports')
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None
    else:
        response = pagination_handler(response)
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

    response = api_core_request(
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

    response = api_core_request(
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

    response = api_core_request(
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
    response = api_core_request(
        endpoint=f'/workspaces/{workspace_id}/reports/{report_id}/getDefinition',
        method='post',
    )
    if not response.success:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None

    # Check if it's a long-running operation (status 202)
    if response.status_code == 202:
        logger.debug('Long-running operation detected, handling LRO...')
        lro_response = lro_handler(response)
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

    response = api_core_request(
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
        lro_response = lro_handler(response)
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

    response = api_core_request(
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
        lro_response = lro_handler(response)
        if not lro_response.success:
            logger.warning(
                f'{lro_response.status_code}: {lro_response.error}.'
            )
            return None
        return lro_response.data

    # For immediate success (status 200)
    return response.data


def export_report(
    workspace: str,
    report: str,
    project_path: str,
    *,
    workspace_path: str = None,
    update_config: bool = True,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
):
    """
    Exports a report definition to a specified folder structure.

    Args:
        workspace (str): The workspace name or ID.
        report (str): The name of the report to export.
        project_path (str): The root path of the project.
        workspace_path (str, optional): The path to the workspace folder. Defaults to "workspace".
        config_path (str): The path to the config file. Defaults to "config.json".
        branches_path (str): The path to the branches folder. Defaults to "branches".
        branch (str, optional): The branch name. Will be auto-detected if not provided.
        workspace_suffix (str, optional): The workspace suffix. Will be read from config if not provided.
        branches_path (str, optional): The path to the branches folder. Defaults to "branches".

    Returns:
        None

    Examples:
        ```python
        export_report('MyProjectWorkspace', 'SalesReport', '/path/to/project')
        export_report('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', '/path/to/project')
        ```
    """
    workspace_path = _resolve_workspace_path(
        workspace=workspace,
        workspace_suffix=workspace_suffix,
        project_path=project_path,
        workspace_path=workspace_path,
    )
    workspace_id = resolve_workspace(workspace)
    workspace_name = get_workspace(workspace_id).get('displayName')
    if not workspace_id:
        return None

    report_ = get_report(workspace_id, report)
    if not report_:
        return None

    report_id = report_['id']
    folder_id = None
    if 'folderId' in report_:
        folder_id = report_['folderId']

    definition = get_report_definition(workspace_id, report_id)
    if not definition:
        return None

    if update_config:
        # Get branch
        branch = get_current_branch(branch)

        # Get the workspace suffix and treating the name
        workspace_suffix = get_workspace_suffix(
            branch, workspace_suffix, branches_path
        )
        workspace_name_without_suffix = workspace_name.split(workspace_suffix)[
            0
        ]

        # Try to read existing config.json
        if not config_path:
            config_path = os.path.join(project_path, 'config.json')
        try:
            existing_config = read_json(config_path)
            logger.info(
                f'Found existing config file at {config_path}, merging workspace config...'
            )
        except FileNotFoundError:
            logger.warning(
                f'No existing config found at {config_path}, creating a new one.'
            )
            existing_config = {}

        config = existing_config[branch][workspace_name_without_suffix]

        report_id = report_['id']
        report_name = report_['displayName']
        report_descr = report_.get('description', '')

        # Find the key in the folders dict whose value matches folder_id
        if folder_id:
            folders = config['folders']
            item_path = next(
                (k for k, v in folders.items() if v == folder_id), None
            )
            item_path = os.path.join(project_path, workspace_path, item_path)
        else:
            item_path = os.path.join(project_path, workspace_path)

        unpack_item_definition(definition, f'{item_path}/{report_name}.Report')

        if 'reports' not in config:
            config['reports'] = {}
        if report_name not in config['reports']:
            config['reports'][report_name] = {}
        if 'id' not in config['reports'][report_name]:
            config['reports'][report_name]['id'] = report_id
        if 'description' not in config['reports'][report_name]:
            config['reports'][report_name]['description'] = report_descr

        if folder_id:
            if 'folder_id' not in config['reports'][report_name]:
                config['reports'][report_name]['folder_id'] = folder_id

        platform_path = f'{item_path}/{report_name}.Report/definition.pbir'
        definition = parse_definition_report(platform_path)
        """
        {
            'workspace_name': 'MyProject',
            'semantic_model_name': 'Financials',
            'semantic_model_id': '34f5e6d7-8a9b-0c1d-2e3f-456789abcdef'
        }
        """
        if 'parameters' not in config['reports'][report_name]:
            config['reports'][report_name]['parameters'] = definition

        # Update the config with the report details
        config['reports'][report_name]['id'] = report_id
        config['reports'][report_name]['description'] = report_descr
        config['reports'][report_name]['folder_id'] = folder_id
        config['reports'][report_name]['parameters'] = definition

        # Saving the updated config back to the config file
        existing_config[branch][workspace_name_without_suffix] = config
        write_json(existing_config, config_path)

    else:
        unpack_item_definition(
            definition, f'{project_path}/{workspace_path}/{report_name}.Report'
        )


def export_all_reports(
    workspace: str,
    project_path: str,
    *,
    workspace_path: str = None,
    update_config: bool = True,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
):
    """
    Exports all reports to the specified folder structure.

    Args:
        workspace (str): The workspace name or ID.
        path (str): The root path of the project.
        config_path (str): The path to the config file. Defaults to "config.json".
        branch (str, optional): The branch name. Will be auto-detected if not provided.
        workspace_suffix (str, optional): The workspace suffix. Will be read from config if not provided.
        branches_path (str, optional): The path to the branches folder. Defaults to "branches".

    Returns:
        None

    Examples:
        ```python
        export_all_reports('MyProjectWorkspace', '/path/to/project')
        export_all_reports('MyProjectWorkspace', '/path/to/project', branch='feature-branch')
        export_all_reports('MyProjectWorkspace', '/path/to/project', workspace_suffix='WorkspaceSuffix')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    reports = list_reports(workspace_id)
    if reports:
        for report in reports:
            export_report(
                workspace=workspace,
                report=report['displayName'],
                project_path=project_path,
                workspace_path=workspace_path,
                update_config=update_config,
                config_path=config_path,
                branch=branch,
                workspace_suffix=workspace_suffix,
                branches_path=branches_path,
            )


def deploy_report(
    workspace: str,
    display_name: str,
    project_path: str,
    *,
    workspace_path: str = None,
    config_path: str = None,
    description: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
):
    """
    Creates or updates a report in Fabric based on local folder structure.
    Automatically detects the folder_id based on where the report is located locally.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name of the report.
        project_path (str): The root path of the project.
        workspace_path (str): The workspace folder name. Defaults to "workspace".
        config_path (str): The path to the config file. Defaults to "config.json".
        description (str, optional): A description for the report.
        branch (str, optional): The branch name. Will be auto-detected if not provided.
        workspace_suffix (str, optional): The workspace suffix. Will be read from config if not provided.

    Examples:
        ```python
        deploy_report('MyProjectWorkspace', 'SalesReport', '/path/to/project')
        deploy_report('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', '/path/to/project')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    workspace_name = get_workspace(workspace_id).get('displayName')

    # Auto-detect branch and workspace suffix
    if not branch:
        branch = get_current_branch()

    if not workspace_suffix:
        workspace_suffix = get_workspace_suffix(branch, None, branches_path)

    workspace_name_without_suffix = workspace_name.split(workspace_suffix)[0]

    # Read config to get folder mappings
    if not config_path:
        config_path = os.path.join(project_path, 'config.json')

    try:
        config_file = read_json(config_path)
        config = config_file.get(branch, {}).get(
            workspace_name_without_suffix, {}
        )
        folders_mapping = config.get('folders', {})
    except:
        logger.warning(
            'No config file found. Cannot determine folder structure.'
        )
        folders_mapping = {}

    # Find where the report is located locally
    report_folder_path = None
    report_full_path = None

    # Check if report exists in workspace root
    workspace_path = _resolve_workspace_path(
        workspace=workspace,
        workspace_suffix=workspace_suffix,
        project_path=project_path,
        workspace_path=workspace_path,
    )
    root_path = f'{project_path}/{workspace_path}/{display_name}.Report'
    if os.path.exists(root_path):
        report_folder_path = workspace_path
        report_full_path = root_path
        logger.debug(f'Found report in workspace root: {root_path}')
    else:
        # Search for the report in subfolders (only once)
        base_search_path = f'{project_path}/{workspace_path}'
        logger.debug(
            f'Searching for {display_name}.Report in: {base_search_path}'
        )

        for root, dirs, files in os.walk(base_search_path):
            if f'{display_name}.Report' in dirs:
                report_full_path = os.path.join(root, f'{display_name}.Report')
                report_folder_path = os.path.relpath(
                    root, project_path
                ).replace('\\', '/')
                logger.debug(f'Found report in: {report_full_path}')
                logger.debug(f'Relative folder path: {report_folder_path}')
                break

    if not report_folder_path or not report_full_path:
        logger.debug(
            f'Report {display_name}.Report not found in local structure'
        )
        logger.debug(f'Searched in: {project_path}/{workspace_path}')
        return None

    # Determine folder_id based on local path
    folder_id = None

    if report_folder_path != workspace_path:
        folder_relative_path = report_folder_path.replace(
            f'{workspace_path}/', ''
        )

        logger.debug(f'Report located in subfolder: {folder_relative_path}')

        if folder_relative_path in folders_mapping:
            folder_id = folders_mapping[folder_relative_path]
            logger.debug(
                f'Found folder mapping: {folder_relative_path} -> {folder_id}'
            )
        else:
            logger.debug(
                f'No folder mapping found for: {folder_relative_path}'
            )
            logger.debug(
                f'Available folder mappings: {list(folders_mapping.keys())}'
            )
    else:
        logger.debug(f'Report will be created in workspace root')

    # Create the definition
    definition = pack_item_definition(report_full_path)

    # Check if report already exists (check only once)
    report_id = resolve_report(workspace_id, display_name, silent=True)

    if report_id:
        logger.info(f"Report '{display_name}' already exists, updating...")
        # Update existing report
        payload = {'definition': definition}
        if description:
            payload['description'] = description

        response = api_core_request(
            endpoint=f'/workspaces/{workspace_id}/reports/{report_id}/updateDefinition',
            method='post',
            payload=payload,
            params={'updateMetadata': True},
        )
        if response and response.error:
            logger.warning(
                f"Failed to update report '{display_name}': {response.error}"
            )
            return None

        logger.success(f"Successfully updated report '{display_name}'")
        return get_report(workspace_id, report_id)

    else:
        logger.info(f'Creating new report: {display_name}')
        # Create new report
        payload = {'displayName': display_name, 'definition': definition}
        if description:
            payload['description'] = description
        if folder_id:
            payload['folderId'] = folder_id

        response = api_core_request(
            endpoint=f'/workspaces/{workspace_id}/reports',
            method='post',
            payload=payload,
        )
        if response and response.error:
            logger.warning(
                f"Failed to create report '{display_name}': {response.error}"
            )
            return None

        logger.success(f"Successfully created report '{display_name}'")
        return get_report(workspace_id, display_name)


def deploy_all_reports(
    workspace: str,
    project_path: str,
    *,
    workspace_path: str = None,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
):
    """
    Deploy all reports from a project path.
    Searches recursively through all folders to find .Report directories.

    Args:
        workspace (str): The workspace name or ID.
        project_path (str): The root path of the project.
        workspace_path (str): The workspace folder name. Defaults to "workspace".
        config_path (str): The path to the config file. Defaults to "config.json".
        branch (str, optional): The branch name. Will be auto-detected if not provided.
        workspace_suffix (str, optional): The workspace suffix. Will be read from config if not provided.
        branches_path (str, optional): The path to the branches folder. Defaults to "branches".

    Returns:
        None

    Examples:
        ```python
        deploy_all_reports('MyProjectWorkspace', '/path/to/project')
        deploy_all_reports('MyProjectWorkspace', '/path/to/project', branch='feature-branch')
        deploy_all_reports('MyProjectWorkspace', '/path/to/project', workspace_suffix='WorkspaceSuffix')
        ```
    """
    workspace_path = _resolve_workspace_path(
        workspace=workspace,
        workspace_suffix=workspace_suffix,
        project_path=project_path,
        workspace_path=workspace_path,
    )
    base_path = f'{project_path}/{workspace_path}'

    if not os.path.exists(base_path):
        logger.error(f'Base path does not exist: {base_path}')
        return None

    # Find all report folders recursively
    report_folders = []
    for root, dirs, files in os.walk(base_path):
        for dir_name in dirs:
            if dir_name.endswith('.Report'):
                full_path = os.path.join(root, dir_name)
                # Extract just the report name (without .Report suffix)
                report_name = dir_name.replace('.Report', '')
                report_folders.append(
                    {
                        'name': report_name,
                        'path': full_path,
                        'relative_path': os.path.relpath(
                            full_path, project_path
                        ).replace('\\', '/'),
                    }
                )

    if not report_folders:
        logger.warning(f'No report folders found in {base_path}')
        return None

    logger.debug(f'Found {len(report_folders)} reports to deploy:')
    for report in report_folders:
        logger.debug(f"  - {report['name']} at {report['relative_path']}")

    # Deploy each report
    deployed_reports = []
    for report_info in report_folders:
        try:
            logger.debug(f"Deploying report: {report_info['name']}")
            result = deploy_report(
                workspace=workspace,
                display_name=report_info['name'],
                project_path=project_path,
                workspace_path=workspace_path,
                config_path=config_path,
                branch=branch,
                workspace_suffix=workspace_suffix,
                branches_path=branches_path,
            )
            if result:
                deployed_reports.append(report_info['name'])
                logger.debug(f"Successfully deployed: {report_info['name']}")
            else:
                logger.debug(f"Failed to deploy: {report_info['name']}")
        except Exception as e:
            logger.error(f"Error deploying {report_info['name']}: {str(e)}")

    logger.success(
        f'Deployment completed. Successfully deployed {len(deployed_reports)} reports.'
    )
    return deployed_reports


def deploy_all_reports_cicd(
    project_path: str,
    workspace_alias: str,
    *,
    config_path: str = None,
    branch: str = None,
    branches_path: str = None,
    workspace_suffix: str = None,
):
    """
    Deploy all reports in a CI/CD pipeline.

    Args:
        project_path (str): The path to the project.
        workspace_alias (str): The alias of the workspace.
        config_path (str, optional): The path to the config file.
        branch (str, optional): The branch to deploy.
        branches_path (str, optional): The path to the branches file.
        workspace_suffix (str, optional): The suffix for the workspace.

    Examples:
        ```python
        pf.deploy_all_reports_cicd(
            project_path='/path/to/project',
            workspace_alias='my_workspace',
            config_path='/path/to/config.json',
            branch='main',
            branches_path='/path/to/branches.json',
            workspace_suffix='dev'
        )
        ```
    """
    repo_root = get_root_path()

    if not branch:
        branch = get_current_branch()

    if not config_path:
        config_path = f'{project_path}/config.json'

    if not branches_path:
        branches_path = f'{repo_root}/branches.json'

    if not workspace_suffix:
        workspace_suffix = get_workspace_suffix(
            branch, workspace_suffix, branches_path
        )

    workspace_name = workspace_alias + workspace_suffix

    # For each report, we will define the report attached to the semantic model and deploy it.
    for report_path in glob.glob(
        f'{project_path}/**/*.Report', recursive=True
    ):
        print(f'Processing report: {report_path}')
        report_name = (
            report_path.replace('\\', '/').split('/')[-1].split('.Report')[0]
        )
        print(f'Deploying report: {report_name}')

        with open(f'{report_path}/definition.pbir', 'r') as f:
            report_definition = json.load(f)

        dataset_reference = report_definition['datasetReference']

        if 'byPath' in dataset_reference:
            dataset_path = dataset_reference['byPath']['path']
            dataset_name = dataset_path.split('/')[-1].split('.SemanticModel')[
                0
            ]

        elif 'byConnection' in dataset_reference:
            text_to_search = dataset_reference['byConnection'][
                'connectionString'
            ]
            # Capture the value after "initial catalog="
            match = re.search(r'initial catalog=([^;]+)', text_to_search)
            if match:
                dataset_name = match.group(1)

        print(f'Semantic model: {dataset_name}')

        # Search for the semantic model in the config.json
        with open(config_path, 'r') as f:
            config_content = json.load(f)
        config = config_content[branch]
        semantic_model_id = config[workspace_alias]['semantic_models'][
            dataset_name
        ]['id']
        print(f'Semantic Model ID: {semantic_model_id}')

        # Replace the definition.pbir with the updated template
        with open(
            os.path.join(repo_root, 'template_report_definition.pbir'),
            'r',
            encoding='utf-8',
        ) as f:
            report_definition_template = f.read()

        report_definition_updated = report_definition_template.replace(
            '#{workspace_name}#', workspace_name
        )
        report_definition_updated = report_definition_updated.replace(
            '#{semantic_model_name}#', dataset_name
        )
        report_definition_updated = report_definition_updated.replace(
            '#{semantic_model_id}#', semantic_model_id
        )

        # Write the updated report definition to the definition.pbir
        with open(
            f'{report_path}/definition.pbir', 'w', encoding='utf-8'
        ) as f:
            f.write(report_definition_updated)

        # Deploy the report
        deploy_report(
            workspace=workspace_name,
            display_name=report_name,
            project_path=project_path,
            branches_path=branches_path,
        )

        # Write back the original report_definition for the definition.pbir
        with open(
            f'{report_path}/definition.pbir', 'w', encoding='utf-8'
        ) as f:
            json.dump(report_definition, f, indent=2)


def convert_reports_to_local_references(
    project_path: str,
    *,
    branch: str = None,
):
    """
    Convert report definition.pbir files from byConnection to byPath references.

    This function scans all reports in the project, extracts the semantic model name
    from the connection string, finds the relative path to the semantic model directory,
    and updates the datasetReference to use local byPath instead of byConnection.

    Args:
        project_path (str): The path to the project directory.
        workspace_alias (str, optional): The alias of the workspace (workspace without suffix).
        branch (str, optional): The branch name. Defaults to current branch.

    Examples:
        ```python
        convert_reports_to_local_references(
            project_path='/path/to/project',
            branch='main'
        )
        ```
    """
    if not branch:
        branch = get_current_branch()

    converted_reports = []

    # Process all reports in the project
    for report_path in glob.glob(
        f'{project_path}/**/*.Report', recursive=True
    ):
        logger.info(f'Processing report: {report_path}')
        report_name = (
            report_path.replace('\\', '/').split('/')[-1].split('.Report')[0]
        )
        logger.info(f'Converting report: {report_name}')

        # Read the current definition.pbir
        definition_path = f'{report_path}/definition.pbir'

        if not os.path.exists(definition_path):
            logger.warning(f'definition.pbir not found: {definition_path}')
            continue

        try:
            with open(definition_path, 'r', encoding='utf-8') as f:
                report_definition = json.load(f)
        except Exception as e:
            logger.error(f'Error reading definition.pbir: {e}')
            continue

        # Check if it already uses byPath
        dataset_reference = report_definition.get('datasetReference', {})

        if 'byPath' in dataset_reference:
            logger.info(
                f'Report {report_name} already uses byPath reference - skipping'
            )
            continue

        if 'byConnection' not in dataset_reference:
            logger.warning(
                f'Report {report_name} has no byConnection reference - skipping'
            )
            continue

        # Extract semantic model name from connection string
        connection_string = dataset_reference['byConnection'].get(
            'connectionString', ''
        )

        # Capture the value after "initial catalog="
        match = re.search(r'initial catalog=([^;]+)', connection_string)
        if not match:
            logger.warning(
                f'Could not extract semantic model name from connection string in {report_name}'
            )
            continue

        dataset_name = match.group(1)
        logger.info(f'Found semantic model: {dataset_name}')

        # Find the semantic model directory relative to the report
        # Look for *.SemanticModel directories in the project
        semantic_model_pattern = (
            f'{project_path}/**/{dataset_name}.SemanticModel'
        )
        semantic_model_paths = glob.glob(
            semantic_model_pattern, recursive=True
        )

        if not semantic_model_paths:
            logger.error(
                f'Semantic model directory not found: {dataset_name}.SemanticModel'
            )
            continue

        if len(semantic_model_paths) > 1:
            logger.warning(
                f'Multiple semantic model directories found for {dataset_name}, using first one'
            )

        semantic_model_path = semantic_model_paths[0]
        logger.info(f'Found semantic model at: {semantic_model_path}')

        # Calculate relative path from definition.pbir to semantic model
        # The definition.pbir is inside the Report directory, so we need to go up one level first
        definition_dir = report_path  # This is the .Report directory
        relative_path = os.path.relpath(semantic_model_path, definition_dir)

        # Convert backslashes to forward slashes for consistency
        relative_path = relative_path.replace('\\', '/')

        logger.info(f'Relative path from definition.pbir: {relative_path}')

        # Update the dataset reference
        new_dataset_reference = {'byPath': {'path': relative_path}}

        # Create updated definition
        updated_definition = report_definition.copy()
        updated_definition['datasetReference'] = new_dataset_reference

        # Write the updated definition back to file
        try:
            with open(definition_path, 'w', encoding='utf-8') as f:
                json.dump(updated_definition, f, indent=2)

            logger.success(
                f'Successfully converted {report_name} to use byPath reference'
            )
            converted_reports.append(
                {
                    'report_name': report_name,
                    'semantic_model': dataset_name,
                    'relative_path': relative_path,
                }
            )

        except Exception as e:
            logger.error(f'Error writing updated definition.pbir: {e}')

    logger.success(
        f'Conversion completed. Successfully converted {len(converted_reports)} reports.'
    )
    return converted_reports
