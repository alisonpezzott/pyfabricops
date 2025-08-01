import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from pandas import DataFrame

from ..core.workspaces import resolve_workspace
from ..helpers.folders import (
    create_folders_from_path_string,
    resolve_folder_from_id_to_path,
)
from ..items.data_pipelines import (
    create_data_pipeline,
    get_data_pipeline,
    get_data_pipeline_definition,
    list_data_pipelines,
    resolve_data_pipeline,
    update_data_pipeline_definition,
)
from ..utils.decorators import df
from ..utils.logging import get_logger
from ..utils.utils import (
    extract_display_name_from_platform,
    extract_middle_path,
    list_paths_of_type,
    pack_item_definition,
    unpack_item_definition,
)

logger = get_logger(__name__)


def get_data_pipeline_config(
    workspace: str, data_pipeline: str
) -> Union[Dict[str, Any], None]:
    """
    Get a specific data_pipeline config from a workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        data_pipeline (str): The name or ID of the data_pipeline.

    Returns:
        (Union[Dict[str, Any], None]): The dict config from the data_pipeline.
    """
    item = data_pipeline
    item_data = get_data_pipeline(workspace, item, df=False)

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


def get_all_data_pipelines_config(
    workspace: str,
) -> Union[Dict[str, Any], None]:
    """
    Get data_pipelines config from a workspace.

    Args:
        workspace (str): The name or ID from the workspace.

    Returns:
        (Union[Dict[str, Any], None]): The dict config of all data_pipelines in the workspace
    """
    items = list_data_pipelines(workspace, df=False)

    if items is None:
        return None

    config = {}

    for item in items:

        item_data = get_data_pipeline(workspace, item['id'], df=False)

        config[item['displayName']] = {
            'id': item['id'],
            'description': item.get('description', None),
            'folder_id': ''
            if item.get('folderId') is None or pd.isna(item.get('folderId'))
            else item['folderId'],
        }

    return config


def export_data_pipeline(
    workspace: str,
    data_pipeline: str,
    path: Union[str, Path],
) -> None:
    """
    Export a data_pipeline to path.

    Args:
        workspace (str): The name or ID of the workspace.
        data_pipeline (str): The name or ID of the data_pipeline.
        path (Union[str, Path]): The path to export to.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    item = get_data_pipeline(workspace_id, data_pipeline, df=False)
    try:
        folder_path = resolve_folder_from_id_to_path(
            workspace_id, item['folderId']
        )
    except:
        logger.info(
            f'{item["displayName"]}.DataPipeline is not inside a folder.'
        )
        folder_path = None

    if folder_path is None:
        item_path = Path(path) / (item['displayName'] + '.DataPipeline')
    else:
        item_path = (
            Path(path) / folder_path / (item['displayName'] + '.DataPipeline')
        )
    os.makedirs(item_path, exist_ok=True)

    definition = get_data_pipeline_definition(workspace_id, item['id'])
    if definition is None:
        return None

    unpack_item_definition(definition, item_path)

    logger.success(
        f'`{item["displayName"]}.DataPipeline` was exported to {item_path} successfully.'
    )
    return None


def export_all_data_pipelines(
    workspace: str,
    path: Union[str, Path],
) -> None:
    """
    Export a data_pipeline to path.

    Args:
        workspace (str): The name or ID of the workspace.
        path (Union[str, Path]): The path to export to.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    items = list_data_pipelines(workspace_id, df=False)
    if items is None:
        return None

    for item in items:
        try:
            folder_path = resolve_folder_from_id_to_path(
                workspace_id, item['folderId']
            )
        except:
            logger.info(
                f'{item["displayName"]}.DataPipeline is not inside a folder.'
            )
            folder_path = None

        if folder_path is None:
            item_path = Path(path) / (item['displayName'] + '.DataPipeline')
        else:
            item_path = (
                Path(path)
                / folder_path
                / (item['displayName'] + '.DataPipeline')
            )
        os.makedirs(item_path, exist_ok=True)

        definition = get_data_pipeline_definition(workspace_id, item['id'])
        if definition is None:
            return None

        unpack_item_definition(definition, item_path)

    logger.success(f'All data_pipelines were exported to {path} successfully.')
    return None


@df
def deploy_data_pipeline(
    workspace: str,
    path: str,
    start_path: Optional[str] = None,
    description: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Deploy a data_pipeline to workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        path (str): The path to the data_pipeline.
        start_path (Optional[str]): The starting path for folder creation.
        description (Optional[str]): Description for the data_pipeline.
        df (Optional[bool]): If True, returns a DataFrame, otherwise returns a dictionary.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The deployed data_pipeline or None if deployment fails.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    display_name = extract_display_name_from_platform(path)
    if display_name is None:
        return None

    item_id = resolve_data_pipeline(workspace_id, display_name)

    folder_path_string = extract_middle_path(path, start_path=start_path)
    folder_id = create_folders_from_path_string(
        workspace_id, folder_path_string
    )

    item_definition = pack_item_definition(path)

    if item_id is None:
        return create_data_pipeline(
            workspace_id,
            display_name=display_name,
            item_definition=item_definition,
            description=description,
            folder=folder_id,
            df=False,
        )

    else:
        return update_data_pipeline_definition(
            workspace_id,
            item_id,
            item_definition=item_definition,
            df=False,
        )


def deploy_all_data_pipelines(
    workspace: str,
    path: str,
    start_path: Optional[str] = None,
) -> None:
    """
    Deploy all data_pipelines to workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        path (str): The path to the data_pipelines.
        start_path (Optional[str]): The starting path for folder creation.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    data_pipelines_paths = list_paths_of_type(path, 'DataPipeline')

    for path_ in data_pipelines_paths:

        display_name = extract_display_name_from_platform(path_)
        if display_name is None:
            return None

        item_id = resolve_data_pipeline(workspace_id, display_name)

        folder_path_string = extract_middle_path(path_, start_path=start_path)
        folder_id = create_folders_from_path_string(
            workspace_id, folder_path_string
        )

        item_definition = pack_item_definition(path_)

        if item_id is None:
            create_data_pipeline(
                workspace_id,
                display_name=display_name,
                item_definition=item_definition,
                folder=folder_id,
                df=False,
            )

        else:
            update_data_pipeline_definition(
                workspace_id,
                item_id,
                item_definition=item_definition,
                df=False,
            )

    logger.success(
        f'All data_pipelines were deployed to workspace "{workspace}" successfully.'
    )
    return None


def extract_data_pipeline_variables(path: str) -> List[Dict[str, str]]:
    """
    Extract data pipeline variables from the `pipeline-content.json` file.

    Args:
        path (str): The path to the data pipeline.

    Returns:
        List[Dict[str, str]]: A list of dictionaries containing the extracted variables.
    """

    path = Path(path) / 'pipeline-content.json'

    with open(path, 'r') as f:
        content = json.load(f)

    activities = content['properties']['activities']

    variables = []

    for activity_index, activity in enumerate(activities):
        activity_name = activity['name']

        subactivities = activity['typeProperties']['activities']
        for subactivity_index, subactivity in enumerate(subactivities):
            subactivity_name = subactivity['name']
            properties = subactivity['typeProperties']

            source = properties['source']['datasetSettings']
            source_database = source['typeProperties']['database']
            source_connection = source['externalReferences']['connection']

            sink = properties['sink']['datasetSettings']['linkedService']
            sink_name = sink['name']
            sink_properties = sink['properties']['typeProperties']
            sink_workspace_id = sink_properties['workspaceId']
            sink_artifact_id = sink_properties['artifactId']

            variables.append(
                {
                    'activity_index': activity_index,
                    'activity_name': activity_name,
                    'subactivity_index': subactivity_index,
                    'subactivity_name': subactivity_name,
                    'source_database': source_database,
                    'source_connection': source_connection,
                    'sink_name': sink_name,
                    'sink_workspace_id': sink_workspace_id,
                    'sink_artifact_id': sink_artifact_id,
                }
            )

    return variables


def replace_data_pipeline_variables_with_placeholders(
    path: str, variables: List[Dict[str, str]]
) -> None:
    """
    Replace data pipeline variables with placeholders in the pipeline content JSON.

    Args:
        path (str): The path to the data pipeline.
        variables (List[Dict[str, str]]): The list of variables to replace.
    """

    path = Path(path) / 'pipeline-content.json'

    with open(path, 'r') as f:
        content = json.load(f)

    for variable in variables:
        # Use indexes to find correct variable - Does not assume unique names
        # This allows multiple activities/subactivities with the same name
        activity_idx = variable['activity_index']
        subactivity_idx = variable['subactivity_index']

        # Substitute just the values that need to be replaced with placeholders
        # Database
        content['properties']['activities'][activity_idx]['typeProperties'][
            'activities'
        ][subactivity_idx]['typeProperties']['source']['datasetSettings'][
            'typeProperties'
        ][
            'database'
        ] = f"#{{{variable['activity_name']}_{variable['subactivity_name']}_source_database}}#"

        # Connection
        content['properties']['activities'][activity_idx]['typeProperties'][
            'activities'
        ][subactivity_idx]['typeProperties']['source']['datasetSettings'][
            'externalReferences'
        ][
            'connection'
        ] = f"#{{{variable['activity_name']}_{variable['subactivity_name']}_source_connection}}#"

        # Workspace ID
        content['properties']['activities'][activity_idx]['typeProperties'][
            'activities'
        ][subactivity_idx]['typeProperties']['sink']['datasetSettings'][
            'linkedService'
        ][
            'properties'
        ][
            'typeProperties'
        ][
            'workspaceId'
        ] = f"#{{{variable['activity_name']}_{variable['subactivity_name']}_sink_workspace_id}}#"

        # Artifact ID
        content['properties']['activities'][activity_idx]['typeProperties'][
            'activities'
        ][subactivity_idx]['typeProperties']['sink']['datasetSettings'][
            'linkedService'
        ][
            'properties'
        ][
            'typeProperties'
        ][
            'artifactId'
        ] = f"#{{{variable['activity_name']}_{variable['subactivity_name']}_sink_artifact_id}}#"

    modified_content = json.dumps(content, indent=2)

    # Save the modified content back to the file
    with open(path, 'w') as file:
        file.write(modified_content)


def _create_data_pipeline_placeholder_mapping(
    variables: List[Dict[str, str]]
) -> dict:
    """
    Creates a mapping of placeholders to their real values based on the extracted variables.
    """
    placeholder_mapping = {}

    for variable in variables:
        activity_name = variable['activity_name']
        subactivity_name = variable['subactivity_name']

        # Create a unique placeholder for each variable
        placeholder_mapping[
            f'{activity_name}_{subactivity_name}_source_database'
        ] = variable['source_database']
        placeholder_mapping[
            f'{activity_name}_{subactivity_name}_source_connection'
        ] = variable['source_connection']
        placeholder_mapping[
            f'{activity_name}_{subactivity_name}_sink_workspace_id'
        ] = variable['sink_workspace_id']
        placeholder_mapping[
            f'{activity_name}_{subactivity_name}_sink_artifact_id'
        ] = variable['sink_artifact_id']

    return placeholder_mapping


def replace_data_pipeline_placeholders_with_variables(
    path: str, variables: List
) -> None:
    """
    Replace data pipeline placeholders with their corresponding variable values.

    Args:
        path (str): The path to the data pipeline.
        variables (List[Dict[str, str]]): The list of variables to replace.
    """

    path = Path(path) / 'pipeline-content.json'

    with open(path, 'r') as f:
        content_str = f.read()

    mappings = _create_data_pipeline_placeholder_mapping(variables)

    # Substitute each placeholder with the corresponding value
    for placeholder, value in mappings.items():
        placeholder_pattern = f'#{{{placeholder}}}#'
        content_str = content_str.replace(placeholder_pattern, value)

    # Save the modified content back to the file
    with open(path, 'w') as file:
        file.write(content_str)
