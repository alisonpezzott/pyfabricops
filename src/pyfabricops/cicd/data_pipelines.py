def export_data_pipeline(
    workspace: str,
    data_pipeline: str,
    project_path: str,
    *,
    workspace_path: str = None,
    update_config: bool = True,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
):
    """
    Exports a data_pipeline definition to a specified folder structure.

    Args:
        workspace (str): The workspace name or ID.
        data_pipeline (str): The name of the data_pipeline to export.
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
        # Export a specific data_pipeline to the project structure with default config update
        export_data_pipeline(
            'MyProjectWorkspace',
            'SalesDataPipeline',
            './Project',
        )

        # Export a specific data_pipeline to the project structure without updating config
        export_data_pipeline(
            'MyProjectWorkspace',
            'SalesDataPipeline',
            './Project',
            workspace_path='other_workspace',
            update_config=False,
        )

        # Export a specific data_pipeline to the project structure with custom config path
        export_data_pipeline(
            'MyProjectWorkspace',
            'SalesDataPipeline',
            './Project',
            config_path='./Project/my_other_config.json'
        )
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

    data_pipeline_ = get_data_pipeline(workspace_id, data_pipeline)
    if not data_pipeline_:
        return None

    data_pipeline_id = data_pipeline_['id']
    folder_id = None
    if 'folderId' in data_pipeline_:
        folder_id = data_pipeline_['folderId']

    definition = get_data_pipeline_definition(workspace_id, data_pipeline_id)
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

        data_pipeline_id = data_pipeline_['id']
        data_pipeline_name = data_pipeline_['displayName']
        data_pipeline_descr = data_pipeline_.get('description', '')

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
            definition, f'{item_path}/{data_pipeline_name}.DataPipeline'
        )

        if 'data_pipelines' not in config:
            config['data_pipelines'] = {}
        if data_pipeline_name not in config['data_pipelines']:
            config['data_pipelines'][data_pipeline_name] = {}
        if 'id' not in config['data_pipelines'][data_pipeline_name]:
            config['data_pipelines'][data_pipeline_name][
                'id'
            ] = data_pipeline_id
        if 'description' not in config['data_pipelines'][data_pipeline_name]:
            config['data_pipelines'][data_pipeline_name][
                'description'
            ] = data_pipeline_descr

        if folder_id:
            if 'folder_id' not in config['data_pipelines'][data_pipeline_name]:
                config['data_pipelines'][data_pipeline_name][
                    'folder_id'
                ] = folder_id

        # Update the config with the data_pipeline details
        config['data_pipelines'][data_pipeline_name]['id'] = data_pipeline_id
        config['data_pipelines'][data_pipeline_name][
            'description'
        ] = data_pipeline_descr
        config['data_pipelines'][data_pipeline_name]['folder_id'] = folder_id

        # Saving the updated config back to the config file
        existing_config[branch][workspace_name_without_suffix] = config
        write_json(existing_config, config_path)

    else:
        unpack_item_definition(
            definition,
            f'{project_path}/{workspace_path}/{data_pipeline_name}.DataPipeline',
        )


def export_all_data_pipelines(
    workspace: str,
    project_path: str,
    *,
    workspace_path: str = None,
    update_config: bool = True,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
):
    """
    Exports all data_pipelines to the specified folder structure.

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
        # Export all data_pipelines to the project structure with default config update
        export_all_data_pipelines(
            workspace='MyProjectWorkspace',
            project_path='./Project',
        )

        # Export all data_pipelines to the project structure without updating config
        export_all_data_pipelines(
            workspace='MyProjectWorkspace',
            project_path='./Project',
            update_config=False
        )

        # Export all data_pipelines to the project structure with custom config path
        export_all_data_pipelines(
            workspace='MyProjectWorkspace',
            project_path='./Project',
            config_path='./Project/my_other_config.json'
        )
        ```
    """
    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    data_pipelines = list_data_pipelines(workspace_id)
    if data_pipelines:
        for data_pipeline in data_pipelines:
            export_data_pipeline(
                workspace=workspace,
                data_pipeline=data_pipeline['displayName'],
                project_path=project_path,
                workspace_path=workspace_path,
                update_config=update_config,
                config_path=config_path,
                branch=branch,
                workspace_suffix=workspace_suffix,
                branches_path=branches_path,
            )


def deploy_data_pipeline(
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
):
    """
    Deploy a data_pipeline in Fabric based on local folder structure.
    Automatically detects the folder_id based on where the data_pipeline is located locally.

    Args:
        workspace (str): The workspace name or ID.
        display_name (str): The display name of the data_pipeline.
        project_path (str): The root path of the project.
        workspace_path (str): The workspace folder name. Defaults to "workspace".
        config_path (str): The path to the config file. Defaults to "config.json".
        description (str, optional): A description for the data_pipeline.
        branch (str, optional): The branch name. Will be auto-detected if not provided.
        workspace_suffix (str, optional): The workspace suffix. Will be read from config if not provided.
        branches_path (str, optional): The path to the branches folder. Defaults to "branches".

    Returns:
        None

    Examples:
        ```python
        # Deploy a specific data_pipeline to the workspace
        deploy_data_pipeline(
            'MyProjectWorkspace',
            'SalesDataPipeline',
            './Project/workspace/SalesDataPipeline.DataPipeline'
        )

        # Deploy a specific data_pipeline to the workspace with custom config path
        deploy_data_pipeline(
            'MyProjectWorkspace',
            'SalesDataPipeline',
            './Project/workspace/SalesDataPipeline.DataPipeline',
            config_path='./Project/my_other_config.json'
        )

        # Deploy a specific data_pipeline to the workspace with custom branch and workspace suffix
        deploy_data_pipeline(
            'MyProjectWorkspace',
            'SalesDataPipeline',
            './Project/workspace/SalesDataPipeline.DataPipeline',
            branch='feature-branch',
            workspace_suffix='-feature',
            branches_path='./Project/branches'
        )
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

    # Find where the data pipeline is located locally
    data_pipeline_folder_path = None
    data_pipeline_full_path = None

    # Check if data_pipeline exists in workspace root
    root_path = f'{project_path}/{workspace_path}/{display_name}.DataPipeline'
    if os.path.exists(root_path):
        data_pipeline_folder_path = workspace_path
        data_pipeline_full_path = root_path
        logger.debug(f'Found data_pipeline in workspace root: {root_path}')
    else:
        # Search for the data_pipeline in subfolders (only once)
        base_search_path = f'{project_path}/{workspace_path}'
        logger.debug(
            f'Searching for {display_name}.DataPipeline in: {base_search_path}'
        )

        for root, dirs, files in os.walk(base_search_path):
            if f'{display_name}.DataPipeline' in dirs:
                data_pipeline_full_path = os.path.join(
                    root, f'{display_name}.DataPipeline'
                )
                data_pipeline_folder_path = os.path.relpath(
                    root, project_path
                ).replace('\\', '/')
                logger.debug(
                    f'Found DataPipeline in: {data_pipeline_full_path}'
                )
                logger.debug(
                    f'Relative folder path: {data_pipeline_folder_path}'
                )
                break

    if not data_pipeline_folder_path or not data_pipeline_full_path:
        logger.debug(
            f'DataPipeline {display_name}.DataPipeline not found in local structure'
        )
        logger.debug(f'Searched in: {project_path}/{workspace_path}')
        return None

    # Determine folder_id based on local path
    folder_id = None

    # Para data_pipelines em subpastas, precisamos mapear o caminho da pasta pai
    if data_pipeline_folder_path != workspace_path:
        # O data_pipeline está em uma subpasta, precisamos encontrar o folder_id
        # Remover o "workspace/" do início do caminho para obter apenas a estrutura de pastas
        folder_relative_path = data_pipeline_folder_path.replace(
            f'{workspace_path}/', ''
        )

        logger.debug(
            f'DataPipeline located in subfolder: {folder_relative_path}'
        )

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
        logger.debug(f'data_pipeline will be created in workspace root')

    # Create the definition
    definition = pack_item_definition(data_pipeline_full_path)

    # Check if data_pipeline already exists (check only once)
    data_pipeline_id = resolve_data_pipeline(
        workspace_id, display_name, silent=True
    )

    if data_pipeline_id:
        logger.info(
            f"DataPipeline '{display_name}' already exists, updating..."
        )
        # Update existing DataPipeline
        payload = {'definition': definition}
        if description:
            payload['description'] = description

        response = _api_request(
            endpoint=f'/workspaces/{workspace_id}/dataPipelines/{data_pipeline_id}/updateDefinition',
            method='post',
            payload=payload,
            params={'updateMetadata': True},
        )
        if response and response.error:
            logger.warning(
                f"Failed to update data_pipeline '{display_name}': {response.error}"
            )
            return None

        logger.success(f"Successfully updated DataPipeline '{display_name}'")
        return get_data_pipeline(workspace_id, data_pipeline_id)

    else:
        logger.info(f'Creating new DataPipeline: {display_name}')
        # Create new DataPipeline
        payload = {'displayName': display_name, 'definition': definition}
        if description:
            payload['description'] = description
        if folder_id:
            payload['folderId'] = folder_id

        response = _api_request(
            endpoint=f'/workspaces/{workspace_id}/dataPipelines',
            method='post',
            payload=payload,
        )
        if response and response.error:
            logger.warning(
                f"Failed to create DataPipeline '{display_name}': {response.error}"
            )
            return None

        logger.success(f"Successfully created DataPipeline '{display_name}'")
        return get_data_pipeline(workspace_id, display_name)


def deploy_all_data_pipelines(
    workspace: str,
    project_path: str,
    *,
    workspace_path: str = None,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
):
    """
    Deploy all data pipelines from a project path.
    Searches recursively through all folders to find .DataPipeline directories.

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
        # Deploy all data_pipelines to the workspace
        deploy_all_data_pipelines(
            'MyProjectWorkspace',
            './Project',
            workspace_path='workspace',
            config_path='./Project/config.json'
        )

        # Deploy all data_pipelines to the workspace with custom branch and workspace suffix
        deploy_all_data_pipelines(
            'MyProjectWorkspace',
            './Project',
            branch='feature-branch',
            workspace_suffix='-feature',
            branches_path='./Project/branches'
        )
        ```
    """
    base_path = f'{project_path}/{workspace_path}'

    if not os.path.exists(base_path):
        logger.error(f'Base path does not exist: {base_path}')
        return None

    # Find all data_pipeline folders recursively
    data_pipeline_folders = []
    for root, dirs, files in os.walk(base_path):
        for dir_name in dirs:
            if dir_name.endswith('.DataPipeline'):
                full_path = os.path.join(root, dir_name)
                # Extract just the data_pipeline name (without .DataPipeline suffix)
                data_pipeline_name = dir_name.replace('.DataPipeline', '')
                data_pipeline_folders.append(
                    {
                        'name': data_pipeline_name,
                        'path': full_path,
                        'relative_path': os.path.relpath(
                            full_path, project_path
                        ).replace('\\', '/'),
                    }
                )

    if not data_pipeline_folders:
        logger.warning(f'No data_pipeline folders found in {base_path}')
        return None

    logger.debug(
        f'Found {len(data_pipeline_folders)} data_pipelines to deploy:'
    )
    for data_pipeline in data_pipeline_folders:
        logger.debug(
            f"  - {data_pipeline['name']} at {data_pipeline['relative_path']}"
        )

    # Deploy each data_pipeline
    deployed_data_pipelines = []
    for data_pipeline_info in data_pipeline_folders:
        try:
            logger.debug(
                f"Deploying data_pipeline: {data_pipeline_info['name']}"
            )
            result = deploy_data_pipeline(
                workspace=workspace,
                display_name=data_pipeline_info['name'],
                project_path=project_path,
                workspace_path=workspace_path,
                config_path=config_path,
                branch=branch,
                workspace_suffix=workspace_suffix,
                branches_path=branches_path,
            )
            if result:
                deployed_data_pipelines.append(data_pipeline_info['name'])
                logger.debug(
                    f"Successfully deployed: {data_pipeline_info['name']}"
                )
            else:
                logger.debug(f"Failed to deploy: {data_pipeline_info['name']}")
        except Exception as e:
            logger.error(
                f"Error deploying {data_pipeline_info['name']}: {str(e)}"
            )

    logger.success(
        f'Deployment completed. Successfully deployed {len(deployed_data_pipelines)} data_pipelines.'
    )
    return deployed_data_pipelines
