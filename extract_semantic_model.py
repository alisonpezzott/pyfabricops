from dotenv import load_dotenv

load_dotenv()

import pyfabricops as pf

pf.set_auth_provider('env')
pf.setup_logging(format_style='minimal', level='info')

# Setups
workspace = '_pyfabricops-PRD'
item_name = 'Sales'
path = 'Exported'
wpath = f'{path}/workspace'

# Resolve the workspace_id and creating initial config
workspace_id = pf.resolve_workspace(workspace)
config = pf.get_workspace_config(workspace_id)

# Get folders config
folders_config = pf.get_folders_config(workspace_id)
config['folders'] = folders_config

# Resolve the item ID
item_id = pf.resolve_semantic_model(workspace_id, item_name)

# Export item and get its config
pf.export_semantic_model(workspace_id, item_id, wpath)

item_config = pf.get_semantic_model_config(workspace_id, item_id)

config['semantic_models'] = {}
config['semantic_models'][item_name] = item_config

item_path = pf.resolve_folder_from_id_to_path(
    workspace_id,
    item_config['folder_id'],
)
item_path = f'{wpath}/{item_path}/{item_name}.SemanticModel'

# Extract TMDL parameters
tmdl_parameters = pf.extract_tmdl_parameters_from_semantic_model(item_path)
config['semantic_models'][item_name]['parameters'] = tmdl_parameters

# Write config to JSON
pf.write_json(config, f'{path}/config.json')

# Replace parameters with placeholders to commit
pf.replace_semantic_model_parameters_with_placeholders(
    item_path,
)
