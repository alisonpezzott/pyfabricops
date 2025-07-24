def get_semantic_model_id(
    workspace_id: str, 
    semantic_model_id: str, 
    *, 
    silent: bool = False
) -> str | None:
    """
    Resolves a semantic model name to its ID.

    Args:
        workspace (str): The name or ID of the workspace.
        semantic_model (str): The name or ID of the semantic model.
        silent (bool, optional): If True, suppresses warnings. Defaults to False.

    Returns:
        str: The ID of the semantic model, or None if not found.

    Examples:
        ```python
        resolve_semantic_model('MyProjectWorkspace', 'SalesDataModel')
        ```
    """
    if is_valid_uuid(semantic_model):
        return semantic_model

    workspace_id = resolve_workspace(workspace)
    if not workspace_id:
        return None

    semantic_models = list_semantic_models(workspace, df=False)
    if not semantic_models:
        return None

    for semantic_model_ in semantic_models:
        if semantic_model_['displayName'] == semantic_model:
            return semantic_model_['id']
    if not silent:
        logger.warning(f"Semantic model '{semantic_model}' not found.")
    return None