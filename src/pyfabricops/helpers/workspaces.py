from typing import Any, Dict

from ..core.workspaces import get_workspace, list_workspace_role_assignments
from ..utils.exceptions import ResourceNotFoundError


def get_workspace_config(
    workspace: str,
) -> Dict[str, Any]:
    """
    Retrieves the workspace details for a given workspace.

    Args:
        workspace (str): The ID or name of the workspace to retrieve configuration for.

    Returns:
        dict: A dictionary containing the workspace details, including workspace ID, name, description, capacity ID, region, and roles.

    Examples:
        ```python
        get_workspace_details('123e4567-e89b-12d3-a456-426614174000')
        get_workspace_details('MyProject')
        ```
    """
    # Retrieving details from the workspace
    workspace_details = get_workspace(workspace, df=False)
    if not workspace_details:
        raise ResourceNotFoundError(f'Workspace {workspace} not found.')

    workspace_name = workspace_details.get('displayName', '')
    workspace_id = workspace_details.get('id', '')
    workspace_description = workspace_details.get('description', '')
    capacity_id = workspace_details.get('capacityId', '')
    capacity_region = workspace_details.get('capacityRegion', '')

    # Retrieving workspace roles
    # Retrieve details
    roles_details = list_workspace_role_assignments(workspace_id, df=False)

    # Init a empty list
    roles = []

    # Iterate for each role details
    for role in roles_details:
        principal_type = role['principal']['type']
        role_entry = {
            'user_uuid': role['id'],
            'user_type': principal_type,
            'role': role['role'],
            'display_name': role['principal'].get('displayName', ''),
        }

        if principal_type == 'Group':
            group_details = role['principal'].get('groupDetails', {})
            role_entry['group_type'] = group_details.get('groupType', '')
            role_entry['email'] = group_details.get('email', '')
        elif principal_type == 'User':
            user_details = role['principal'].get('userDetails', {})
            role_entry['user_principal_name'] = user_details.get(
                'userPrincipalName', ''
            )
        elif principal_type == 'ServicePrincipal':
            spn_details = role['principal'].get('servicePrincipalDetails', {})
            role_entry['app_id'] = spn_details.get('aadAppId', '')

        roles.append(role_entry)

    # Create a empty dict
    workspace_config = {}

    # Populate the dict
    workspace_config['workspace_id'] = workspace_id
    workspace_config['workspace_name'] = workspace_name
    workspace_config['workspace_description'] = workspace_description
    workspace_config['capacity_id'] = capacity_id
    workspace_config['capacity_region'] = capacity_region
    workspace_config['workspace_roles'] = roles

    return workspace_config
