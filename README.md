# Welcome to pyfabricops

[![PyPI version](https://img.shields.io/pypi/v/pyfabricops.svg)](https://pypi.org/project/pyfabricops/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python versions](https://img.shields.io/pypi/pyversions/pyfabricops.svg)](https://pypi.org/project/pyfabricops/)
[![Typing status](https://img.shields.io/badge/typing-PEP%20561-blue)](https://peps.python.org/pep-0561/)    
[![Tests](https://github.com/alisonpezzott/pyfabricops/actions/workflows/test.yml/badge.svg)](https://github.com/alisonpezzott/pyfabricops/actions/workflows/test.yml)  

> A Python wrapper library for Microsoft Fabric (and Power BI) operations, providing a simple interface to the official Fabric REST APIs. Falls back to Power BI REST APIs where needed. Designed to run in Python notebooks, pure Python scripts or integrated into YAML-based workflows for CI/CD.
Access to the repositoy on [GitHub](https://github.com/alisonpezzott/pyfabricops).

## 🚀 Features  

- Authenticate using environment variables (GitHub Secrets, ADO Secrets, .env ...)
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

#### OAuth (Interactive)

```python
pf.set_auth_provider("oauth")
```
This will open a browser window for user authentication.  

> Create a repository and clone it locally.
> Prepare your environment with the required variables according to your authentication method (GitHub Secrets, ADO Secrets, .env ...)


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


## 🪄 Examples

Visit: [https://github.com/alisonpezzott/pyfabricops-examples](https://github.com/alisonpezzott/pyfabricops-examples)


## 🧬 Project Structure  

```bash
src/
└── pyfabricops/
    ├── api/
    │   ├── __init__.py
    │   ├── api.py
    │   ├── auth.py
    │   └── scopes.py
    ├── cd/
    │   ├── __init__.py
    │   └── support_files.py
    ├── core/
    │   ├── __init__.py
    │   ├── capacities.py
    │   ├── connections.py
    │   ├── deployment_pipelines.py
    │   ├── domains.py
    │   ├── folders.py
    │   ├── gateways.py
    │   ├── gateways_encryp_creds.py
    │   ├── git.py
    │   ├── tags.py
    │   └── workspaces.py
    ├── dmv/
    │   ├── __init__.py
    │   ├── dmv.py
    ├── helpers/
    │   ├── __init__.py
    │   ├── data_pipelines.py│   
    ├── dataflows_gen1.py
    │   ├── dataflows_gen2.py
    │   ├── folders.py
    │   ├── items.py
    │   ├── lakehouses.py
    │   ├── notebooks.py
    │   ├── reports.py
    │   ├── semantic_models.py
    │   ├── warehouses.py
    │   └── workspaces.py
    ├── items/
    │   ├── __init__.py
    │   ├── data_pipelines.py
    │   ├── dataflows_gen1.py
    │   ├── dataflows_gen2.py
    │   ├── items.py
    │   ├── lakehouses.py
    │   ├── notebooks.py
    │   ├── reports.py
    │   ├── semantic_models.py
    │   ├── shortcuts.py
    │   ├── variable_libraries.py
    │   └── warehouses.py
    ├── utils/
    │   ├── __init__.py
    │   ├── decorators.py
    │   ├── exceptions.py
    │   ├── logging.py
    │   ├── schemas.py
    │   └── utils.py
    ├── __init__.py
    └── _version.py
```  

### Logging configuration  

The custom logging system implemented in `pyfabricops` provides a complete and flexible solution for monitoring and debugging the library.


#### 🎨 **Custom Formatting**
- **Automatic colors**: Different colors for each log level (DEBUG=Cyan, INFO=Green, WARNING=Yellow, ERROR=Red, CRITICAL=Magenta)
- **Multiple styles**:
  - `minimal`: Only timestamp, level and message
  - `standard`: Includes module name in compact form
  - `detailed`: Complete format with all information

#### 🎛️ **Easy Configuration**
```python
import pyfabricops as pf

# Basic configuration
pf.setup_logging(level='INFO', format_style='standard')

# Debug mode for development
pf.enable_debug_mode(include_external=False)

# Disable logging completely
pf.disable_logging()

# Reset to default configuration
pf.reset_logging()
```  

For complete logging configuration options, refer to the [logging_system.md](logging_system.md)  


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


