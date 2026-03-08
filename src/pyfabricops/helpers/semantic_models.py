import os
import re
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

import pandas as pd
from pandas import DataFrame

from ..api.api import _base_api, api_request
from ..core.gateways import resolve_gateway
from ..core.workspaces import resolve_workspace
from ..helpers.folders import (
    create_folders_from_path_string,
    resolve_folder_from_id_to_path,
)
from ..helpers.lakehouses import list_valid_lakehouses
from ..helpers.warehouses import list_valid_warehouses
from ..items.semantic_models import (
    create_semantic_model,
    get_semantic_model,
    get_semantic_model_definition,
    list_semantic_models,
    resolve_semantic_model,
    update_semantic_model_definition,
)
from ..utils.decorators import df
from ..utils.logging import get_logger
from ..utils.utils import (
    extract_display_name_from_platform,
    extract_middle_path,
    list_paths_of_type,
    pack_item_definition,
    parse_tmdl_parameters,
    unpack_item_definition,
)

logger = get_logger(__name__)


def get_semantic_model_config(
    workspace: str, semantic_model: str
) -> Union[Dict[str, Any], None]:
    """
    Get a specific semantic model config from a workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        semantic_model (str): The name or ID of the semantic.

    Returns:
        (Union[Dict[str, Any], None]): The dict config from the semantic model
    """
    item = semantic_model
    item_data = get_semantic_model(workspace, item, df=False)

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


def get_all_semantic_models_config(
    workspace: str,
) -> Union[Dict[str, Any], None]:
    """
    Get semantic models config from a workspace.

    Args:
        workspace (str): The name or ID from the workspace.

    Returns:
        (Union[Dict[str, Any], None]): The dict config of all semantic models in the workspace
    """
    items = list_valid_semantic_models(workspace, df=False)

    if items is None:
        return None

    config = {}

    for item in items:

        item_data = get_semantic_model(workspace, item['id'], df=False)

        config[item['displayName']] = {
            'id': item['id'],
            'description': item.get('description', None),
            'folder_id': ''
            if item.get('folderId') is None or pd.isna(item.get('folderId'))
            else item['folderId'],
        }

    return config


@df
def list_valid_semantic_models(
    workspace: str,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Generate a list of valid semantic_models of the workspace.

    Args:
        workspace (str): The name or ID from the workspace.

    Returns:
        (Union[Dict[str, Any], None]): The list of valids semantic_models of the workspace
    """
    workspace_id = resolve_workspace(workspace)

    # Retrivieng the list of semantic models
    items = list_semantic_models(workspace_id)
    if items is None:
        return None

    # Creating a excluded list of Staging, Lake and Warehouses default semantic models
    exclude_list = ['staging']

    lakehouses_df = list_valid_lakehouses(workspace_id)
    if lakehouses_df is not None:
        lakehouses_list = lakehouses_df['displayName'].tolist()
        exclude_list.extend(lakehouses_list)

    warehouses_df = list_valid_warehouses(workspace_id)
    if warehouses_df is not None:
        warehouses_list = warehouses_df['displayName'].tolist()
        exclude_list.extend(warehouses_list)

    # Create regex pattern to create multiple parts
    if exclude_list:
        exclude_pattern = '|'.join(exclude_list)
        filtered_items = items[
            ~items['displayName'].str.contains(
                exclude_pattern, case=False, na=False
            )
        ]
    else:
        filtered_items = items

    return filtered_items.to_dict(orient='records')


def export_semantic_model(
    workspace: str,
    semantic_model: str,
    path: Union[str, Path],
) -> None:
    """
    Export a semantic model to path.

    Args:
        workspace (str): The name or ID of the workspace.
        semantic_model (str): The name or ID of the semantic_model.
        path (Union[str, Path]): The path to export to.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    item = get_semantic_model(workspace_id, semantic_model, df=False)
    try:
        folder_path = resolve_folder_from_id_to_path(
            workspace_id, item['folderId']
        )
    except:
        logger.info(
            f'{item["displayName"]}.SemanticModel is not inside a folder.'
        )
        folder_path = None

    if folder_path is None:
        item_path = Path(path) / (item['displayName'] + '.SemanticModel')
    else:
        item_path = (
            Path(path) / folder_path / (item['displayName'] + '.SemanticModel')
        )
    os.makedirs(item_path, exist_ok=True)

    definition = get_semantic_model_definition(workspace_id, item['id'])
    if definition is None:
        return None

    unpack_item_definition(definition, item_path)

    logger.success(
        f'`{item["displayName"]}.SemanticModel` was exported to {item_path} successfully.'
    )
    return None


def export_all_semantic_models(
    workspace: str,
    path: Union[str, Path],
) -> None:
    """
    Export a semantic model to path.

    Args:
        workspace (str): The name or ID of the workspace.
        path (Union[str, Path]): The path to export to.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    items = list_valid_semantic_models(workspace_id, df=False)
    if items is None:
        return None

    for item in items:
        try:
            folder_path = resolve_folder_from_id_to_path(
                workspace_id, item['folderId']
            )
        except:
            logger.info(
                f'{item["displayName"]}.SemanticModel is not inside a folder.'
            )
            folder_path = None

        if folder_path is None:
            item_path = Path(path) / (item['displayName'] + '.SemanticModel')
        else:
            item_path = (
                Path(path)
                / folder_path
                / (item['displayName'] + '.SemanticModel')
            )
        os.makedirs(item_path, exist_ok=True)

        definition = get_semantic_model_definition(workspace_id, item['id'])
        if definition is None:
            return None

        unpack_item_definition(definition, item_path)

    logger.success(
        f'All semantic models were exported to {path} successfully.'
    )
    return None


def extract_tmdl_parameters_from_semantic_model(
    path: Union[str, Path]
) -> Dict[str, str]:
    """
    Extract TMDL parameters from a specified semantic model in the local directory.

    Args:
        path (Union[str, Path]): The semantic model path.
    """
    expressions_path = Path(path) / 'definition' / 'expressions.tmdl'
    if not expressions_path.exists():
        return None

    parameters = parse_tmdl_parameters(expressions_path)

    if parameters is None:
        return None

    return parameters


def bind_semantic_model_to_gateway(
    workspace: str,
    semantic_model: str,
    gateway: str,
    *,
    datasource_ids: list[str] = None,
) -> None:
    """
    Binds the specified dataset from the specified workspace to the specified gateway, optionally with a given set of data source IDs. If you don't supply a specific data source ID, the dataset will be bound to the first matching data source in the gateway.

    Args:
        workspace (str): The workspace name or ID.
        semantic_model (str): The semantic model name or ID.
        gateway (str): The gateway name or ID.
        datasource_ids (list[str], optional): List of data source IDs to bind. If not provided, the first matching data source will be used.

    Returns:
        None

    Examples:
        ```python
        bind_semantic_model_to_gateway(
            workspace="AdventureWorks",
            semantic_model="SalesAnalysis",
            gateway="my_gateway",
            datasource_ids=["id1", "id2", "id3"]
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        logger.error(f'Workspace "{workspace}" not found.')
        return None

    semantic_model_id = resolve_semantic_model(workspace_id, semantic_model)
    if not semantic_model_id:
        logger.error(
            f'Semantic model "{semantic_model}" not found in workspace "{workspace}".'
        )
        return None

    gateway_id = resolve_gateway(gateway)
    if not gateway_id:
        logger.error(f'Gateway "{gateway}" not found.')
        return None

    payload = {'gatewayObjectId': gateway}
    if datasource_ids:
        payload['datasourceObjectIds'] = datasource_ids

    response = _base_api(
        endpoint=f'/groups/{workspace}/datasets/{semantic_model_id}/Default.BindToGateway',
        method='post',
        payload=payload,
        audience='powerbi',
    )

    if response.status_code == 200:
        logger.success(
            f'Successfully bound semantic model "{semantic_model}" to gateway "{gateway}".'
        )
        return None
    else:
        logger.error(
            f'Failed to bind semantic model "{semantic_model}" to gateway "{gateway}".'
        )
        return None


def refresh_semantic_model(
    workspace: str,
    semantic_model: str,
    *,
    notify_option: Literal[
        'MailOnCompletion', 'MailOnFailure', 'NoNotification'
    ] = 'NoNotification',
    apply_refresh_policy: Union[bool, None] = None,
    commit_mode: Literal['PartialBatch', 'Transactional'] = 'Transactional',
    effective_date: str = None,
    max_parallelism: int = 1,
    objects: list[dict[str, str]] = None,
    retry_count: int = 3,
    timeout: str = '00:30:00',
    type: Literal[
        'Automatic',
        'Calculate',
        'ClearValues',
        'DataOnly',
        'Defragment',
        'Full',
    ] = 'Full',
) -> None:
    """
    Refreshes the specified semantic model in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        semantic_model (str): The semantic model name or ID.
        notify_option (Literal['MailOnCompletion', 'MailOnFailure', 'NoNotification'], optional): Notification option for the refresh operation.
        apply_refresh_policy (bool, optional): Whether to apply the refresh policy.
        commit_mode (Literal['PartialBatch', 'Transactional'], optional): Commit mode for the refresh operation.
        effective_date (str, optional): Effective date for the refresh operation.
        max_parallelism (int, optional): Maximum parallelism for the refresh operation.
        objects (list[dict[str, str]], optional): List of objects to refresh.
        retry_count (int, optional): Number of retry attempts for the refresh operation.
        timeout (str, optional): Timeout duration for the refresh operation.
        type (Literal['Automatic', 'Calculate', 'ClearValues', 'DataOnly','Defragment', 'Full'], optional): Type of refresh operation.

    Returns:
        None

    Examples:
        ```python
        refresh_semantic_model(
            workspace="AdventureWorks",
            semantic_model="SalesAnalysis",
            apply_refresh_policy=False,
            commit_mode="Transactional",
            effective_date="2023-01-01",
            max_parallelism=5,
            objects=[
                {
                    "table": "FactSales",
                    "partition": "2024"
                },
                {
                    "table": "FactReturns",
                    "partition": "2024"
                }
            ],
            retry_count=3,
            timeout="00:30:00",
            type="Full"
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        logger.error(f'Workspace "{workspace}" not found.')
        return None

    semantic_model_id = resolve_semantic_model(workspace_id, semantic_model)
    if not semantic_model_id:
        logger.error(
            f'Semantic model "{semantic_model}" not found in workspace "{workspace}".'
        )
        return None

    payload = {'notifyOption': notify_option}
    if apply_refresh_policy is not None:
        payload['applyRefreshPolicy'] = apply_refresh_policy
    if commit_mode:
        payload['commitMode'] = commit_mode
    if effective_date:
        payload['effectiveDate'] = effective_date
    if max_parallelism:
        payload['maxParallelism'] = max_parallelism
    if objects:
        payload['objects'] = objects
    if retry_count:
        payload['retryCount'] = retry_count
    if timeout:
        payload['timeout'] = timeout
    if type:
        payload['type'] = type

    response = _base_api(
        endpoint=f'/groups/{workspace_id}/datasets/{semantic_model_id}/refreshes',
        method='post',
        payload=payload,
        audience='powerbi',
    )

    if response.status_code == 202:
        logger.success('Refresh accepted successfully.')
    else:
        logger.error(f'Refresh failed: {response.error}')


@df
def get_semantic_model_refreshes(
    workspace: str,
    semantic_model: str,
    *,
    top: int = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Get the list of refresh operations for a semantic model.

    Args:
        workspace (str): The workspace name or ID.
        semantic_model (str): The semantic model name or ID.
        top (int, optional): The maximum number of refresh operations to return.
        df (bool, optional): Whether to return the results as a DataFrame.

    Returns:
        Union[DataFrame, List[Dict[str, Any]], None]: The list of refresh operations or None if not found.
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        logger.error(f'Workspace "{workspace}" not found.')
        return None

    semantic_model_id = resolve_semantic_model(workspace_id, semantic_model)
    if not semantic_model_id:
        logger.error(
            f'Semantic model "{semantic_model}" not found in workspace "{workspace}".'
        )
        return None

    params = {}
    if not top is None and top >= 1:
        params = {'$top': top}

    response = api_request(
        endpoint=f'/groups/{workspace_id}/datasets/{semantic_model_id}/refreshes',
        audience='powerbi',
        support_pagination=True,
        params=params,
    )
    return response


@df
def get_semantic_model_refresh_details(
    workspace: str,
    semantic_model: str,
    refresh_id: str,
    *,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Get the details of a specific refresh operation for a semantic model.

    Args:
        workspace (str): The workspace name or ID.
        semantic_model (str): The semantic model name or ID.
        refresh_id (str): The ID of the refresh operation.
        df (bool, optional): Whether to return the results as a DataFrame.

    Returns:
        Union[DataFrame, List[Dict[str, Any]], None]: The details of the refresh operation or None if not found.
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        logger.error(f'Workspace "{workspace}" not found.')
        return None

    semantic_model_id = resolve_semantic_model(workspace_id, semantic_model)
    if not semantic_model_id:
        logger.error(
            f'Semantic model "{semantic_model}" not found in workspace "{workspace}".'
        )
        return None

    response = api_request(
        endpoint=f'/groups/{workspace_id}/datasets/{semantic_model_id}/refreshes/{refresh_id}',
        audience='powerbi',
    )
    return response


def execute_queries(
    workspace: str,
    semantic_model: str,
    query: str,
    *,
    include_nulls: bool = True,
    impersonated_user_name: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Execute DAX queries against a semantic model.

    Args:
        workspace (str): The workspace name or ID.
        semantic_model (str): The semantic model name or ID.
        query (str): The DAX query to execute.
        df (bool, optional): Whether to return the results as a DataFrame.

    Returns:
        Union[DataFrame, List[Dict[str, Any]], None]: The details of the refresh operation or None if not found.
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        logger.error(f'Workspace "{workspace}" not found.')
        return None

    semantic_model_id = resolve_semantic_model(workspace_id, semantic_model)
    if not semantic_model_id:
        logger.error(
            f'Semantic model "{semantic_model}" not found in workspace "{workspace}".'
        )
        return None

    payload = {
        'queries': [{'query': query}],
        'serializerSettings': {'includeNulls': include_nulls},
    }

    if impersonated_user_name:
        payload['impersonatedUserName'] = impersonated_user_name

    response = api_request(
        endpoint=f'/groups/{workspace_id}/datasets/{semantic_model_id}/executeQueries',
        method='POST',
        audience='powerbi',
        payload=payload,
    )
    return response


@df
def deploy_semantic_model(
    workspace: str,
    path: str,
    start_path: Optional[str] = None,
    description: Optional[str] = None,
    df: Optional[bool] = True,
) -> Union[DataFrame, Dict[str, Any], None]:
    """
    Deploy a semantic model to workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        path (str): The path to the semantic model.
        start_path (Optional[str]): The starting path for folder creation.
        description (Optional[str]): Description for the semantic model.
        df (Optional[bool]): If True, returns a DataFrame, otherwise returns a dictionary.

    Returns:
        (Union[DataFrame, Dict[str, Any], None]): The deployed semantic model or None if deployment fails.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    display_name = extract_display_name_from_platform(path)
    if display_name is None:
        return None

    semantic_model_id = resolve_semantic_model(workspace_id, display_name)

    folder_path_string = extract_middle_path(path, start_path=start_path)
    folder_id = create_folders_from_path_string(
        workspace_id, folder_path_string
    )

    item_definition = pack_item_definition(path)

    if semantic_model_id is None:
        return create_semantic_model(
            workspace_id,
            display_name=display_name,
            item_definition=item_definition,
            description=description,
            folder=folder_id,
            df=False,
        )

    else:
        return update_semantic_model_definition(
            workspace_id,
            semantic_model_id,
            item_definition=item_definition,
            df=False,
        )


def deploy_all_semantic_models(
    workspace: str,
    path: str,
    start_path: Optional[str] = None,
) -> None:
    """
    Deploy all semantic models to workspace.

    Args:
        workspace (str): The name or ID of the workspace.
        path (str): The path to the semantic models.
        start_path (Optional[str]): The starting path for folder creation.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    semantic_models_paths = list_paths_of_type(path, 'SemanticModel')

    for path_ in semantic_models_paths:

        display_name = extract_display_name_from_platform(path_)
        if display_name is None:
            return None

        semantic_model_id = resolve_semantic_model(workspace_id, display_name)

        folder_path_string = extract_middle_path(path_, start_path=start_path)
        folder_id = create_folders_from_path_string(
            workspace_id, folder_path_string
        )

        item_definition = pack_item_definition(path_)

        if semantic_model_id is None:
            create_semantic_model(
                workspace_id,
                display_name=display_name,
                item_definition=item_definition,
                folder=folder_id,
                df=False,
            )

        else:
            update_semantic_model_definition(
                workspace_id,
                semantic_model_id,
                item_definition=item_definition,
                df=False,
            )

    logger.success(
        f'All semantic models were deployed to workspace "{workspace}" successfully.'
    )
    return None


def replace_semantic_model_parameters_with_placeholders(
    path: Union[str, Path]
) -> None:
    """
    Replace parameter values with placeholders in semantic model expressions.
    Supports both Import and Direct Lake model syntaxes.

    Args:
        path (Union[str, Path]): The path to the semantic model.
    """
    # Read the current content of expressions.tmdl
    expressions_path = Path(path) / 'definition' / 'expressions.tmdl'

    if not expressions_path.exists():
        logger.warning(f'expressions.tmdl not found: {expressions_path}')
        return None

    try:
        with open(expressions_path, 'r', encoding='utf-8') as f:
            expressions = f.read()
    except Exception as e:
        logger.error(f'Error reading expressions.tmdl: {e}')
        return None

    semantic_model_parameters = extract_tmdl_parameters_from_semantic_model(
        path
    )
    if semantic_model_parameters is None:
        logger.warning(f'No parameters found in semantic model: {path}')
        return None

    # Replace the values with placeholders
    expressions_with_placeholders = expressions
    replacements_made = 0

    for parameter_name, actual_value in semantic_model_parameters.items():
        logger.debug(
            f'Processing parameter: {parameter_name} = "{actual_value}"'
        )

        # Pattern 1: Import model syntax - expression ParameterName = "Value"
        pattern1 = rf'(expression\s+{re.escape(parameter_name)}\s*=\s*")({re.escape(actual_value)})(")'
        replacement1 = (
            lambda m: f'{m.group(1)}#{{{parameter_name}}}#{m.group(3)}'
        )

        # Pattern 2: Direct Lake - Sql.Database("server", "database") - First parameter (server)
        pattern2 = (
            rf'(Sql\.Database\s*\(\s*")({re.escape(actual_value)})("\s*,)'
        )
        replacement2 = (
            lambda m: f'{m.group(1)}#{{{parameter_name}}}#{m.group(3)}'
        )

        # Pattern 3: Direct Lake - Sql.Database("server", "database") - Second parameter (database)
        pattern3 = rf'(Sql\.Database\s*\([^"]*"[^"]*"\s*,\s*")({re.escape(actual_value)})(")'
        replacement3 = (
            lambda m: f'{m.group(1)}#{{{parameter_name}}}#{m.group(3)}'
        )

        # Pattern 4: Generic parameter syntax - ParameterName = "Value" (without 'expression' keyword)
        pattern4 = rf'({re.escape(parameter_name)}\s*=\s*")({re.escape(actual_value)})(")'
        replacement4 = (
            lambda m: f'{m.group(1)}#{{{parameter_name}}}#{m.group(3)}'
        )

        # Pattern 5: Alternative syntax with single quotes
        pattern5 = rf"({re.escape(parameter_name)}\s*=\s*')({re.escape(actual_value)})(')"
        replacement5 = (
            lambda m: f'{m.group(1)}#{{{parameter_name}}}#{m.group(3)}'
        )

        # Pattern 6: Parameters starting with # (like #date, #datetime, etc.)
        pattern6 = rf'(expression\s+{re.escape(parameter_name)}\s*=\s*)({re.escape(actual_value)})'
        replacement6 = lambda m: f'{m.group(1)}#{{{parameter_name}}}#'

        # Try each pattern
        patterns = [
            (pattern1, replacement1, 'Import model (expression)'),
            (
                pattern2,
                replacement2,
                'Direct Lake (first parameter - server)',
            ),
            (
                pattern3,
                replacement3,
                'Direct Lake (second parameter - database)',
            ),
            (pattern4, replacement4, 'Generic parameter'),
            (pattern5, replacement5, 'Single quotes'),
            (
                pattern6,
                replacement6,
                'Hash functions (#date, #datetime, etc.)',
            ),
        ]

        pattern_found = False
        for pattern, replacement, description in patterns:
            if re.search(
                pattern,
                expressions_with_placeholders,
                re.IGNORECASE | re.DOTALL,
            ):
                old_content = expressions_with_placeholders
                expressions_with_placeholders = re.sub(
                    pattern,
                    replacement,
                    expressions_with_placeholders,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                if old_content != expressions_with_placeholders:
                    logger.info(
                        f'Replaced {parameter_name} using {description} pattern'
                    )
                    replacements_made += 1
                    pattern_found = True
                    break

        if not pattern_found:
            logger.warning(
                f'No matching pattern found for parameter: {parameter_name}'
            )
            logger.debug(f'Looking for value: "{actual_value}"')

            # Log a snippet around potential matches for debugging
            if actual_value in expressions_with_placeholders:
                logger.debug(
                    f'Value found in file but no pattern matched. Context:'
                )
                lines = expressions_with_placeholders.split('\n')
                for i, line in enumerate(lines):
                    if actual_value in line:
                        start = max(0, i - 2)
                        end = min(len(lines), i + 3)
                        for j in range(start, end):
                            prefix = '>>> ' if j == i else '    '
                            logger.debug(f'{prefix}{j+1}: {lines[j]}')

    # Write back the result to file
    try:
        with open(expressions_path, 'w', encoding='utf-8') as f:
            f.write(expressions_with_placeholders)
        logger.success(
            f'Updated expressions.tmdl for: {path} ({replacements_made} replacements)'
        )
    except Exception as e:
        logger.error(f'Error writing expressions.tmdl: {e}')
    return None


def replace_semantic_model_placeholders_with_parameters(
    path: Union[str, Path], parameters: Dict[str, str]
) -> None:
    """
    Replace placeholders with actual parameter values in semantic model expressions.
    Supports both Import and Direct Lake model syntaxes.

    Args:
        path (Union[str, Path]): The path to the semantic model.
        parameters (Dict[str, str]): A dictionary mapping parameter names to their values.
    """
    # Read the current content of expressions.tmdl
    expressions_path = Path(path) / 'definition' / 'expressions.tmdl'

    if not os.path.exists(expressions_path):
        logger.warning(f'expressions.tmdl not found: {expressions_path}')
        return None

    try:
        with open(expressions_path, 'r', encoding='utf-8') as f:
            expressions = f.read()
    except Exception as e:
        logger.error(f'Error reading expressions.tmdl: {e}')
        return None

    # Replace placeholders with actual values
    expressions_with_values = expressions
    replacements_made = 0

    for parameter_name, actual_value in parameters.items():
        logger.debug(
            f'Processing parameter: {parameter_name} = "{actual_value}"'
        )

        # Create placeholder pattern: #{ParameterName}#
        placeholder = f'#{{{parameter_name}}}#'

        # Pattern 1: Import model syntax - expression ParameterName = "#{ParameterName}#"
        pattern1 = rf'(expression\s+{re.escape(parameter_name)}\s*=\s*")({re.escape(placeholder)})(")'
        replacement1 = lambda m: f'{m.group(1)}{actual_value}{m.group(3)}'

        # Pattern 2: Direct Lake - Sql.Database("#{ServerEndpoint}#", ...) - First parameter
        pattern2 = (
            rf'(Sql\.Database\s*\(\s*")({re.escape(placeholder)})("\s*,)'
        )
        replacement2 = lambda m: f'{m.group(1)}{actual_value}{m.group(3)}'

        # Pattern 3: Direct Lake - Sql.Database(..., "#{DatabaseId}#") - Second parameter
        pattern3 = rf'(Sql\.Database\s*\([^"]*"[^"]*"\s*,\s*")({re.escape(placeholder)})(")'
        replacement3 = lambda m: f'{m.group(1)}{actual_value}{m.group(3)}'

        # Pattern 4: Generic parameter syntax - ParameterName = "#{ParameterName}#"
        pattern4 = rf'({re.escape(parameter_name)}\s*=\s*")({re.escape(placeholder)})(")'
        replacement4 = lambda m: f'{m.group(1)}{actual_value}{m.group(3)}'

        # Pattern 5: Alternative syntax with single quotes
        pattern5 = rf"({re.escape(parameter_name)}\s*=\s*')({re.escape(actual_value)})(')"
        replacement5 = lambda m: f'{m.group(1)}{actual_value}{m.group(3)}'

        # Pattern 6: Parameters starting with # (like #date, #datetime, etc.) - for placeholders
        pattern6 = rf'(expression\s+{re.escape(parameter_name)}\s*=\s*)({re.escape(placeholder)})'
        replacement6 = lambda m: f'{m.group(1)}{actual_value}'

        # Try each pattern
        patterns = [
            (pattern1, replacement1, 'Import model (expression)'),
            (
                pattern2,
                replacement2,
                'Direct Lake (first parameter - server)',
            ),
            (
                pattern3,
                replacement3,
                'Direct Lake (second parameter - database)',
            ),
            (pattern4, replacement4, 'Generic parameter'),
            (pattern5, replacement5, 'Single quotes'),
            (
                pattern6,
                replacement6,
                'Hash functions (#date, #datetime, etc.)',
            ),
        ]

        pattern_found = False
        for pattern, replacement, description in patterns:
            if re.search(
                pattern, expressions_with_values, re.IGNORECASE | re.DOTALL
            ):
                old_content = expressions_with_values
                expressions_with_values = re.sub(
                    pattern,
                    replacement,
                    expressions_with_values,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                if old_content != expressions_with_values:
                    logger.info(
                        f'Replaced placeholder {parameter_name} with value using {description} pattern'
                    )
                    replacements_made += 1
                    pattern_found = True
                    break

        if not pattern_found:
            logger.warning(
                f'No matching pattern found for placeholder: {parameter_name}'
            )
            logger.debug(f'Looking for placeholder: "{placeholder}"')

            # Log a snippet around potential matches for debugging
            if placeholder in expressions_with_values:
                logger.debug(
                    f'Placeholder found in file but no pattern matched. Context:'
                )
                lines = expressions_with_values.split('\n')
                for i, line in enumerate(lines):
                    if placeholder in line:
                        start = max(0, i - 2)
                        end = min(len(lines), i + 3)
                        for j in range(start, end):
                            prefix = '>>> ' if j == i else '    '
                            logger.debug(f'{prefix}{j+1}: {lines[j]}')

    # Write back the result to file
    try:
        with open(expressions_path, 'w', encoding='utf-8') as f:
            f.write(expressions_with_values)
        logger.success(
            f'Updated expressions.tmdl for: {path} ({replacements_made} replacements)'
        )
    except Exception as e:
        logger.error(f'Error writing expressions.tmdl: {e}')

    return None
