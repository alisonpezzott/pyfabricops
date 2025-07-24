def export_dataflow_gen2(
    workspace: str,
    dataflow: str,
    project_path: str,
    *,
    workspace_path: str = None,
    update_config: bool = True,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
) -> None:
    """
    Exports a dataflow definition to a specified folder structure.

    Args:
        workspace (str): The workspace name or ID.
        dataflow (str): The name of the dataflow to export.
        project_path (str): The root path of the project.
        workspace_path (str, optional): The path to the workspace folder. Defaults to "workspace".
        config_path (str): The path to the config file. Defaults to "config.json".
        branches_path (str): The path to the branches folder. Defaults to "branches".
        branch (str, optional): The branch name. Will be auto-detected if not provided.
        workspace_suffix (str, optional): The workspace suffix. Will be read from config if not provided.
        branches_path (str, optional): The path to the branches folder. Defaults to "branches".

    Returns:
        None

    Examples:
        ```python
        export_dataflow('MyProjectWorkspace', 'SalesDataModel', 'path/to/project')
        export_dataflow('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', 'path/to/project', branch='feature-branch')
        ```
    """
    workspace_path = _resolve_workspace_path(
        workspace=workspace,
        workspace_suffix=workspace_suffix,
        project_path=project_path,
        workspace_path=workspace_path,
    )
    workspace_id = resolve_workspace(workspace)
    workspace_name = get_workspace(workspace_id).get('displayName')
    if not workspace_id:
        return None

    dataflow_ = get_dataflow(workspace_id, dataflow)
    if not dataflow_:
        return None

    dataflow_id = dataflow_['id']
    folder_id = None
    if 'folderId' in dataflow_:
        folder_id = dataflow_['folderId']

    definition = get_dataflow_definition(workspace_id, dataflow_id)
    if not definition:
        return None

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

        dataflow_id = dataflow_['id']
        dataflow_name = dataflow_['displayName']
        dataflow_descr = dataflow_.get('description', '')

        # Find the key in the folders dict whose value matches folder_id
        if folder_id:
            folders = config['folders']
            item_path = next(
                (k for k, v in folders.items() if v == folder_id), None
            )
            item_path = os.path.join(project_path, workspace_path, item_path)
        else:
            item_path = os.path.join(project_path, workspace_path)

        unpack_item_definition(
            definition, f'{item_path}/{dataflow_name}.Dataflow'
        )

        if 'dataflows' not in config:
            config['dataflows'] = {}
        if dataflow_name not in config['dataflows']:
            config['dataflows'][dataflow_name] = {}
        if 'id' not in config['dataflows'][dataflow_name]:
            config['dataflows'][dataflow_name]['id'] = dataflow_id
        if 'description' not in config['dataflows'][dataflow_name]:
            config['dataflows'][dataflow_name]['description'] = dataflow_descr

        if folder_id:
            if 'folder_id' not in config['dataflows'][dataflow_name]:
                config['dataflows'][dataflow_name]['folder_id'] = folder_id

        # Update the config with the dataflow details
        config['dataflows'][dataflow_name]['id'] = dataflow_id
        config['dataflows'][dataflow_name]['description'] = dataflow_descr
        config['dataflows'][dataflow_name]['folder_id'] = folder_id

        # Saving the updated config back to the config file
        existing_config[branch][workspace_name_without_suffix] = config
        write_json(existing_config, config_path)

    else:
        unpack_item_definition(
            definition,
            f'{project_path}/{workspace_path}/{dataflow_name}.Dataflow',
        )


def export_all_dataflows_gen2(
    workspace: str,
    project_path: str,
    *,
    workspace_path: str = None,
    update_config: bool = True,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
) -> None:
    """
    Exports all dataflows to the specified folder structure.

    Args:
        workspace (str): The workspace name or ID.
        path (str): The root path of the project.
        config_path (str): The path to the config file. Defaults to "config.json".
        branch (str, optional): The branch name. Will be auto-detected if not provided.
        workspace_suffix (str, optional): The workspace suffix. Will be read from config if not provided.
        branches_path (str, optional): The path to the branches folder. Defaults to "branches".

    Returns:
        None

    Examples:
        ```python
        export_all_dataflows('MyProjectWorkspace', 'path/to/project')
        export_all_dataflows('MyProjectWorkspace', 'path/to/project', branch='feature-branch')
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    dataflows = list_dataflows(workspace_id)
    if dataflows:
        for dataflow in dataflows:
            export_dataflow(
                workspace=workspace,
                dataflow=dataflow['displayName'],
                project_path=project_path,
                workspace_path=workspace_path,
                update_config=update_config,
                config_path=config_path,
                branch=branch,
                workspace_suffix=workspace_suffix,
                branches_path=branches_path,
            )


def deploy_dataflow_gen2(
    workspace: str,
    display_name: str,
    project_path: str,
    *,
    workspace_path: str = None,
    config_path: str = None,
    description: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
) -> None:
    """
    Creates or updates a dataflow in Fabric based on local folder structure.
    Automatically detects the folder_id based on where the dataflow is located locally.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name of the dataflow.
        project_path (str): The root path of the project.
        workspace_path (str): The workspace folder name. Defaults to "workspace".
        config_path (str): The path to the config file. Defaults to "config.json".
        description (str, optional): A description for the dataflow.
        branch (str, optional): The branch name. Will be auto-detected if not provided.
        workspace_suffix (str, optional): The workspace suffix. Will be read from config if not provided.

    Returns:
        None

    Examples:
        ```python
        deploy_dataflow('MyProjectWorkspace', 'SalesDataModel', 'path/to/project')
        deploy_dataflow('MyProjectWorkspace', '123e4567-e89b-12d3-a456-426614174000', 'path/to/project', description='Sales data model')
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

    # Auto-detect branch and workspace suffix
    if not branch:
        branch = get_current_branch()

    if not workspace_suffix:
        workspace_suffix = get_workspace_suffix(branch, None, branches_path)

    workspace_name_without_suffix = workspace_name.split(workspace_suffix)[0]

    # Read config to get folder mappings
    if not config_path:
        config_path = os.path.join(project_path, 'config.json')

    try:
        config_file = read_json(config_path)
        config = config_file.get(branch, {}).get(
            workspace_name_without_suffix, {}
        )
        folders_mapping = config.get('folders', {})
    except:
        logger.warning(
            'No config file found. Cannot determine folder structure.'
        )
        folders_mapping = {}

    # Find where the dataflow is located locally
    dataflow_folder_path = None
    dataflow_full_path = None

    # Check if dataflow exists in workspace root
    root_path = f'{project_path}/{workspace_path}/{display_name}.dataflow'
    if os.path.exists(root_path):
        dataflow_folder_path = workspace_path
        dataflow_full_path = root_path
        logger.debug(f'Found dataflow in workspace root: {root_path}')
    else:
        # Search for the dataflow in subfolders (only once)
        base_search_path = f'{project_path}/{workspace_path}'
        logger.debug(
            f'Searching for {display_name}.dataflow in: {base_search_path}'
        )

        for root, dirs, files in os.walk(base_search_path):
            if f'{display_name}.dataflow' in dirs:
                dataflow_full_path = os.path.join(
                    root, f'{display_name}.dataflow'
                )
                dataflow_folder_path = os.path.relpath(
                    root, project_path
                ).replace('\\', '/')
                logger.debug(f'Found dataflow in: {dataflow_full_path}')
                logger.debug(f'Relative folder path: {dataflow_folder_path}')
                break

    if not dataflow_folder_path or not dataflow_full_path:
        logger.debug(
            f'dataflow {display_name}.dataflow not found in local structure'
        )
        logger.debug(f'Searched in: {project_path}/{workspace_path}')
        return None

    # Determine folder_id based on local path
    folder_id = None

    # Para dataflows em subpastas, precisamos mapear o caminho da pasta pai
    if dataflow_folder_path != workspace_path:
        # O dataflow está em uma subpasta, precisamos encontrar o folder_id
        # Remover o "workspace/" do início do caminho para obter apenas a estrutura de pastas
        folder_relative_path = dataflow_folder_path.replace(
            f'{workspace_path}/', ''
        )

        logger.debug(f'dataflow located in subfolder: {folder_relative_path}')

        # Procurar nos mapeamentos de pastas
        if folder_relative_path in folders_mapping:
            folder_id = folders_mapping[folder_relative_path]
            logger.debug(
                f'Found folder mapping: {folder_relative_path} -> {folder_id}'
            )
        else:
            logger.debug(
                f'No folder mapping found for: {folder_relative_path}'
            )
            logger.debug(
                f'Available folder mappings: {list(folders_mapping.keys())}'
            )
    else:
        logger.debug(f'dataflow will be created in workspace root')

    # Create the definition
    definition = pack_item_definition(dataflow_full_path)

    # Check if dataflow already exists (check only once)
    dataflow_id = resolve_dataflow(workspace_id, display_name, silent=True)

    if dataflow_id:
        logger.info(f"dataflow '{display_name}' already exists, updating...")
        # Update existing dataflow
        payload = {'definition': definition}
        if description:
            payload['description'] = description

        response = _api_request(
            endpoint=f'/workspaces/{workspace_id}/dataflows/{dataflow_id}/updateDefinition',
            method='post',
            payload=payload,
            params={'updateMetadata': True},
        )
        if response and response.error:
            logger.warning(
                f"Failed to update dataflow '{display_name}': {response.error}"
            )
            return None

        logger.success(f"Successfully updated dataflow '{display_name}'")
        return get_dataflow(workspace_id, dataflow_id)

    else:
        logger.info(f'Creating new dataflow: {display_name}')
        # Create new dataflow
        payload = {'displayName': display_name, 'definition': definition}
        if description:
            payload['description'] = description
        if folder_id:
            payload['folderId'] = folder_id

        response = _api_request(
            endpoint=f'/workspaces/{workspace_id}/dataflows',
            method='post',
            payload=payload,
        )
        if response and response.error:
            logger.warning(
                f"Failed to create dataflow '{display_name}': {response.error}"
            )
            return None

        logger.success(f"Successfully created dataflow '{display_name}'")
        return get_dataflow(workspace_id, display_name)


def deploy_all_dataflows_gen2(
    workspace: str,
    project_path: str,
    *,
    workspace_path: str = None,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
) -> None:
    """
    Deploy all dataflows from a project path.
    Searches recursively through all folders to find .Dataflow directories.

    Args:
        workspace (str): The workspace name or ID.
        project_path (str): The root path of the project.
        workspace_path (str): The workspace folder name. Defaults to "workspace".
        config_path (str): The path to the config file. Defaults to "config.json".
        branch (str, optional): The branch name. Will be auto-detected if not provided.
        workspace_suffix (str, optional): The workspace suffix. Will be read from config if not provided.
        branches_path (str, optional): The path to the branches folder. Defaults to "branches".

    Returns:
        None

    Examples:
        ```python
        deploy_all_dataflows('MyProjectWorkspace', 'path/to/project')
        deploy_all_dataflows('MyProjectWorkspace', 'path/to/project', branch='feature-branch')
        ```
    """
    workspace_path = _resolve_workspace_path(
        workspace=workspace,
        workspace_suffix=workspace_suffix,
        project_path=project_path,
        workspace_path=workspace_path,
    )
    base_path = f'{project_path}/{workspace_path}'

    if not os.path.exists(base_path):
        logger.error(f'Base path does not exist: {base_path}')
        return None

    # Find all dataflow folders recursively
    dataflow_folders = []
    for root, dirs, files in os.walk(base_path):
        for dir_name in dirs:
            if dir_name.endswith('.dataflow'):
                full_path = os.path.join(root, dir_name)
                # Extract just the dataflow name (without .dataflow suffix)
                dataflow_name = dir_name.replace('.dataflow', '')
                dataflow_folders.append(
                    {
                        'name': dataflow_name,
                        'path': full_path,
                        'relative_path': os.path.relpath(
                            full_path, project_path
                        ).replace('\\', '/'),
                    }
                )

    if not dataflow_folders:
        logger.warning(f'No dataflow folders found in {base_path}')
        return None

    logger.debug(f'Found {len(dataflow_folders)} dataflows to deploy:')
    for dataflow in dataflow_folders:
        logger.debug(f"  - {dataflow['name']} at {dataflow['relative_path']}")

    # Deploy each dataflow
    deployed_dataflows = []
    for dataflow_info in dataflow_folders:
        try:
            logger.debug(f"Deploying dataflow: {dataflow_info['name']}")
            result = deploy_dataflow(
                workspace=workspace,
                display_name=dataflow_info['name'],
                project_path=project_path,
                workspace_path=workspace_path,
                config_path=config_path,
                branch=branch,
                workspace_suffix=workspace_suffix,
                branches_path=branches_path,
            )
            if result:
                deployed_dataflows.append(dataflow_info['name'])
                logger.debug(f"Successfully deployed: {dataflow_info['name']}")
            else:
                logger.debug(f"Failed to deploy: {dataflow_info['name']}")
        except Exception as e:
            logger.error(f"Error deploying {dataflow_info['name']}: {str(e)}")

    logger.success(
        f'Deployment completed. Successfully deployed {len(deployed_dataflows)} dataflows.'
    )
    return deployed_dataflows
