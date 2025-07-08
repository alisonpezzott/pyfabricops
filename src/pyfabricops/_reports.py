import logging
import os

import pandas

from ._core import api_core_request, lro_handler, pagination_handler
from ._decorators import df
from ._folders import resolve_folder
from ._utils import (
    get_current_branch,
    get_workspace_suffix,
    is_valid_uuid,
    pack_item_definition,
    parse_definition_report,
    read_json,
    unpack_item_definition,
    write_json,
)
from ._workspaces import get_workspace, resolve_workspace

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


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
        return response.data
    else:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None


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
        return response.data
    else:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None


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
        return response.data
    else:
        logger.warning(f'{response.status_code}: {response.error}.')
        return None


def export_report(
    workspace: str,
    report: str,
    project_path: str,
    workspace_path: str = 'workspace',
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
    workspace_path: str = 'workspace',
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
    workspace_path: str = 'workspace',
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

        logger.info(f"Successfully updated report '{display_name}'")
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

        logger.info(f"Successfully created report '{display_name}'")
        return get_report(workspace_id, display_name)


def deploy_all_reports(
    workspace: str,
    project_path: str,
    workspace_path: str = 'workspace',
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

    logger.info(
        f'Deployment completed. Successfully deployed {len(deployed_reports)} reports.'
    )
    return deployed_reports
