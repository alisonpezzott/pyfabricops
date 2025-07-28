import json
import os
import pyfabricops as pf
from pyfabricops.cicd import notebooks, reports

pf.set_auth_provider('env')
workspace = '_pyfabricops-PRD'

config = pf.get_workspace_details(workspace) 

folders = pf.get_folders_paths(workspace).to_dict(orient='records') 
config['folders'] = folders

# Extracting lakehouses
lakehouses = pf.list_lakehouses(workspace)
lakehouses_not_stg = lakehouses[~lakehouses['displayName'].str.contains('staging', case=False, na=False)]
if not lakehouses_not_stg.empty:
    if not config.get('lakehouses'):
        config['lakehouses'] = {}
    for index, row in lakehouses_not_stg.iterrows():
        config['lakehouses'][row['displayName']] = {
            'id': row['id'],
            'description': row.get('description', ''),
            'folder_id': row.get('folderId', ''),
        }

# Extracting warehouses
warehouses = pf.list_warehouses(workspace)
warehouses_not_stg = warehouses[~warehouses['displayName'].str.contains('staging', case=False, na=False)]
if not warehouses_not_stg.empty:
    if not config.get('warehouses'):
        config['warehouses'] = {}
    for index, row in warehouses_not_stg.iterrows():
        config['warehouses'][row['displayName']] = {
            'id': row['id'],
            'description': row.get('description', ''),
            'folder_id': row.get('folderId', ''),
        }

# Exclude lakehouses and warehouses from semantic models
items_to_exclude_sms = lakehouses['displayName'].to_list() + warehouses['displayName'].to_list()

# Extract Notebooks
notebooks = pf.list_notebooks(workspace)
if not notebooks.empty:
    if not config.get('notebooks'):
        config['notebooks'] = {}
    for index, row in notebooks.iterrows():
        config['notebooks'][row['displayName']] = {
            'id': row['id'],
            'description': row.get('description', ''),
            'folder_id': row.get('folderId', ''),
        }

# Extracting DataPipelines
data_pipelines = pf.list_data_pipelines(workspace)
if not data_pipelines.empty:
    if not config.get('data_pipelines'):
        config['data_pipelines'] = {}
    for index, row in data_pipelines.iterrows():
        config['data_pipelines'][row['displayName']] = {
            'id': row['id'],
            'description': row.get('description', ''),
            'folder_id': row.get('folderId', ''),
        }

# Extracting Dataflows Gen2
dataflows_gen2 = pf.list_dataflows_gen2(workspace)
if not dataflows_gen2.empty:
    if not config.get('dataflows_gen2'):
        config['dataflows_gen2'] = {}
    for index, row in dataflows_gen2.iterrows():
        config['dataflows_gen2'][row['displayName']] = {
            'id': row['id'],
            'description': row.get('description', ''),
            'folder_id': row.get('folderId', ''),
        } 

# List semantic models excluding lakehouses and warehouses
semantic_models = pf.list_semantic_models(workspace)
semantic_models = semantic_models[~semantic_models['displayName'].isin(items_to_exclude_sms)]
if not semantic_models.empty:
    if not config.get('semantic_models'):
        config['semantic_models'] = {}
    for index, row in semantic_models.iterrows():
        config['semantic_models'][row['displayName']] = {
            'id': row['id'],
        'description': row.get('description', ''),
        'folder_id': row.get('folderId', ''),
    }

# Extracting Reports
reports = pf.list_reports(workspace)
if not reports.empty:
    if not config.get('reports'):
        config['reports'] = {}
    for index, row in reports.iterrows():
        config['reports'][row['displayName']] = {
            'id': row['id'],
            'description': row.get('description', ''),
            'folder_id': row.get('folderId', ''),
        }  

# Save the configuration to a JSON file
with open('config.json', 'w') as json_file:
    json.dump(config, json_file, indent=4)
