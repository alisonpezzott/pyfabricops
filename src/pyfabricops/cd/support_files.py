from ..utils.utils import get_logger

logger = get_logger(__name__)

ENV = {
    'path': '.env',
    'content': """FAB_CLIENT_ID=your_client_id_here
FAB_CLIENT_SECRET=your_client_secret_here
FAB_TENANT_ID=your_tenant_id_here
FAB_USERNAME=your_username_here
FAB_PASSWORD=your_password_here
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
    "develop": "-DEV",
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


SRC = {
    'path': 'src/README.md',
    'content': """(# Source Directory
  This directory contains the source code for the project. 
  It is structured to facilitate development and deployment of the application.""",
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
        SRC,
    ]

    # Create directories and files
    for file_dict in files:
        path = file_dict.get('path')
        if path:
            os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(file_dict['content'])
            logger.success(f'Created {path}')
