def _get_workspace_config(
    workspace: str,
    *,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
):
    """
    Retrieves the workspace configuration for a given workspace, branch, and optional suffix.

    Args:
        workspace (str): The ID or name of the workspace to retrieve configuration for.
        branch (str, optional): The branch name to use for the configuration. If not provided, the current branch is used.
        workspace_suffix (str, optional): The suffix to append to the workspace name. If not provided, it will be determined from branches.json.
        branches_path (str, optional): The path to branches.json. If not provided, it defaults to the root path.

    Returns:
        dict: A dictionary containing the workspace configuration details, including workspace ID, name, description, capacity ID, region, and roles.

    Examples:
        ```python
        get_workspace_config_flow('123e4567-e89b-12d3-a456-426614174000')
        get_workspace_config_flow('MyProject', branch='main', workspace_suffix='-PRD')
        ```
    """
    # Retrieving details from the workspace
    workspace_details = get_workspace(workspace)
    if not workspace_details:
        raise ResourceNotFoundError(f'Workspace {workspace} not found.')

    workspace_name = workspace_details.get('displayName', '')
    workspace_id = workspace_details.get('id', '')
    workspace_description = workspace_details.get('description', '')
    capacity_id = workspace_details.get('capacityId', '')
    capacity_region = workspace_details.get('capacityRegion', '')

    # Retrieving workspace roles
    # Retrieve details
    roles_details = list_workspace_roles(workspace_id)

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
    workspace_config['workspace_config'] = {}

    # Populate the dict
    workspace_config['workspace_config']['workspace_id'] = workspace_id
    workspace_config['workspace_config']['workspace_name'] = workspace_name
    workspace_config['workspace_config'][
        'workspace_description'
    ] = workspace_description
    workspace_config['workspace_config']['capacity_id'] = capacity_id
    workspace_config['workspace_config']['capacity_region'] = capacity_region
    workspace_config['workspace_config']['workspace_roles'] = roles

    if not workspace_config:
        return None

    # Get branch
    branch = get_current_branch(branch)

    # Get the workspace suffix and treating the name
    workspace_suffix = get_workspace_suffix(
        branch, workspace_suffix, branches_path
    )
    workspace_name_without_suffix = workspace_config['workspace_config'][
        'workspace_name'
    ].split(workspace_suffix)[0]

    # Build the config
    config = {}
    config[branch] = {}
    config[branch][workspace_name_without_suffix] = workspace_config

    return config


def export_workspace_config(
    workspace: str,
    project_path: str,
    *,
    config_path: str = None,
    merge_mode: Literal['update', 'replace', 'preserve'] = 'update',
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
):
    """
    Exports the workspace configuration to a JSON file, merging with existing configurations.

    Args:
        workspace (str): Workspace name or ID
        project_path (str): Path to the project directory
        merge_mode (str): How to handle existing data:
            - 'update': Update existing workspace config (default)
            - 'replace': Replace entire branch config
            - 'preserve': Only add if workspace doesn't exist
        branch (str, optional): Branch name
        workspace_suffix (str, optional): Workspace suffix
        branches_path (str, optional): Path to branches.json


    Returns:
        None: If the operation is successful, writes to the specified path.

    Examples:
        ```python
        # Export workspace configuration for a specific workspace with default configs.
        export_workspace_config('MyProject', project_path='/path/to/project')

        # Export workspace configuration for a specific workspace with custom branch and suffix.
        export_workspace_config('MyProject', project_path='/path/to/project', branch='dev', workspace_suffix='-DEV')

        # Export workspace configuration for a specific workspace with custom branches path.
        export_workspace_config('MyProject', project_path='/path/to/project', branches_path='/path/to/branches.json')
        ```
    """
    # Get the new config for this workspace
    new_config = _get_workspace_config(
        workspace,
        branch=branch,
        workspace_suffix=workspace_suffix,
        branches_path=branches_path,
    )

    if not config_path:
        config_path = os.path.join(project_path, 'config.json')

    # Create path if not exists
    if not os.path.exists(os.path.dirname(config_path)):
        os.makedirs(os.path.dirname(config_path), exist_ok=True)

    # Try to read existing config.json
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

    # Process each branch in new config
    for branch_name, workspaces in new_config.items():
        if merge_mode == 'replace':
            # Replace entire branch
            existing_config[branch_name] = workspaces
            logger.success(
                f'Replaced all workspaces in branch "{branch_name}"'
            )
        else:
            # Ensure branch exists in existing config
            if branch_name not in existing_config:
                existing_config[branch_name] = {}

            # Process each workspace
            for workspace_name, workspace_config in workspaces.items():

                workspace_name_without_suffix = workspace_name.split(
                    workspace_suffix
                )[0]

                if (
                    merge_mode == 'preserve'
                    and workspace_name_without_suffix
                    in existing_config[branch_name]
                ):
                    logger.info(
                        f'Workspace "{workspace_name}" already exists in branch "{branch_name}". Preserving existing config.'
                    )
                    continue

                # Ensure workspace exists in existing config
                if (
                    workspace_name_without_suffix
                    not in existing_config[branch_name]
                ):
                    existing_config[branch_name][
                        workspace_name_without_suffix
                    ] = {}

                # Merge workspace_config with existing data, preserving other keys like 'folders'
                if merge_mode == 'update':
                    # Update only the workspace_config, preserve other keys like 'folders'
                    existing_config[branch_name][
                        workspace_name_without_suffix
                    ]['workspace_config'] = workspace_config[
                        'workspace_config'
                    ]
                    logger.success(
                        f'Updated workspace_config for "{workspace_name}" in branch "{branch_name}"'
                    )
                else:
                    # For other modes, replace the entire workspace config
                    existing_config[branch_name][
                        workspace_name_without_suffix
                    ] = workspace_config
                    action = (
                        'Updated'
                        if workspace_name_without_suffix
                        in existing_config[branch_name]
                        else 'Added'
                    )
                    logger.info(
                        f'{action} workspace "{workspace_name}" in branch "{branch_name}"'
                    )

    # Write the updated configuration to the file
    write_json(existing_config, config_path)
    logger.success(
        f'Workspace configuration successfully written to {config_path}'
    )


def _resolve_workspace_path(
    workspace: str,
    project_path: str,
    *,
    workspace_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
) -> str | None:
    """Resolve workspace_name for export items"""
    workspace_name = get_workspace(workspace).get('displayName', '')
    if not workspace_name:
        logger.warning(f"Workspace '{workspace}' not found.")
        return None
    else:
        if not workspace_suffix:
            workspace_suffix = get_workspace_suffix(
                branch=branch,
                workspace_suffix=workspace_suffix,
                path=branches_path,
            )
        workspace_alias = workspace_name.split(workspace_suffix)[0]

    # Add the workspace path
    if not workspace_path:
        workspace_path = workspace_alias

    return workspace_path
