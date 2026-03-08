import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from pandas import DataFrame

from ..core.workspaces import resolve_workspace
from ..helpers.folders import resolve_folder_from_id_to_path
from ..items.warehouses import get_warehouse, list_warehouses
from ..utils.decorators import df
from ..utils.logging import get_logger
from ..utils.schemas import PLATFORM_SCHEMA, PLATFORM_VERSION

logger = get_logger(__name__)


def _save_warehouse_sqlproj(
    display_name: str,
    path: Union[Path, str],
) -> None:
    """
    Create a dummy warehouse `.sqlproj` file
    """
    WAREHOUSE_SQL_PROJECT = r"""<Project DefaultTargets="Build">
  <Sdk Name="Microsoft.Build.Sql" Version="0.1.19-preview" />
  <PropertyGroup>
    <Name>{warehouse_display_name}</Name>
    <DSP>Microsoft.Data.Tools.Schema.Sql.SqlDwUnifiedDatabaseSchemaProvider</DSP>
    <DefaultCollation>Latin1_General_100_BIN2_UTF8</DefaultCollation>
  </PropertyGroup>
  <Target Name="BeforeBuild">
    <Delete Files="$(BaseIntermediateOutputPath)\project.assets.json" />
  </Target>
</Project>"""

    sql_project = WAREHOUSE_SQL_PROJECT.format(
        warehouse_display_name=display_name
    )

    with open(Path(path) / f'{display_name}.sqlproj', 'w') as f:
        f.write(sql_project)

    logger.success(
        f'{display_name}.sqlproject has been created in {path} successfully.'
    )


def _save_warehouse_defaultsemanticmodel_txt(
    path: Union[Path, str],
) -> None:
    """
    Create a `DefaultSemanticModel.txt` in `Warehouse` path.
    """
    with open(Path(path) / 'DefaultSemanticModel.txt', 'w') as f:
        f.write('Has default semantic model')

    logger.success(
        f'DefaultSemanticModel.txt was created in {path} successfully.'
    )


def _save_warehouse_xmla_json(
    path: Union[Path, str],
) -> None:
    """
    Create a dummy `xmla.json` on `Warehouse` path.
    """
    WAREHOUSE_XMLA_JSON = {
        'name': '{{Dataset_Name}}',
        'compatibilityLevel': 1604,
        'model': {
            'name': '{{Dataset_Name}}',
            'culture': 'en-US',
            'collation': 'Latin1_General_100_BIN2_UTF8',
            'dataAccessOptions': {
                'legacyRedirects': True,
                'returnErrorValuesAsNull': True,
            },
            'defaultPowerBIDataSourceVersion': 'powerBI_V3',
            'sourceQueryCulture': 'en-US',
            'expressions': [
                {
                    'name': 'DatabaseQuery',
                    'kind': 'm',
                    'expression': 'let\n    database = {{TDS_Endpoint}}\nin\n    database\n',
                }
            ],
            'annotations': [
                {'name': '__PBI_TimeIntelligenceEnabled', 'value': '0'},
                {
                    'name': 'SourceLineageTagType',
                    'value': 'DatabaseFullyQualifiedName',
                },
            ],
        },
    }
    with open(Path(path) / 'xmla.json', 'w') as f:
        json.dump(WAREHOUSE_XMLA_JSON, f, indent=2)

    logger.success(f'xmla.json was created in {path} successfully.')


def _generate_warehouse_platform(
    display_name: str,
    description: Optional[str] = '',
) -> Dict[str, Any]:
    """
    Generate the warehouse .platform file

    Args:
        display_name (str): The warehouse display name.
        description (str): The warehouse's description.

    Returns:
        (Dict[str, Any]): The .platform dict.
    """
    return {
        '$schema': PLATFORM_SCHEMA,
        'metadata': {
            'type': 'Warehouse',
            'displayName': display_name,
            'description': description,
        },
        'config': {
            'version': PLATFORM_VERSION,
            'logicalId': '00000000-0000-0000-0000-000000000000',
        },
    }


def _save_warehouse_platform(
    platform: Dict[str, Any],
    path: str,
) -> None:
    """
    Save the warehouses's .platform in path

    Args:
        platform (Dict[str, Any]): The .platform dict.
        path (str): The warehouse directory path to save to.
    """
    with open(Path(path) / '.platform', 'w') as f:
        json.dump(platform, f, indent=2)


def get_warehouse_config(
    workspace: str, warehouse: str
) -> Union[Dict[str, Any], None]:
    """
    Get a specific warehouse config from a workspace.

    Args:
        workspace (str): The name or ID from the workspace.
        warehouse (str): The name or ID from the warehouse.

    Returns:
        (Union[Dict[str, Any], None]): The dict config from the warehouse
    """
    item = warehouse
    item_data = get_warehouse(workspace, item, df=False)

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
            'connection_string': item_data['properties']['connectionString'],
        }

        return config


def get_all_warehouses_config(workspace: str) -> Union[Dict[str, Any], None]:
    """
    Generate warehouses config from a workspace.

    Args:
        workspace (str): The name or ID from the workspace.

    Returns:
        (Union[Dict[str, Any], None]): The dict config from the warehouses of the workspace
    """
    items = list_valid_warehouses(workspace, df=False)

    if items is None:
        return None

    config = {}

    for item in items:

        item_data = get_warehouse(workspace, item['id'], df=False)

        config[item['displayName']] = {
            'id': item['id'],
            'description': item.get('description', None),
            'folder_id': ''
            if item.get('folderId') is None or pd.isna(item.get('folderId'))
            else item['folderId'],
            'connection_string': item_data['properties']['connectionString'],
        }

    return config


@df
def list_valid_warehouses(
    workspace: str,
    df: Optional[bool] = True,
) -> Union[DataFrame, List[Dict[str, Any]], None]:
    """
    Generate a list of valid warehouses from a workspace.

    Args:
        workspace (str): The name or ID from the workspace.

    Returns:
        (Union[Dict[str, Any], None]): The list of valids warehouses of the workspace
    """
    items = list_warehouses(workspace)

    if items is None:
        return None

    return items[
        ~items['displayName'].str.contains('staging', case=False, na=False)
    ].to_dict(orient='records')


def export_warehouse(
    workspace: str,
    warehouse: str,
    path: Union[str, Path],
) -> None:
    """
    Export a warehouse to path

    Args:
        workspace (str): The name or ID of the workspace.
        warehouse (str): The name or ID of the warehouse.
        path (Union[str, Path]): The path to export to.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    item = get_warehouse(workspace_id, warehouse, df=True)
    try:
        folder_path = resolve_folder_from_id_to_path(
            workspace_id, item['folderId']
        )
    except:
        logger.info(f'{item["displayName"]}.Warehouse is not inside a folder.')
        folder_path = None

    if folder_path is None:
        item_path = Path(path) / (item['displayName'] + '.Warehouse')
    else:
        item_path = (
            Path(path) / folder_path / (item['displayName'] + '.Warehouse')
        )
    os.makedirs(item_path, exist_ok=True)

    platform = _generate_warehouse_platform(
        display_name=item['displayName'],
        description=item['description'],
    )

    _save_warehouse_platform(platform, item_path)

    _save_warehouse_defaultsemanticmodel_txt(item_path)

    _save_warehouse_sqlproj(item['displayName'], item_path)

    _save_warehouse_xmla_json(item_path)

    logger.success(f'All warehouses exported to {path} successfully.')
    return None


def export_all_warehouses(workspace: str, path: Union[str, Path]) -> None:
    """
    Exports all warehouses from the workspace to path.

    Args:
        workspace (str): The ID or name of the workspace.
        path (Union[str, Path]): The path to export to.
    """
    workspace_id = resolve_workspace(workspace)
    if workspace_id is None:
        return None

    items = list_valid_warehouses(workspace_id, df=False)
    if items is None:
        return None

    for item in items:
        try:
            folder_path = resolve_folder_from_id_to_path(
                workspace_id, item['folderId']
            )
        except:
            logger.info(
                f'{item["displayName"]}.Warehouse is not inside a folder.'
            )
            folder_path = None

        if folder_path is None:
            item_path = Path(path) / (item['displayName'] + '.Warehouse')
        else:
            item_path = (
                Path(path) / folder_path / (item['displayName'] + '.Warehouse')
            )
        os.makedirs(item_path, exist_ok=True)

        platform = _generate_warehouse_platform(
            display_name=item['displayName'],
            description=item['description'],
        )

        _save_warehouse_platform(platform, item_path)

        _save_warehouse_defaultsemanticmodel_txt(item_path)

        _save_warehouse_sqlproj(item['displayName'], item_path)

        _save_warehouse_xmla_json(item_path)

    logger.success(f'All warehouses exported to {path} successfully.')
    return None
