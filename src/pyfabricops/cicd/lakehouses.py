def export_lakehouse(
    workspace: str,
    lakehouse: str,
    project_path: str,
    *,
    workspace_path: str = None,
    update_config: bool = True,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
    workspace_items: list = None,
) -> bool:
    """
    Exports a lakehouse to the specified project path.

    Args:
        workspace (str): The workspace name or ID.
        lakehouse (str): The name or ID of the lakehouse to export.
        project_path (str): The path to the project directory.
        workspace_path (str, optional): The path to the workspace directory. Defaults to None.
        update_config (bool, optional): Whether to update the config file. Defaults to True.
        config_path (str, optional): The path to the config file. Defaults to None.
        branch (str, optional): The branch to use. Defaults to None.
        workspace_suffix (str, optional): The workspace suffix to use. Defaults to None.
        branches_path (str, optional): The path to the branches directory. Defaults to None.
        workspace_items (list, optional): A list of workspace items to improve performance.

    Returns:
        bool: True if the export was successful, otherwise False.

    Examples:
        ```python
        export_lakehouse('MyProjectWorkspace', 'SalesDataLakehouse', '/path/to/project')
        export_lakehouse('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', '/path/to/project', workspace_suffix='dev')
        ```
    """
    workspace_path = _resolve_workspace_path(
        workspace=workspace,
        workspace_suffix=workspace_suffix,
        project_path=project_path,
        workspace_path=workspace_path,
    )
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    workspace_name = get_workspace(workspace_id).get('displayName')

    lakehouse_ = get_lakehouse(workspace_id, lakehouse)
    if not lakehouse_:
        return None

    lakehouse_id = lakehouse_['id']
    folder_id = None
    if 'folderId' in lakehouse_:
        folder_id = lakehouse_['folderId']

    lakehouse_display_name = lakehouse_['displayName']
    lakehouse_description = lakehouse_['description']
    platform = {
        'metadata': {
            'type': 'Lakehouse',
            'displayName': lakehouse_display_name,
            'description': lakehouse_description,
        }
    }

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

        # Find the key in the folders dict whose value matches folder_id

        if folder_id:
            folders = config['folders']
            item_path = next(
                (k for k, v in folders.items() if v == folder_id), None
            )
            item_path = os.path.join(project_path, workspace_path, item_path)
        else:
            item_path = workspace_path

        definition_path_full = (
            f'{item_path}/{lakehouse_display_name}.Lakehouse/.platform'
        )
        write_json(platform, definition_path_full)

        lk_id = lakehouse_['id']
        lakehouse_name = lakehouse_['displayName']
        lakehouse_sql_str = lakehouse_['properties']['sqlEndpointProperties'][
            'connectionString'
        ]
        lakehouse_sql_id = lakehouse_['properties']['sqlEndpointProperties'][
            'id'
        ]

        if 'description' not in lakehouse_:
            lakehouse_descr = ''
        else:
            lakehouse_descr = lakehouse_['description']

        if 'lakehouses' not in config:
            config['lakehouses'] = {}
        if lakehouse_name not in config['lakehouses']:
            config['lakehouses'][lakehouse_name] = {}
        if 'id' not in config['lakehouses'][lakehouse_name]:
            config['lakehouses'][lakehouse_name]['id'] = lakehouse_id
        if 'description' not in config['lakehouses'][lakehouse_name]:
            config['lakehouses'][lakehouse_name][
                'description'
            ] = lakehouse_descr

        if folder_id:
            if 'folder_id' not in config['lakehouses'][lakehouse_name]:
                config['lakehouses'][lakehouse_name]['folder_id'] = folder_id

        if 'sql_endpoint_id' not in config['lakehouses'][lakehouse_name]:
            config['lakehouses'][lakehouse_name][
                'sql_endpoint_id'
            ] = lakehouse_sql_id

        if (
            'sql_endpoint_connection_string'
            not in config['lakehouses'][lakehouse_name]
        ):
            config['lakehouses'][lakehouse_name][
                'sql_endpoint_connection_string'
            ] = lakehouse_sql_str

        # Saving the updated config back to the config file
        existing_config[branch][workspace_name_without_suffix] = config
        write_json(existing_config, config_path)

    else:
        definition_path_full = f'{project_path}/{workspace_path}/{lakehouse_display_name}.Lakehouse/.platform'
        write_json(platform, definition_path_full)

    # Creating aditional fields in .platform
    with open(
        f'{item_path}/{lakehouse_display_name}.Lakehouse/.platform', 'r'
    ) as f:
        platform_content = json.load(f)

    if 'config' not in platform_content:
        platform_content['config'] = {}

        # Generate a unique ID
        logical_id = str(uuid.uuid4())

        platform_config = {
            'version': PLATFORM_VERSION,
            'logicalId': logical_id,
        }
        platform_content['config'] = platform_config

    if '$schema' not in platform_content:
        platform_content['$schema'] = ''
        platform_content['$schema'] = PLATFORM_SCHEMA

    sorted_platform = OrderedDict()
    sorted_platform['$schema'] = platform_content['$schema']
    sorted_platform['metadata'] = platform_content['metadata']
    sorted_platform['config'] = platform_content['config']

    with open(
        f'{item_path}/{lakehouse_display_name}.Lakehouse/.platform', 'w'
    ) as f:
        json.dump(sorted_platform, f, indent=2)

    # Check if lakehouse.metadata.json exists and create it if not
    metadata_path = f'{item_path}/{lakehouse_display_name}.Lakehouse/lakehouse.metadata.json'
    if not os.path.exists(metadata_path):
        with open(metadata_path, 'w') as f:
            json.dump({}, f, indent=2)

    # Check if shortcuts.metadata.json exists and create it if not
    shortcuts_path = f'{item_path}/{lakehouse_display_name}.Lakehouse/shortcuts.metadata.json'
    if not os.path.exists(shortcuts_path):
        from .shortcuts import list_shortcuts

        shortcuts_list = list_shortcuts(workspace_id, lakehouse_id)

        # Init a empty list for shortcuts
        shortcuts_list_new = []

        if shortcuts_list:
            for shortcut_dict in shortcuts_list:
                shortcut_target = shortcut_dict['target']
                shortcut_target_type = (
                    shortcut_target['type'][0].lower()
                    + shortcut_target['type'][1:]
                )
                shortcut_target_workspace_id = shortcut_target[
                    shortcut_target_type
                ]['workspaceId']
                shortcut_target_item_id = shortcut_target[
                    shortcut_target_type
                ]['itemId']

                if not workspace_items:
                    workspace_items = list_items(shortcut_target_workspace_id)
                    for item in workspace_items:
                        if item['id'] == shortcut_target_item_id:
                            shortcut_target_item_type = item['type']
                            break

            # Check if the workspace_id is equal shortcut_target_workspace_id then uuid zero
            if shortcut_target_workspace_id == workspace_id:
                shortcut_target_workspace_id = (
                    '00000000-0000-0000-0000-000000000000'
                )

            # Create item type if not exists
            if (
                'artifactType'
                not in shortcut_dict['target'][shortcut_target_type]
            ):
                shortcut_dict['target'][shortcut_target_type][
                    'artifactType'
                ] = ''
            if (
                'workspaceId'
                not in shortcut_dict['target'][shortcut_target_type]
            ):
                shortcut_dict['target'][shortcut_target_type][
                    'workspaceId'
                ] = ''

            # Update if exists
            shortcut_dict['target']['oneLake'][
                'artifactType'
            ] = shortcut_target_item_type
            shortcut_dict['target']['oneLake'][
                'workspaceId'
            ] = shortcut_target_workspace_id

            shortcuts_list_new.append(shortcut_dict)

        # Write the shortcuts to path
        with open(shortcuts_path, 'w') as f:
            json.dump(shortcuts_list_new, f, indent=2)


def export_all_lakehouses(
    workspace: str,
    project_path: str,
    *,
    workspace_path: str = None,
    update_config: bool = True,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
    excluded_starts: tuple = ('Staging',),
) -> bool:
    """
    Exports all lakehouses in the specified workspace.

    Args:
        workspace (str): The workspace name or ID.
        project_path (str): The path to the project directory.
        workspace_path (str, optional): The path to the workspace directory. Defaults to 'workspace'.
        update_config (bool, optional): Whether to update the config file. Defaults to True.
        config_path (str, optional): The path to the config file. Defaults to None.
        branch (str, optional): The branch name. Defaults to None.
        workspace_suffix (str, optional): The workspace suffix. Defaults to None.
        branches_path (str, optional): The path to the branches directory. Defaults to None.
        excluded_starts (tuple, optional): A tuple of strings to exclude from the start of lakehouse names. Defaults to ('Staging',).

    Returns:
        bool: True if all lakehouses were exported successfully, otherwise False.

    Examples:
        ```python
        export_all_lakehouses('MyProjectWorkspace', '/path/to/project')
        export_all_lakehouses('MyProjectWorkspace', '/path/to/project', workspace_path='my_workspace')
        export_all_lakehouses('MyProjectWorkspace', '/path/to/project', update_config=False)
        ```
    """
    workspace_path = _resolve_workspace_path(
        workspace=workspace,
        workspace_suffix=workspace_suffix,
        project_path=project_path,
        workspace_path=workspace_path,
    )
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    lakehouses = list_lakehouses(
        workspace_id, excluded_starts=excluded_starts, df=False
    )

    if not lakehouses:
        logger.warning(
            f"No valid lakehouses found in workspace '{workspace}'."
        )
        return None
    else:
        for lakehouse in lakehouses:
            export_lakehouse(
                workspace=workspace,
                lakehouse=lakehouse['displayName'],
                project_path=project_path,
                workspace_path=workspace_path,
                update_config=update_config,
                config_path=config_path,
                branch=branch,
                workspace_suffix=workspace_suffix,
                branches_path=branches_path,
            )
