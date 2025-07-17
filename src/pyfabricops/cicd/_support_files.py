ENV = {
    'path': '.env',
    'content': """FAB_CLIENT_ID=your_client_id_here
FAB_CLIENT_SECRET=your_client_secret_here
FAB_TENANT_ID=your_tenant_id_here
FAB_USERNAME=your_username_here
FAB_PASSWORD=your_password_here
AZURE_CLIENT_ID=your_azure_client_id_here
AZURE_CLIENT_SECRET=your_azure_client_secret_here
AZURE_TENANT_ID=your_azure_tenant_id_here
AZURE_KEY_VAULT_NAME=your_key_vault_name_here
DATABASE_USERNAME=your_database_username_here
DATABASE_PASSWORD=your_database_password_here
GH_TOKEN=your_github_token_here""",
}


BRANCHES = {
    'path': 'branches.json',
    'content': """{
    "main": "-PRD",
    "master": "-PRD",
    "dev": "-DEV",
    "staging": "-STG"
}""",
}


WORKSPACES_ROLES = {
    'path': 'workspaces_roles.json',
    'content': """[
    {
        "user_uuid": "00000000-0000-0000-0000-0000000000000",
        "user_type": "User",
        "role": "Admin"
    },
    {
        "user_uuid": "00000000-0000-0000-0000-0000000000000",
        "user_type": "Group",
        "role": "Member"
    },
    {
        "user_uuid": "00000000-0000-0000-0000-0000000000000",
        "user_type": "ServicePrincipal",
        "role": "Contributor"
    },
    {
        "user_uuid": "00000000-0000-0000-0000-0000000000000",
        "user_type": "ServicePrincipalProfile",
        "role": "Viewer"
    }
]""",
}


CONNECTIONS_ROLES = {
    'path': 'connections_roles.json',
    'content': """[
        {
            "user_uuid": "00000000-0000-0000-0000-0000000000000",
            "user_type": "User",
            "role": "Owner"
        },
        {
            "user_uuid": "00000000-0000-0000-0000-0000000000000",
            "user_type": "Group",
            "role": "User"
        },
        {
            "user_uuid": "00000000-0000-0000-0000-0000000000000",
            "user_type": "ServicePrincipal",
            "role": "UserWithReshare"
        },
        {
            "user_uuid": "00000000-0000-0000-0000-0000000000000",
            "user_type": "ServicePrincipalProfile",
            "role": "UserWithReshare"
        }
    ]""",
}


GITIGNORE = {
    'path': '.gitignore',
    'content': """**/.pbi/localSettings.json
**/.pbi/cache.abf
**/__pycache__/**
**/_stg/**
.vscode/
.venv
.env
**/py_fab.egg-info
**/dist
**/build
metadata/""",
}


GITATTRIBUTES = {
    'path': '.gitattributes',
    'content': """src/**/config.json merge=union
# This file is used to define attributes for paths in the repository.
# The 'merge=union' attribute allows for union merging of JSON files in the 'src' directory.
# This means that when merging changes, if there are conflicts, the resulting file will contain all unique elements from the conflicting files.
""",
}


ACTION_UPDATE_FROM_GIT = {
    'path': '.github/workflows/update_from_git.yml',
    'content': """name: Update from git

on:
  push:
    branches: [dev]
  pull_request:
    branches: [main]
    types: [closed]
  workflow_dispatch:
    inputs:
      branch:
        description: 'Branch to deploy'
        required: true
        default: 'dev'
        type: choice
        options:
          - main
          - dev

jobs:
  deploy:
    if: >-
      github.event_name == 'workflow_dispatch' ||
      (github.event_name == 'push' && github.ref == 'refs/heads/dev') ||
      (github.event_name == 'pull_request' && github.event.pull_request.merged == true)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event_name == 'workflow_dispatch' && github.event.inputs.branch || github.ref }}

      - name: Display deployment info
        run: |
          BRANCH=$([[ "${{ github.event_name }}" == "workflow_dispatch" ]] \
            && echo "${{ github.event.inputs.branch }}" \
            || echo "${{ github.ref_name }}")
          echo "Deploying branch: $BRANCH"
          echo "Triggered by: ${{ github.event_name }}"

      - uses: actions/setup-python@v4
        with:
          python-version: '3.12.10'

      - name: Install dependencies
        run: |
          pip install pyfabricops python-dotenv
          pip list

      - name: Run update from git
        env:
          FAB_CLIENT_ID:        ${{ secrets.FAB_CLIENT_ID }}
          FAB_CLIENT_SECRET:    ${{ secrets.FAB_CLIENT_SECRET }}
          FAB_TENANT_ID:        ${{ secrets.FAB_TENANT_ID }}
          FAB_USERNAME:         ${{ secrets.FAB_USERNAME }}
          FAB_PASSWORD:         ${{ secrets.FAB_PASSWORD }}
          AZURE_CLIENT_ID:      ${{ secrets.AZURE_CLIENT_ID }}
          AZURE_CLIENT_SECRET:  ${{ secrets.AZURE_CLIENT_SECRET }}
          AZURE_TENANT_ID:      ${{ secrets.AZURE_TENANT_ID }}
          AZURE_KEY_VAULT_NAME: ${{ secrets.AZURE_KEY_VAULT_NAME }}
          DATABASE_USERNAME:    ${{ secrets.DATABASE_USERNAME }}
          DATABASE_PASSWORD:    ${{ secrets.DATABASE_PASSWORD }}
          GH_TOKEN:             ${{ secrets.GH_TOKEN }}
        run: python scripts/update_from_git.py

      
      - name: Commit changes
        run: |
          git config --local user.name  "GitHub Actions"
          git config --local user.email "actions@github.com"
          git add .
          git commit -m "chore: update from git with GitHub Actions" || echo "No changes to commit"
      
      - name: Push changes
        run: |
          git push origin HEAD:${{ github.event_name == 'workflow_dispatch' && github.event.inputs.branch || github.ref_name }}""",
}


SRC = {
    'path': 'src/README.md',
    'content': """(# Source Directory
  This directory contains the source code for the project. 
  It is structured to facilitate development and deployment of the application.""",
}


SCRIPTS_PBI_CD_PIPELINES = {
    'path': 'scripts/_pbi_cd_pipelines.py',
    'content': '''# Import support libraries
from dotenv import load_dotenv
import json
import os
from pathlib import Path
import pyfabricops as pf
import time
from typing import Literal


def _pbi_deploy_to_workspace(
    project: str,
    mode: Literal['init_from_local', 'update_from_local', 'update_from_git'],
    *,
    workspace_alias: str = None,
    project_path: str = None,
    dataflows_gen1: list[str] = None,
):
    """
    Deploys a Power BI project using PyFabricOps.
    This script sets up the workspace, deploys folders, dataflows, semantic models, and reports.
    """
    
    # Load environment variables from .env file
    load_dotenv()


    # Set authentication provider
    pf.set_auth_provider('env') 


    # Setup logging
    pf.setup_logging(format_style='minimal')


    # Project parameters
    project = project.strip()  # Ensure no leading/trailing spaces 
    workspace_alias = workspace_alias.strip() if workspace_alias else project.strip()  # Ensure no leading/trailing spaces
    root_path = pf.get_root_path()
    project_path = project_path if project_path else Path(root_path) / project


    # Get branch and workspace information
    branch = pf.get_current_branch()
    workspace_suffix = pf.get_workspace_suffix()
    workspace_name = workspace_alias + workspace_suffix 


    # Display project details
    print('=============== PROJECT DETAILS ===============')
    print(f'Project: {project}')
    print(f'Workspace: {workspace_name}')
    print(f'Project path: {project_path}') 
    print('===============================================')


    # Retrieve workspace roles configuration
    workspace_roles_path = os.path.join(root_path, 'workspaces_roles.json')
    print(f"Workspace roles configuration path: {workspace_roles_path}")
    with open(workspace_roles_path, 'r', encoding='utf-8') as f:
        roles = json.load(f)


    # Create workspace and assign roles
    pf.create_workspace(
        workspace_name, 
        description='A Power BI Project with PyFabricOps', 
        roles=roles,
    )


    # Export workspace configuration
    pf.export_workspace_config(
        workspace_name, 
        project_path, 
        branch=branch,
        workspace_suffix=workspace_suffix,
    ) 


    # Retrienving the workspace_id from config.json in the project_path for better performance
    config_path = f'{project_path}/config.json'
    config_content = pf.read_json(config_path)
    config = config_content[branch]  
    workspace_id = config[workspace_alias]['workspace_config']['workspace_id'] 
    print(f'Workspace ID: {workspace_id}')


    # Deploy the folders first
    pf.deploy_folders(
        workspace=workspace_id, 
        project_path=project_path,
        branch=branch,
        workspace_suffix=workspace_suffix,
    )


    # Check if running in GitHub Actions or manually
    if os.environ.get('GITHUB_ACTIONS', '').lower() == 'true':
        print("Running inside GitHub Actions.")
        running_in_github_actions = True
    else:
        print("Running manually (not in GitHub Actions).")
        running_in_github_actions = False
        # Deploy the calendar dataflow gen1
        # Due a conflict with others dataflow generations and limitations with folders we need deploy it separately.
        if dataflows_gen1:
            for dataflow in dataflows_gen1:
                pf.deploy_dataflow_gen1(
                    workspace=workspace_id, 
                    path=f'{project_path}/{project}/{dataflow}',
                )


    # Export dataflow config
    # Dataflows gen1 don't have folders support on export.
    # They arrive in the root of the workspace.
    pf.export_all_dataflows_gen1(
        workspace=workspace_id,
        project_path=project_path,
        branch=branch,
        workspace_suffix=workspace_suffix,
    )


    # Extract the parameters from semantic models
    if mode == 'init_from_local':
        pf.extract_semantic_models_parameters(
            project_path,
            workspace_alias=project,
            branch=branch,
        )


    # Replace the placeholders with actual values
    elif mode in ['update_from_local', 'update_from_git']:
        pf.replace_semantic_models_placeholders_with_parameters(
            project_path,
            workspace_alias=project,
            branch=branch,
        )


    pf.deploy_all_semantic_models(
        workspace=workspace_id, 
        project_path=project_path,
        branch=branch,
        workspace_suffix=workspace_suffix,
    )

    # Time experienced during tests to deploy because of server
    time.sleep(5)

    pf.export_all_semantic_models(
        workspace_name, 
        project_path, 
        branch=branch,
        workspace_suffix=workspace_suffix,
    )


    pf.deploy_all_reports_cicd(
        project_path=project_path,
        workspace_alias=workspace_alias,
        branch=branch,
        workspace_suffix=workspace_suffix,
    )

    # Replace parameters with placeholders to commit 
    # For local editing use the function pf.replace_semantic_models_placeholders_with_parameters
    pf.replace_semantic_models_parameters_with_placeholders(
        project_path,
        workspace_alias,
        branch=branch,
    )


def pbi_init_from_local(
    project: str,
    *,
    workspace_alias: str = None,
    project_path: str = None,
    dataflows_gen1: list = None,
):
    """
    Initialize the Power BI workspace with local files.

    Args:
        project (str): The name of the project.
        workspace_alias (str, optional): The alias of the workspace.
        project_path (str, optional): The path to the project files.
        dataflows_gen1 (list, optional): A list of Gen1 dataflows to include.

    Examples:
        pbi_init_workspace(
            project="PowerBIDemo",
            workspace_alias="PowerBIDemo",
            project_path="src/PowerBIDemo",
            dataflows_gen1=["Calendar.Dataflow"],
        )
    """
    _pbi_deploy_to_workspace(
        project=project,
        workspace_alias=workspace_alias,
        mode='init_from_local',
        project_path=project_path,
        dataflows_gen1=dataflows_gen1,
    )


def pbi_update_from_local(
    project: str,
    *,
    workspace_alias: str = None,
    project_path: str = None,
    dataflows_gen1: list = None,
):
    """
    Update the Power BI workspace with local files.

    Args:
        project (str): The name of the project.
        workspace_alias (str, optional): The alias of the workspace.
        project_path (str, optional): The path to the project files.
        dataflows_gen1 (list, optional): A list of Gen1 dataflows to include.

    Examples:
        pbi_update_from_local(
            project="PowerBIDemo",
            workspace_alias="PowerBIDemo",
            project_path="src/PowerBIDemo",
            dataflows_gen1=["Calendar.Dataflow"],
        )
    """
    _pbi_deploy_to_workspace(
        project=project,
        workspace_alias=workspace_alias,
        mode='update_from_local',
        project_path=project_path,
        dataflows_gen1=dataflows_gen1,
    )


def pbi_update_from_git(
    project: str,
    *,
    workspace_alias: str = None,
    project_path: str = None,
):
    """
    Update the Power BI workspace with files from the git repository.
    Ideal to use when you want to sync changes with GitHub Actions pipelines.
    This method doesn't sync dataflows Gen1 because API limitations.

    Args:
        project (str): The name of the project.
        workspace_alias (str, optional): The alias of the workspace.
        project_path (str, optional): The path to the project files.
        dataflows_gen1 (list, optional): A list of Gen1 dataflows to include.

    Examples:
        _update_from_git(
            project="PowerBIDemo",
            workspace_alias="PowerBIDemo",
            project_path="src/PowerBIDemo",
            dataflows_gen1=["Calendar.Dataflow"],
        )
    """
    _pbi_deploy_to_workspace(
        project=project,
        workspace_alias=workspace_alias,
        mode='update_from_git',
        project_path=project_path,
    )


def pbi_sync_from_workspace(
    project: str,
    *,
    workspace_alias: str = None,
    project_path: str = None,
):
    """
    Sync a Power BI Workspace with local.
    """
    
    # Load environment variables from .env file
    load_dotenv()


    # Set authentication provider
    pf.set_auth_provider('env') 


    # Setup logging
    pf.setup_logging(format_style='minimal')


    # Project parameters
    project = project.strip()  # Ensure no leading/trailing spaces 
    workspace_alias = workspace_alias.strip() if workspace_alias else project.strip()  # Ensure no leading/trailing spaces
    root_path = pf.get_root_path()
    project_path = project_path if project_path else Path(root_path) / project


    # Get branch and workspace information
    branch = pf.get_current_branch()
    workspace_suffix = pf.get_workspace_suffix()
    workspace_name = workspace_alias + workspace_suffix 


    # Display project details
    print('=============== PROJECT DETAILS ===============')
    print(f'Project: {project}')
    print(f'Workspace: {workspace_name}')
    print(f'Project path: {project_path}') 
    print('===============================================')


    # Retrieve workspace configuration
    pf.export_workspace_config(
        workspace_name,
        project_path,
        branch=branch,
        workspace_suffix=workspace_suffix,
    )


    # Retrienving the workspace_id from config.json in the project_path for better performance
    config_path = f'{project_path}/config.json'
    config_content = pf.read_json(config_path)
    config = config_content[branch]  
    workspace_id = config[workspace_alias]['workspace_config']['workspace_id'] 
    print(f'Workspace ID: {workspace_id}')


    # Export all folders
    try:
        pf.export_folders(
            workspace=workspace_id, 
            project_path=project_path,
            workspace_path=workspace_alias,
            branch=branch,
            workspace_suffix=workspace_suffix,
        )
    except:
        pass


    # Export dataflow config
    # Dataflows gen1 don't have folders support on export.
    # They arrive in the root of the workspace.
    pf.export_all_dataflows_gen1(
        workspace=workspace_id,
        project_path=project_path,
        workspace_path=workspace_alias,
        branch=branch,
        workspace_suffix=workspace_suffix,
    )


    pf.export_all_semantic_models(
        workspace_name, 
        project_path,
        workspace_path=workspace_alias,
        branch=branch,
        workspace_suffix=workspace_suffix,
    )


    pf.export_all_reports(
        workspace_name, 
        project_path,
        workspace_path=workspace_alias,
        branch=branch,
        workspace_suffix=workspace_suffix,
    )

    # Replace parameters with placeholders to commit 
    # For local editing use the function pf.replace_semantic_models_placeholders_with_parameters
    pf.replace_semantic_models_parameters_with_placeholders(
        project_path,
        workspace_alias,
        branch=branch,
    )

    # Convert byConnection by byPath on reports definitions.pbir
    pf.convert_reports_to_local_references(
        project_path,
        branch=branch,
    )


def pbi_enable_local_edit(
        project_path: str,
        workspace_alias: str,
        *,
        branch: str = None,
        config_path: str = None, 
):
    """
    Enable local editing for Power BI semantic models.
    """
    pf.replace_semantic_models_placeholders_with_parameters(
        project_path=project_path,
        workspace_alias=workspace_alias,
        branch=branch,
        config_path=config_path,
    )
''',
}


SCRIPTS_PBI_INIT_FROM_LOCAL = {
    'path': 'scripts/pbi_init_from_local.py',
    'content': """import sys
import os

# Add root directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts._pbi_cd_pipelines import pbi_init_from_local

pbi_init_from_local(
    project='AdventureWorks',
    workspace_alias='SalesPerformance',
    project_path='src',
    dataflows_gen1=['Calendar.Dataflow'],
)""",
}


SCRIPTS_PBI_UPDATE_FROM_LOCAL = {
    'path': 'scripts/pbi_update_from_local.py',
    'content': """import sys
import os

# Add root directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts._pbi_cd_pipelines import pbi_update_from_local

pbi_update_from_local(
    project='AdventureWorks',
    workspace_alias='SalesPerformance',
    project_path='src',
    dataflows_gen1=['Calendar.Dataflow'],
)""",
}


SCRIPTS_PBI_UPDATE_FROM_GIT = {
    'path': 'scripts/pbi_update_from_git.py',
    'content': """import sys
import os

# Add root directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts._pbi_cd_pipelines import pbi_update_from_git

pbi_update_from_git(
    project='AdventureWorks',
    workspace_alias='SalesPerformance',
    project_path='src',
)
""",
}


SCRIPTS_PBI_SYNC_FROM_WORKSPACE = {
    'path': 'scripts/pbi_sync_from_workspace.py',
    'content': """import sys
import os

# Add root directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts._pbi_cd_pipelines import pbi_sync_from_workspace

pbi_sync_from_workspace(
    project='AdventureWorks',
    workspace_alias='SalesPerformance',
    project_path='src',
)
""",
}


SCRIPTS_PBI_ENABLE_LOCAL_EDIT = {
    'path': 'scripts/pbi_enable_local_edit.py',
    'content': """import sys
import os

# Add root directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts._pbi_cd_pipelines import pbi_enable_local_edit

pbi_enable_local_edit(
    project_path="src/PyFabricOps_Demo_001",
    workspace_alias="PyFabricOps_Demo_001",
)
""",
}


import os


def create_support_files():
    """
    Create support files with predefined content for PyFabricOps CI/CD operations.
    """
    files = [
        ENV,
        BRANCHES,
        WORKSPACES_ROLES,
        CONNECTIONS_ROLES,
        GITIGNORE,
        GITATTRIBUTES,
        ACTION_UPDATE_FROM_GIT,
        SRC,
        SCRIPTS_PBI_CD_PIPELINES,
        SCRIPTS_PBI_INIT_FROM_LOCAL,
        SCRIPTS_PBI_UPDATE_FROM_LOCAL,
        SCRIPTS_PBI_UPDATE_FROM_GIT,
        SCRIPTS_PBI_SYNC_FROM_WORKSPACE,
        SCRIPTS_PBI_ENABLE_LOCAL_EDIT,
    ]

    # Create directories and files
    for file_dict in files:
        path = file_dict.get('path')
        if path:
            os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(file_dict['content'])
            print(f'✓ {path}')
