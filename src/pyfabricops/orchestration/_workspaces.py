import inspect
from typing import Optional, Sequence

from .._data_pipelines import export_all_data_pipelines
from .._dataflows_gen1 import export_all_dataflows_gen1
from .._dataflows_gen2 import export_all_dataflows
from .._folders import export_folders
from .._lakehouses import export_all_lakehouses
from .._notebooks import export_all_notebooks
from .._reports import export_all_reports
from .._semantic_models import export_all_semantic_models
from .._warehouses import export_all_warehouses
from .._workspaces import export_workspace_config

EXPORT_FUNCS = [
    export_workspace_config,
    export_folders,
    export_all_lakehouses,
    export_all_warehouses,
    export_all_semantic_models,
    export_all_reports,
    export_all_data_pipelines,
    export_all_notebooks,
    export_all_dataflows,
    export_all_dataflows_gen1,
]


def export_full_workspace(
    workspace: str,
    project_path: str,
    workspace_path: str = 'workspace',
    update_config: bool = True,
    config_path: str = None,
    branch: str = None,
    workspace_suffix: str = None,
    branches_path: str = None,
    include: Optional[Sequence[str]] = None,
    exclude: Optional[Sequence[str]] = None,
):
    """
    Exports all items from a Fabric workspace to a local project folder.

    Args:
        workspace (str): The name of the Fabric workspace.
        project_path (str): The local path where the workspace items will be exported.
        workspace_path (str): The subfolder within the project path where the workspace items will be stored.
        update_config (bool): Whether to update the workspace configuration file.
        config_path (str): The path to the workspace configuration file.
        branch (str): The branch name to use for the export.
        workspace_suffix (str): A suffix to append to the workspace name in the export.
        branches_path (str): The path where branch-specific configurations are stored.
        include (Optional[Sequence[str]]): A list of function names to include in the export. If None, all functions are included.
        exclude (Optional[Sequence[str]]): A list of function names to exclude from the export. If None, no functions are excluded.

    Examples:
        ```python
        export_full_workspace(
            workspace='my_workspace',
            project_path='/path/to/project',
            workspace_path='workspace',
            update_config=True,
            config_path='/path/to/config',
            branch='main',
            workspace_suffix='dev',
            branches_path='/path/to/branches',
            include=['export_workspace_config', 'export_folders'],
            exclude=['export_all_dataflows']
        )
        ```
    """
    # Treat [] as None, to keep wildcard
    include = set(include) if include else None
    exclude = set(exclude) if exclude else None

    params = locals()
    for func in EXPORT_FUNCS:
        name = func.__name__
        # if include is not None and the function is not in include, skip
        if include is not None and name not in include:
            continue
        # if exclude is not None and the function is in exclude, skip
        if exclude is not None and name in exclude:
            continue

        sig = inspect.signature(func)
        kwargs = {n: params[n] for n in sig.parameters if n in params}
        func(**kwargs)
