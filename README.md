# Welcome to pyfabricops

[![PyPI version](https://img.shields.io/pypi/v/pyfabricops.svg)](https://pypi.org/project/pyfabricops/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python versions](https://img.shields.io/pypi/pyversions/pyfabricops.svg)](https://pypi.org/project/pyfabricops/)
[![Typing status](https://img.shields.io/badge/typing-PEP%20561-blue)](https://peps.python.org/pep-0561/)    
[![Tests](https://github.com/alisonpezzott/pyfabricops/actions/workflows/test.yml/badge.svg)](https://github.com/alisonpezzott/pyfabricops/actions/workflows/test.yml)  

> A Python wrapper library for Microsoft Fabric (and Power BI) operations, providing a simple interface to the official Fabric REST APIs. Falls back to Power BI REST APIs where needed. Designed to run in Python notebooks, pure Python scripts or integrated into YAML-based workflows for CI/CD.
Access to the repositoy on [GitHub](https://github.com/alisonpezzott/pyfabricops).

## 🚀 Features  

- Authenticate using environment variables (GitHub Secrets, ADO Secrets, AzKeyVault, .env ...)
- Manage workspaces, capacities, semantic models, lakehouses, reports and connections
- Execute Git operations and automate Fabric deployment flows (Power BI inclusive)
- Capture and Manage Git branches automatically for CI/CD scenarios
- Many use cases and scenarios including yaml for test and deploy using GitHub Actions

## 📃 Documentation  
Access: [https://pyfabricops.readthedocs.io/en/latest/](https://pyfabricops.readthedocs.io/en/latest/) 

## ✅ Requirements  

- Requires Python >= 3.10 <=3.12.10  

## ⚒️ Installation

```bash
pip install -U pyfabricops
```

## ⚙️ Usage

> Create a repository and clone it locally.
> Create a notebook or a script and import the library:

```python
# Import the library
import pyfabricops as pf
```

### Set the authentication provider

> Set auth environment variables acording to your authentication method  
#### Environment variables (.env, GitHub Secrets, Ado Secrets...)
```python
pf.set_auth_provider("env")
```

This is the default behavior.
You can set these in a .env file or directly in your environment (GitHub Secrets, ADO Secrets...).

Example .env file:
```
FAB_CLIENT_ID=your_client_id_here
FAB_CLIENT_SECRET=your_client_secret_here
FAB_TENANT_ID=your_tenant_id_here
FAB_USERNAME=your_username_here   # Necessary for some functions with no SPN support
FAB_PASSWORD=your_password_here   # Necessary for some functions with no SPN support
```

#### Azure Key Vault

```python
pf.set_auth_provider("vault")
```
Ensure you have the required Azure Key Vault secrets set:
```
AZURE_CLIENT_ID=your_azure_client_id_here
AZURE_CLIENT_SECRET=your_azure_client_secret_here
AZURE_TENANT_ID=your_azure_tenant_id_here
AZURE_KEY_VAULT_NAME=your_key_vault_name_here
```

#### OAuth (Interactive)

```python
pf.set_auth_provider("oauth")
```
This will open a browser window for user authentication.

```

> Create a repository and clone it locally.
> Prepare your environment with the required variables according to your authentication method (GitHub Secrets, ADO Secrets, AzKeyVault, .env ...)


### Branches configuration

Create a branches.json file in the root of your repository to define your branch mappings:

```json
{
    "main": "-PRD",
    "master": "-PRD",
    "dev": "-DEV",
    "staging": "-STG"
}
```
This file maps your local branches to Fabric branches, allowing the library to automatically manage branch names for CI/CD scenarios.

### Logging configuration
This library uses the standard Python logging module. You can configure it in your script or notebook using the helper function:

```python
import logging
pf.enable_notebook_logging(level=logging.INFO)
```


## 🪄 Examples

Visit: [https://github.com/alisonpezzott/pyfabricops-examples](https://github.com/alisonpezzott/pyfabricops-examples)


## 🧬 Project Structure  

```bash
src/
└── pyfabricops/
    ├── orchestration/
    │   ├── __init__.py
    │   └── _workspaces.py
    ├── tests/
    │   ├── __init__.py
    │   └── test_basic.py
    ├── __init__.py
    ├── _auth.py
    ├── _capacities.py
    ├── _connections.py
    ├── _core.py
    ├── _data_pipelines.py
    ├── _dataflows_gen1.py
    ├── _dataflows_gen2.py
    ├── _decorators.py
    ├── _encrypt_gateway_credentials.py
    ├── _exceptions.py
    ├── _fabric_items.py
    ├── _folders.py
    ├── _gateways.py
    ├── _git.py
    ├── _helpers.py
    ├── _items.py
    ├── _lakehouses.py
    ├── _logging_config.py
    ├── _notebooks.py
    ├── _reports.py
    ├── _scopes.py
    ├── _semantic_models.py
    ├── _shortcuts_payloads.py
    ├── _shortcuts.py
    ├── _utils.py
    ├── _version.py
    ├── _warehouses.py
    └── _workspaces.py
```  

## ❤️Contributing
1. Fork this repository
2. Create a new branch (feat/my-feature)
3. Run `poetry install` to set up the development environment
4. Run `poetry run task test` to run tests
5. Submit a pull request 🚀  

## 🚀 Publishing

### For Maintainers

To publish a new version to PyPI:

1. Update the version in `pyproject.toml` and `src/pyfabricops/_version.py`
2. Commit and push changes
3. Create a new release on GitHub with a tag (e.g., `v0.1.0`)
4. The GitHub Action will automatically:
   - Run tests
   - Build the package
   - Publish to PyPI

### Testing with TestPyPI

```bash
# Configure TestPyPI
poetry config repositories.testpypi https://test.pypi.org/legacy/
poetry config pypi-token.testpypi <your-testpypi-token>

# Build and publish to TestPyPI
poetry build
poetry publish -r testpypi

# Install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ pyfabricops
```

### Prerequisites for Publishing

- Set up a PyPI account at https://pypi.org/
- Generate an API token at https://pypi.org/manage/account/token/
- Add the token as `PYPI_TOKEN` secret in GitHub repository settings  

## 🐞 Issues  
If you encounter any issues, please report them at [https://github.com/alisonpezzott/pyfabricops/issues](https://github.com/alisonpezzott/pyfabricops/issues)  

## ⚖️ License
This project is licensed under the MIT License – see the [LICENSE](LICENSE) file for details.  

## 🌟 Acknowledgements
Created and maintained by Alison Pezzott
Feedback, issues and stars are welcome 🌟

[![YouTube subscribers](https://img.shields.io/youtube/channel/subscribers/UCst_4Wi9DkGAc28uEPlHHHw?style=flat&logo=youtube&logoColor=ff0000&colorA=fff&colorB=000)](https://www.youtube.com/@alisonpezzott?sub_confirmation=1)
[![GitHub followers](https://img.shields.io/github/followers/alisonpezzott?style=flat&logo=github&logoColor=000&colorA=fff&colorB=000)](https://github.com/alisonpezzott)
[![LinkedIn](https://custom-icon-badges.demolab.com/badge/LinkedIn-0A66C2?logo=linkedin-white&logoColor=fff)](https://linkedin.com/in/alisonpezzott)
[![Discord](https://img.shields.io/badge/Discord-%235865F2.svg?&logo=discord&logoColor=white)](https://discord.gg/sJTDvWz9sM)
[![Telegram](https://img.shields.io/badge/Telegram-2CA5E0?logo=telegram&logoColor=white)](https://t.me/alisonpezzott)
[![Instagram](https://img.shields.io/badge/Instagram-%23E4405F.svg?logo=Instagram&logoColor=white)](https://instagram.com/alisonpezzott)  


