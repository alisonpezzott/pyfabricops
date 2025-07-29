

def deploy_all_semantic_models(
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
    Deploy all semantic models from a project path.
    Searches recursively through all folders to find .SemanticModel directories.

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
        deploy_all_semantic_models(
            'MyProjectWorkspace',
            'path/to/project',
            workspace_path='workspace',
            config_path='config.json',
            branches_path='branches',
            branch='main',
            workspace_suffix='dev'
        )
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

    # Find all semantic model folders recursively
    semantic_model_folders = []
    for root, dirs, files in os.walk(base_path):
        for dir_name in dirs:
            if dir_name.endswith('.SemanticModel'):
                full_path = os.path.join(root, dir_name)
                # Extract just the semantic model name (without .SemanticModel suffix)
                semantic_model_name = dir_name.replace('.SemanticModel', '')
                semantic_model_folders.append(
                    {
                        'name': semantic_model_name,
                        'path': full_path,
                        'relative_path': os.path.relpath(
                            full_path, project_path
                        ).replace('\\', '/'),
                    }
                )

    for semantic_model_info in semantic_model_folders:
        deploy_semantic_model(
            workspace=workspace,
            display_name=semantic_model_info['name'],
            project_path=project_path,
            workspace_path=workspace_path,
            config_path=config_path,
            branch=branch,
            workspace_suffix=workspace_suffix,
            branches_path=branches_path,
        )

    return None


def replace_semantic_models_parameters_with_placeholders(
    project_path, workspace_alias, *, branch=None, config_path=None
):
    """
    Replace parameter values with placeholders in semantic model expressions.
    Supports both Import and Direct Lake model syntaxes.

    Args:
        project_path (str): The path to the project directory.
        workspace_alias (str): The alias of the workspace (workspace without suffix).
        branch (str, optional): The branch name. Defaults to current branch.
        config_path (str, optional): The path to the config.json file.

    Examples:
        ```python
        replace_parameters_with_placeholders(
            project_path='/path/to/project',
            workspace_alias='DemoWorkspace',
            branch='main'
        )
        ```
    """
    if not branch:
        branch = get_current_branch()

    if not config_path:
        config_path = f'{project_path}/config.json'

    # Read the config.json retrieving the parameters for the semantic model
    try:
        with open(config_path, 'r') as f:
            config_content = json.load(f)
        config = config_content[branch]
        semantic_models_config = config[workspace_alias]['semantic_models']
    except Exception as e:
        logger.error(f'Error reading config file: {e}')
        return

    # Process all semantic models
    for semantic_model_path in glob.glob(
        f'{project_path}/**/*.SemanticModel', recursive=True
    ):
        logger.info(f'Processing semantic model: {semantic_model_path}')
        semantic_model_name = (
            semantic_model_path.replace('\\', '/')
            .split('/')[-1]
            .split('.SemanticModel')[0]
        )
        logger.info(f'Injecting placeholders into: {semantic_model_name}')

        # Check if this semantic model has parameters in config
        if semantic_model_name not in semantic_models_config:
            logger.warning(
                f'No parameters found for semantic model: {semantic_model_name}'
            )
            continue

        semantic_model_config = semantic_models_config[semantic_model_name]
        if 'parameters' not in semantic_model_config:
            logger.warning(
                f'No parameters section found for semantic model: {semantic_model_name}'
            )
            continue

        semantic_model_parameters = semantic_model_config['parameters']

        # Read the current content of expressions.tmdl
        expressions_path = f'{semantic_model_path}/definition/expressions.tmdl'

        if not os.path.exists(expressions_path):
            logger.warning(f'expressions.tmdl not found: {expressions_path}')
            continue

        try:
            with open(expressions_path, 'r', encoding='utf-8') as f:
                expressions = f.read()
        except Exception as e:
            logger.error(f'Error reading expressions.tmdl: {e}')
            continue

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
                f'Updated expressions.tmdl for: {semantic_model_name} ({replacements_made} replacements)'
            )
        except Exception as e:
            logger.error(f'Error writing expressions.tmdl: {e}')


def replace_semantic_models_placeholders_with_parameters(
    project_path, workspace_alias, *, branch=None, config_path=None
):
    """
    Replace placeholders with actual parameter values in semantic model expressions.
    Supports both Import and Direct Lake model syntaxes.

    Args:
        project_path (str): The path to the project directory.
        workspace_alias (str): The alias of the workspace (workspace without suffix).
        branch (str, optional): The branch name. Defaults to current branch.
        config_path (str, optional): The path to the config.json file.

    Examples:
        ```python
        replace_semantic_models_placeholders_with_parameters(
            project_path='/path/to/project',
            workspace_alias='DemoWorkspace',
            branch='main'
        )
        ```
    """
    if not branch:
        branch = get_current_branch()

    if not config_path:
        config_path = f'{project_path}/config.json'

    # Read the config.json retrieving the parameters for the semantic model
    try:
        with open(config_path, 'r') as f:
            config_content = json.load(f)
        config = config_content[branch]
        semantic_models_config = config[workspace_alias]['semantic_models']
    except Exception as e:
        logger.error(f'Error reading config file: {e}')
        return

    # Process all semantic models
    for semantic_model_path in glob.glob(
        f'{project_path}/**/*.SemanticModel', recursive=True
    ):
        logger.info(f'Processing semantic model: {semantic_model_path}')
        semantic_model_name = (
            semantic_model_path.replace('\\', '/')
            .split('/')[-1]
            .split('.SemanticModel')[0]
        )
        logger.info(f'Deploying semantic model name: {semantic_model_name}')

        # Check if this semantic model has parameters in config
        if semantic_model_name not in semantic_models_config:
            logger.warning(
                f'No parameters found for semantic model: {semantic_model_name}'
            )
            continue

        semantic_model_config = semantic_models_config[semantic_model_name]
        if 'parameters' not in semantic_model_config:
            logger.warning(
                f'No parameters section found for semantic model: {semantic_model_name}'
            )
            continue

        semantic_model_parameters = semantic_model_config['parameters']

        # Read the current content of expressions.tmdl
        expressions_path = f'{semantic_model_path}/definition/expressions.tmdl'

        if not os.path.exists(expressions_path):
            logger.warning(f'expressions.tmdl not found: {expressions_path}')
            continue

        try:
            with open(expressions_path, 'r', encoding='utf-8') as f:
                expressions = f.read()
        except Exception as e:
            logger.error(f'Error reading expressions.tmdl: {e}')
            continue

        # Replace placeholders with actual values
        expressions_with_values = expressions
        replacements_made = 0

        for parameter_name, actual_value in semantic_model_parameters.items():
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
            pattern5 = rf"({re.escape(parameter_name)}\s*=\s*')({re.escape(placeholder)})(')"
            replacement5 = lambda m: f'{m.group(1)}{actual_value}{m.group(3)}'

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
                    f'⚠️ No matching pattern found for placeholder: {parameter_name}'
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
                f'Updated expressions.tmdl for: {semantic_model_name} ({replacements_made} replacements)'
            )
        except Exception as e:
            logger.error(f'Error writing expressions.tmdl: {e}')



