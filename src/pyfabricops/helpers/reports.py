import glob
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Union

import pandas as pd
from pandas import DataFrame

from ..core.workspaces import resolve_workspace
from ..helpers.folders import (
    create_folders_from_path_string,
    resolve_folder_from_id_to_path,
)
from ..items.reports import (
    create_report,
    get_report,
    get_report_definition,
    list_reports,
    resolve_report,
    update_report_definition,
)
from ..items.semantic_models import get_semantic_model_id
from ..utils.decorators import df
from ..utils.exceptions import ResourceNotFoundError
from ..utils.logging import get_logger
from ..utils.utils import (
    extract_display_name_from_platform,
    extract_middle_path,
    list_paths_of_type,
    pack_item_definition,
    unpack_item_definition,
)

logger = get_logger(__name__)


def get_report_config(
    workspace: str, report: str
) -> Union[Dict[str, Any], None]:
    """
    Get a specific report config from a workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        report (str): The name or ID of the report.

    Returns:
        (Union[Dict[str, Any], None]): The dict config from the report.
    """
    item = report
    item_data = get_report(workspace, item, df=False)

    if item_data is None:
        return None

    else:
        config = {}
        config = config[item_data.get('displayName')] = {}

        config = {
            'id': item_data['id'],
            'description': item_data.get('description', None),
            'folder_id': ''
            if item_data.get('folderId') is None
            or pd.isna(item_data.get('folderId'))
            else item_data['folderId'],
        }

        return config


def get_all_reports_config(
    workspace: str,
) -> Union[Dict[str, Any], None]:
    """
    Get reports config from a workspace.

    Args:
        workspace (str): The name or ID from the workspace.

    Returns:
        (Union[Dict[str, Any], None]): The dict config of all reports in the workspace
    """
    items = list_reports(workspace, df=False)

    if items is None:
        return None

    config = {}

    for item in items:

        item_data = get_report(workspace, item['id'], df=False)

        config[item['displayName']] = {
            'id': item['id'],
            'description': item.get('description', None),
            'folder_id': ''
            if item.get('folderId') is None or pd.isna(item.get('folderId'))
            else item['folderId'],
        }

    return config


def export_report(
    workspace: str,
    report: str,
    path: Union[str, Path],
) -> None:
    """
    Export a report to path.

    Args:
        workspace (str): The name or ID of the workspace.
        report (str): The name or ID of the report.
        path (Union[str, Path]): The path to export to.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    item = get_report(workspace_id, report, df=False)
    try:
        folder_path = resolve_folder_from_id_to_path(
            workspace_id, item['folderId']
        )
    except:
        logger.info(f'{item["displayName"]}.Report is not inside a folder.')
        folder_path = None

    if folder_path is None:
        item_path = Path(path) / (item['displayName'] + '.Report')
    else:
        item_path = (
            Path(path) / folder_path / (item['displayName'] + '.Report')
        )
    os.makedirs(item_path, exist_ok=True)

    definition = get_report_definition(workspace_id, item['id'])
    if definition is None:
        return None

    unpack_item_definition(definition, item_path)

    logger.success(
        f'`{item["displayName"]}.Report` was exported to {item_path} successfully.'
    )
    return None


def export_all_reports(
    workspace: str,
    path: Union[str, Path],
) -> None:
    """
    Export a report to path.

    Args:
        workspace (str): The name or ID of the workspace.
        path (Union[str, Path]): The path to export to.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    items = list_reports(workspace_id, df=False)
    if items is None:
        return None

    for item in items:
        try:
            folder_path = resolve_folder_from_id_to_path(
                workspace_id, item['folderId']
            )
        except:
            logger.info(
                f'{item["displayName"]}.Report is not inside a folder.'
            )
            folder_path = None

        if folder_path is None:
            item_path = Path(path) / (item['displayName'] + '.Report')
        else:
            item_path = (
                Path(path) / folder_path / (item['displayName'] + '.Report')
            )
        os.makedirs(item_path, exist_ok=True)

        definition = get_report_definition(workspace_id, item['id'])
        if definition is None:
            return None

        unpack_item_definition(definition, item_path)

    logger.success(f'All reports were exported to {path} successfully.')
    return None


def extract_report_definition_pbir(path: Union[str, Path]) -> Dict[str, str]:
    """
    Parse a Power BI report definition file to extract workspace and semantic model information.

    Args:
        path (str): The path to the Power BI report definition file.

    Returns:
        dict: A dictionary containing the workspace name, semantic model name, and semantic model ID.

    Raises:
        ResourceNotFoundError: If the specified file does not exist or is not in the expected format.
        FileNotFoundError: If the specified file does not exist.
        json.JSONDecodeError: If the file content is not valid JSON.

    Examples:
        ```python
        parse_definition_report('MyProject/workspace/path/to/Financials.Report/definition.pbir')
        ```
    """
    path = Path(path) / 'definition.pbir'
    with open(path, encoding='utf-8') as f:
        data = json.load(f)

    # Check if the file contains the expected structure
    if (
        'datasetReference' not in data
        or 'byConnection' not in data['datasetReference']
    ):
        raise ResourceNotFoundError(
            f'Invalid report definition file: {path}. Expected structure not found.'
        )
    by_conn = data['datasetReference']['byConnection']
    conn_str = by_conn['connectionString']
    # model_id = by_conn['pbiModelDatabaseName']

    # 1) workspace_name: part after the last slash and before the semicolon
    workspace_name = conn_str.split('/')[-1].split(';')[0]

    # 2) semantic_model_name: "initial catalog" value from the connection string
    m = re.search(r'initial catalog=([^;]+)', conn_str, re.IGNORECASE)
    semantic_model_name = m.group(1) if m else None

    # 3) semantic_model_id: takes directly from the pbiModelDatabaseName field
    m_id = re.search(r'semanticmodelid=([^;]+)', conn_str, re.IGNORECASE)
    semantic_model_id = m_id.group(1) if m_id else None

    return {
        'workspace_name': workspace_name,
        'semantic_model_name': semantic_model_name,
        'semantic_model_id': semantic_model_id,
    }


@df
def deploy_report(
    workspace: str,
    path: str,
    start_path: Optional[str] = None,
    description: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Deploy a report to workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        path (str): The path to the report.
        start_path (Optional[str]): The starting path for folder creation.
        description (Optional[str]): Description for the report.
        df (Optional[bool]): If True, returns a DataFrame, otherwise returns a dictionary.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The deployed report or None if deployment fails.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    display_name = extract_display_name_from_platform(path)
    if display_name is None:
        return None

    item_id = resolve_report(workspace_id, display_name)

    folder_path_string = extract_middle_path(path, start_path=start_path)
    folder_id = create_folders_from_path_string(
        workspace_id, folder_path_string
    )

    item_definition = pack_item_definition(path)

    if item_id is None:
        return create_report(
            workspace_id,
            display_name=display_name,
            item_definition=item_definition,
            description=description,
            folder=folder_id,
            df=False,
        )

    else:
        return update_report_definition(
            workspace_id,
            item_id,
            item_definition=item_definition,
            df=False,
        )


def deploy_all_reports(
    workspace: str,
    path: str,
    start_path: Optional[str] = None,
) -> None:
    """
    Deploy all reports to workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        path (str): The path to the reports.
        start_path (Optional[str]): The starting path for folder creation.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    reports_paths = list_paths_of_type(path, 'Report')

    for path_ in reports_paths:

        display_name = extract_display_name_from_platform(path_)
        if display_name is None:
            return None

        item_id = resolve_report(workspace_id, display_name)

        folder_path_string = extract_middle_path(path_, start_path=start_path)
        folder_id = create_folders_from_path_string(
            workspace_id, folder_path_string
        )

        item_definition = pack_item_definition(path_)

        if item_id is None:
            create_report(
                workspace_id,
                display_name=display_name,
                item_definition=item_definition,
                folder=folder_id,
                df=False,
            )

        else:
            update_report_definition(
                workspace_id,
                item_id,
                item_definition=item_definition,
                df=False,
            )

    logger.success(
        f'All reports were deployed to workspace "{workspace}" successfully.'
    )
    return None


def convert_report_definition_to_by_path(
    report_path: Union[str, Path],
    workspace_path: Union[str, Path],
) -> None:
    """
    Convert report definition to use byPath reference.

    Args:
        report_path (Union[str, Path]): The file path to the report.
        workspace_path (Union[str, Path]): The file path to the workspace.
    """
    # Read the current definition.pbir
    definition_path = f'{report_path}/definition.pbir'

    if not os.path.exists(definition_path):
        logger.warning(f'definition.pbir not found: {definition_path}')
        return None

    try:
        with open(definition_path, 'r', encoding='utf-8') as f:
            report_definition = json.load(f)
    except Exception as e:
        logger.error(f'Error reading definition.pbir: {e}')
        return None

    # Check if it already uses byPath
    dataset_reference = report_definition.get('datasetReference', {})

    if 'byPath' in dataset_reference:
        logger.info(f'Report already uses byPath reference.')
        return None

    if 'byConnection' not in dataset_reference:
        logger.warning(f'Report has no byConnection reference.')
        return None

    # Extract semantic model name from connection string
    connection_string = dataset_reference['byConnection'].get(
        'connectionString', ''
    )

    # Capture the value after "initial catalog="
    match = re.search(r'initial catalog=([^;]+)', connection_string)
    if not match:
        logger.warning(
            f'Could not extract semantic model name from connection string.'
        )
        return None

    semantic_model_name = match.group(1).strip('"')

    logger.info(f'Found semantic model: {semantic_model_name}')

    # Find the semantic model directory relative to the report
    # Look for *.SemanticModel directories in the project
    semantic_model_pattern = (
        f'{workspace_path}/**/{semantic_model_name}.SemanticModel'
    )
    semantic_model_paths = glob.glob(semantic_model_pattern, recursive=True)

    if not semantic_model_paths:
        logger.error(
            f'Semantic model directory not found: {semantic_model_name}.SemanticModel'
        )
        return None

    if len(semantic_model_paths) > 1:
        logger.warning(
            f'Multiple semantic model directories found for {semantic_model_name}, using first one'
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
            f'Successfully converted report to use byPath reference'
        )

    except Exception as e:
        logger.error(f'Error writing updated definition.pbir: {e}')

    return None


REPORT_DEFINITION = """{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
  "version": "4.0",
  "datasetReference": {
    "byConnection": {
      "connectionString": "Data Source=powerbi://api.powerbi.com/v1.0/myorg/#{workspace_name}#;initial catalog=#{semantic_model_name}#;integrated security=ClaimsToken;semanticmodelid=#{semantic_model_id}#"
    }
  }
}"""


def convert_report_definition_to_by_connection(
    workspace_name: Union[str, Path],
    report_path: Union[str, Path],
) -> None:
    """
    Convert report definition to use byConnection reference.

    Args:
        workspace_name: The name of the Power BI workspace.
        report_path: The file path to the report.
    """
    with open(f'{report_path}/definition.pbir', 'r') as f:
        report_definition = json.load(f)

    dataset_reference = report_definition['datasetReference']

    if 'byPath' in dataset_reference:
        dataset_path = dataset_reference['byPath']['path']
        dataset_name = dataset_path.split('/')[-1].split('.SemanticModel')[0]

    elif 'byConnection' in dataset_reference:
        text_to_search = dataset_reference['byConnection']['connectionString']
        # Capture the value after "initial catalog="
        match = re.search(r'initial catalog=([^;]+)', text_to_search)
        if match:
            dataset_name = match.group(1)

    print(f'Semantic model: {dataset_name}')

    # Get the semantic model ID
    semantic_model_id = get_semantic_model_id(workspace_name, dataset_name)
    if semantic_model_id is None:
        logger.error(f'Could not find semantic model ID for {dataset_name}')
        return None

    report_definition_template = REPORT_DEFINITION

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
    with open(f'{report_path}/definition.pbir', 'w', encoding='utf-8') as f:
        f.write(report_definition_updated)
