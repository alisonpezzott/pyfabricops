import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

import pandas as pd
from pandas import DataFrame


from ..api.api import _base_api
from ..core.gateways import resolve_gateway
from ..core.workspaces import resolve_workspace
from ..helpers.folders import resolve_folder_from_id_to_path, create_folders_from_path_string
from ..helpers.lakehouses import list_valid_lakehouses
from ..helpers.warehouses import list_valid_warehouses
from ..items.semantic_models import create_semantic_model, get_semantic_model, list_semantic_models, get_semantic_model_definition, resolve_semantic_model, update_semantic_model_definition
from ..utils.decorators import df
from ..utils.logging import get_logger
from ..utils.utils import pack_item_definition, unpack_item_definition, parse_tmdl_parameters, extract_display_name_from_platform, extract_middle_path

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
    

def get_all_semantic_models_config(workspace: str) -> Union[Dict[str, Any], None]:
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
            ~items['displayName'].str.contains(exclude_pattern, case=False, na=False)
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
        f'`{item['displayName']}.SemanticModel` was exported to {item_path} successfully.'
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
        semantic_model (str): The name or ID of the semantic_model.
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
                Path(path) / folder_path / (item['displayName'] + '.SemanticModel')
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


def extract_tmdl_parameters_from_semantic_model(path: Union[str, Path]) -> Dict[str, str]:
    """
    Extract TMDL parameters from a specified semantic model in the local directory.
    
    Args:
        path (Union[str, Path]): The semantic model path.
    """
    expressions_path = Path(path) / 'definition' / 'expressions.tmdl'
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

    semantic_model_id = resolve_semantic_model(
        workspace_id, semantic_model, silent=True
    )
    if not semantic_model_id:
        logger.error(
            f'Semantic model "{semantic_model}" not found in workspace "{workspace}".'
        )
        return None

    gateway_id = resolve_gateway(gateway, silent=True)
    if not gateway_id:
        logger.error(f'Gateway "{gateway}" not found.')
        return None

    payload = {'gatewayObjectId': gateway}
    if datasource_ids:
        payload['datasourceObjectIds'] = datasource_ids

    response = _base_api(
        endpoint=f'/groups/{workspace}/datasets/{semantic_model}/Default.BindToGateway',
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
    apply_refresh_policy: bool = False,
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

    semantic_model_id = resolve_semantic_model(
        workspace_id, semantic_model, silent=True
    )
    if not semantic_model_id:
        logger.error(
            f'Semantic model "{semantic_model}" not found in workspace "{workspace}".'
        )
        return None

    payload = {'notifyOption': notify_option}
    if apply_refresh_policy:
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


def deploy_semantic_model(
        workspace: str,
        path: str,
        start_path: Optional[str] = None,
        description: Optional[str] = None,
) -> str:
    """
    Deploy a semantic model to workspace.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None
    
    display_name = extract_display_name_from_platform(path)  
    if display_name is None:
        return None
    
    semantic_model_id = resolve_semantic_model(workspace_id, display_name) 

    folder_path_string = extract_middle_path(path, start_path=start_path)
    folder_id = create_folders_from_path_string(workspace_id, folder_path_string) 

    item_definition = pack_item_definition(path)

    if semantic_model_id is None:
        return create_semantic_model(
            workspace_id,
            display_name=display_name,
            item_definition=item_definition,
            folder=folder_id,
        )

    else:
        return update_semantic_model_definition(
            workspace_id,
            semantic_model_id,
            item_definition=item_definition,
        )
