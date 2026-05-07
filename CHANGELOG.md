# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

---

## [0.6.0] - 2026-05-06

### Added
- `set_auth_provider()` now accepts a `credential_type` keyword argument
  (`"spn"` or `"user"`) when using the `"env"` provider. Setting
  `credential_type="user"` activates the ROPC (`password`) grant flow using
  `FAB_USERNAME` and `FAB_PASSWORD`, enabling authentication in CI/CD
  environments without a Service Principal.
- `move_item()` — moves any Fabric item to a target folder using the
  `POST /workspaces/{id}/items/{id}/move` endpoint.
- `delete_empty_folders()` — recursively deletes all folders in a workspace
  that contain no items and no sub-folders. Iterates in passes (leaves
  first) until no empty folders remain.

### Fixed
- `get_folder_id()` and `resolve_folder()` now accept an optional
  `parent_folder_id` argument. Folder resolution in
  `create_folders_from_path_string()` is scoped per path segment, preventing
  items from being deployed to the wrong folder when two folders share the
  same display name under different parents.
- `deploy_folders()` had a typo (`parente_folder` instead of `parent_folder`)
  that silently skipped parent assignment for name-based parent references.
- `parse_tmdl_parameters()` now recognises numeric parameters
  (`Decimal Number` / `Whole Number`) whose values are not enclosed in
  double quotes in `expressions.tmdl`, and returns them as `int` or `float`
  instead of `str`.
- `extract_middle_path()` now normalises both `path` and `start_path` with
  `Path.as_posix()` before comparison, fixing cases where a `./workspace`
  prefix caused the folder path to resolve as `None`.
- All `deploy_*` and `deploy_all_*` helpers (`semantic_models`, `reports`,
  `notebooks`, `data_pipelines`, `dataflows_gen2`, `environments`, `items`)
  now call `move_item()` on the update path, so existing items are moved to
  the correct folder whenever the local folder structure changes.

---

## [0.5.4] - 2026-03-15

### Changed
- Optimized module imports.

---

## [0.5.3] - 2026-03-15

### Fixed
- Fixed Ruff linting issues in `utils/utils`.

---

## [0.5.2] - 2026-03-15

### Changed
- Renamed `FileNotFoundError` to `PyFabricOpsFileNotFoundError` for namespacing consistency.

---

## [0.5.1] - 2026-03-14

### Changed
- Migrated package manager from Poetry to `uv`.
- Migrated build backend from `poetry-core` to `hatchling`.
- Upgraded Python support to include 3.13+.
- Updated CI/CD workflows for `uv`.

---

## [0.4.4] - 2026-03-08

### Fixed
- Fixed export of Dataflows Gen1.

---

## [0.4.3] - 2026-03-08

Internal build.

---

## [0.4.2] - 2026-03-08

Internal build.

---

## [0.4.1] - 2026-03-08

### Changed
- Migrated from `blue` + `isort` to `ruff` for linting and formatting.
- Adopted double-quote style consistently across the codebase.
- Fixed docstring errors across 19 source files. (Closes #60)

---

## [0.3.15] - 2026-02-15

### Fixed
- Fixed logging in `convert_report_definition_to_by_connection`. (Fixes #56)
- Fixed logging in `deploy_item`. (Fixes #55)

---

## [0.3.14] - 2026-02-14

### Fixed
- Fixed `deploy_item` creating items inside folders. (Fixes #57)

---

## [0.3.13] - 2026-02-08

### Added
- Added `create_azure_devops_connection_with_service_principal` function.

### Fixed
- Fixed `ado_connect` — added required `connection_id` parameter.
- Fixed `resolve_folder` parameter order in `create_report` and `create_variable_library`.

---

## [0.3.12] - 2026-02-08

### Fixed
- Fixed payload key in `assign_domain_workspaces_by_ids` and `unassign_domain_workspaces_by_ids` (`workspacesIds`).

---

## [0.3.11] - 2026-02-07

### Added
- Added graph methods to retrieve `object_id` from user emails, security groups and service principals. (#49)
- Added `create_adlsgen2_connection_with_service_principal_credentials` function. (#48)

### Fixed
- Fixed `deploy_item` to use `POST` method. (#50)

---

## [0.3.10] - 2026-02-01

### Changed
- Improved logging verbosity: long-running operations, environment libraries and utils now log at `DEBUG` level.

---

## [0.3.9] - 2026-02-01

### Fixed
- Fixed `VariableLibraries` API endpoint path in `get_variable_library` and `create_variable_library`.

---

## [0.3.8] - 2026-02-01

### Fixed
- Fixed `publish_environment` to return the API response directly.

---

## [0.3.7] - 2026-02-01

### Added
- Added `delete_path` utility function.

---

## [0.3.6] - 2026-02-01

Internal build.

---

## [0.3.5] - 2026-02-01

Internal build.

---

## [0.3.4] - 2026-02-01

### Changed
- Improved auth module and environments helper; updated public exports in `__init__.py`.

---

## [0.3.3] - 2026-01-31

### Changed
- Extended Python version support to 3.13.
- Updated project description.

---

## [0.3.2] - 2026-01-31

### Fixed
- Fixed environments dependencies hotfix.

---

## [0.3.1] - 2026-01-31

### Added
- PyFabricOps now runs inside Microsoft Fabric Notebooks. (Fixes #16)
- Added 27 new functions for **Environments** and **Spark Pools** management:
  - Primitives: `create_environment`, `delete_environment`, `get_environment`, `get_environment_definition`, `get_environment_id`, `get_environment_spark_compute`, `list_environments`, `publish_environment`, `resolve_environment`, `update_environment`, `update_environment_definition`, `update_environment_spark_compute`.
  - Helpers: `deploy_all_environments`, `deploy_environment`, `export_all_environments`, `export_environment`, `get_all_environments_config`, `get_environment_config`.
  - Spark Pools: `create_workspace_custom_pool`, `delete_workspace_custom_pool`, `get_workspace_custom_pool`, `get_workspace_custom_pool_id`, `get_workspace_spark_settings`, `list_workspace_custom_pools`, `resolve_workspace_custom_pool`, `update_workspace_custom_pool`, `update_workspace_spark_settings`.

---

## [0.2.11] - 2026-01-30

### Removed
- Removed Azure Key Vault authentication provider (`vault`) and `VaultCredentialProvider` class.
- Removed `azure-keyvault-secrets` dependency.

---

## [0.2.10] - 2026-01-30

### Added
- Added documentation pages for Variable Libraries, Domains, Tags and Deployment Pipelines.

---

## [0.2.9] - 2026-01-29

Internal build.

---

## [0.2.8] - 2026-01-24

### Added
- Added Variable Libraries item support (`variable_libraries`).

### Fixed
- Fixed `export_item` when item is outside a folder.
- Fixed `export_all_items` to exclude unsupported `SQLEndpoint` type.
- Fixed `convert_report_definition_to_by_path` with semantic model names containing spaces. (Fixes #27)
- Fixed `export_all_semantic_models`. (Fixes #28)

---

## [0.2.7] - 2025-10-20

Internal build.

---

## [0.2.6] - 2025-10-20

Internal build.

---

## [0.2.5] - 2025-10-18

Internal build.

---

## [0.2.4] - 2025-09-05

Internal build.

---

## [0.2.3] - 2025-09-03

### Added
- Added DMV (Data Model Viewer) support with 9 new functions: `get_semantic_model_refreshes`, `get_semantic_model_refresh_details`, `execute_queries`, `set_dmv_connection_string_spn`, `set_dmv_connection_string_user`, `evaluate_dmv_queries`, `dmv_fetch_tables_raw`, `dmv_fetch_partitions_raw`, `dmv_fetch_partitions_enriched`.

---

## [0.2.2] - 2025-08-28

Internal build.

---

## [0.2.1] - 2025-08-27

### Fixed
- Fixed cryptography compatibility in Microsoft Fabric: implemented lazy loading for gateway credential encryption functions to avoid `_get_backend` ImportError.

---

## [0.2.0] - 2025-08-27

### Added
- Added `get_available_auth_providers()` function to diagnose which authentication providers are available in the current environment.
- Added `auto` authentication provider that automatically detects and uses available credentials.
- Added `AutoCredentialProvider` class.

### Changed
- Implemented lazy loading for Azure KeyVault to resolve Microsoft Fabric compatibility issues with `azure-core`.

### Fixed
- Resolved `ImportError: AccessTokenInfo from azure.core.credentials` in Microsoft Fabric environments.

---

## [0.1.29] - 2025-08-19

### Fixed
- Fixed `refresh_semantic_model` function. (#15)

---

## [0.1.28] - 2025-08-02

### Changed
- Code linting and style cleanup.

---

## [0.1.27] - 2025-08-01

Internal build.

---

## [0.1.26] - 2025-08-01

Internal build.

---

## [0.1.25] - 2025-07-31

### Fixed
- Fixed semantic model parameters starting with `#` not being supported.
- Fixed invalid docstrings.

---

## [0.1.24] - 2025-07-31

Internal build.

---

## [0.1.23] - 2025-07-19

Internal build.

---

## [0.1.22] - 2025-07-19

### Fixed
- Fixed notebooks export: corrected extension casing `.notebooks` → `.Notebooks`.

---

## [0.1.21] - 2025-07-19

### Fixed
- Fixed data pipelines export: corrected extension path handling.

---

## [0.1.20] - 2025-07-19

Internal build.

---

## [0.1.19] - 2025-07-17

Internal build.

---

## [0.1.18] - 2025-07-17

Internal build.

---

## [0.1.17] - 2025-07-17

Internal build.

---

## [0.1.16] - 2025-07-16

### Changed
- Logging system improvements.

---

## [0.1.15] - 2025-07-16

### Added
- New logging icons.
- Script to install the library locally.

### Changed
- Added success flag to logging system.

### Fixed
- Fixed deployment of reports and semantic models to support multiple target workspaces.

---

## [0.1.14] - 2025-07-15

Internal build.

---

## [0.1.13] - 2025-07-15

### Fixed
- Hotfix: critical error in `find_project_root_path`.

---

## [0.1.12] - 2025-07-15

### Added
- New custom logging system.

### Changed
- Modular authentication control improvements.
- Increased core API performance.
- Changed export parameters approach across data pipelines, dataflows, notebooks, reports, semantic models and warehouses.

---

## [0.1.11] - 2025-07-12

### Fixed
- Fixed `deploy_dataflow_gen1` `nameConflict` parameter handling.

### Changed
- Updated project structure documentation in README.

---

## [0.1.10] - 2025-07-12

Internal build.

---

## [0.1.9] - 2025-07-12

### Fixed
- Fixed `add_workspace_role_assignment` with bulk operations.
- Fixed lakehouses and warehouses sort by platform.

---

## [0.1.8] - 2025-07-11

### Changed
- Exposed maintenance scripts.

---

## [0.1.7] - 2025-07-11

### Added
- Added `json_to_df` utility function.
- Added scopes platform support.

### Fixed
- Fixed export lakehouse to support shortcuts.

---

## [0.1.6] - 2025-07-11

### Fixed
- Fixed shortcut bugs.

---

## [0.1.5] - 2025-07-10

### Added
- Added Shortcuts support.

---

## [0.1.4] - 2025-07-09

### Added
- Added orchestration module.

### Fixed
- Fixed git and folders handling.
- Fixed dataflows gen1 JSON behavior.

---

## [0.1.3] - 2025-07-08

### Fixed
- Fixed `export_semantic_models` `update_config` parameter default value.

---

## [0.1.2] - 2025-07-08

### Fixed
- Fixed `export_semantic_models`.

---

## [0.1.1] - 2025-07-08

### Changed
- Added documentation link to README.

---

## [0.1.0] - 2025-07-08

### Added
- Initial release.

[Unreleased]: https://github.com/alisonpezzott/pyfabricops/compare/v0.5.4...HEAD
[0.5.4]: https://github.com/alisonpezzott/pyfabricops/compare/v0.5.3...v0.5.4
[0.5.3]: https://github.com/alisonpezzott/pyfabricops/compare/v0.5.2...v0.5.3
[0.5.2]: https://github.com/alisonpezzott/pyfabricops/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/alisonpezzott/pyfabricops/compare/v0.4.4...v0.5.1
[0.4.4]: https://github.com/alisonpezzott/pyfabricops/compare/v0.4.3...v0.4.4
[0.4.3]: https://github.com/alisonpezzott/pyfabricops/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/alisonpezzott/pyfabricops/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/alisonpezzott/pyfabricops/compare/v0.3.15...v0.4.1
[0.3.15]: https://github.com/alisonpezzott/pyfabricops/compare/v0.3.14...v0.3.15
[0.3.14]: https://github.com/alisonpezzott/pyfabricops/compare/v0.3.13...v0.3.14
[0.3.13]: https://github.com/alisonpezzott/pyfabricops/compare/v0.3.12...v0.3.13
[0.3.12]: https://github.com/alisonpezzott/pyfabricops/compare/v0.3.11...v0.3.12
[0.3.11]: https://github.com/alisonpezzott/pyfabricops/compare/v0.3.10...v0.3.11
[0.3.10]: https://github.com/alisonpezzott/pyfabricops/compare/v0.3.9...v0.3.10
[0.3.9]: https://github.com/alisonpezzott/pyfabricops/compare/v0.3.8...v0.3.9
[0.3.8]: https://github.com/alisonpezzott/pyfabricops/compare/v0.3.7...v0.3.8
[0.3.7]: https://github.com/alisonpezzott/pyfabricops/compare/v0.3.6...v0.3.7
[0.3.6]: https://github.com/alisonpezzott/pyfabricops/compare/v0.3.5...v0.3.6
[0.3.5]: https://github.com/alisonpezzott/pyfabricops/compare/v0.3.4...v0.3.5
[0.3.4]: https://github.com/alisonpezzott/pyfabricops/compare/v0.3.3...v0.3.4
[0.3.3]: https://github.com/alisonpezzott/pyfabricops/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/alisonpezzott/pyfabricops/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/alisonpezzott/pyfabricops/compare/v0.2.11...v0.3.1
[0.2.11]: https://github.com/alisonpezzott/pyfabricops/compare/v0.2.10...v0.2.11
[0.2.10]: https://github.com/alisonpezzott/pyfabricops/compare/v0.2.9...v0.2.10
[0.2.9]: https://github.com/alisonpezzott/pyfabricops/compare/v0.2.8...v0.2.9
[0.2.8]: https://github.com/alisonpezzott/pyfabricops/compare/v0.2.7...v0.2.8
[0.2.7]: https://github.com/alisonpezzott/pyfabricops/compare/v0.2.6...v0.2.7
[0.2.6]: https://github.com/alisonpezzott/pyfabricops/compare/v0.2.5...v0.2.6
[0.2.5]: https://github.com/alisonpezzott/pyfabricops/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/alisonpezzott/pyfabricops/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/alisonpezzott/pyfabricops/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/alisonpezzott/pyfabricops/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/alisonpezzott/pyfabricops/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.29...v0.2.0
[0.1.29]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.28...v0.1.29
[0.1.28]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.27...v0.1.28
[0.1.27]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.26...v0.1.27
[0.1.26]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.25...v0.1.26
[0.1.25]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.24...v0.1.25
[0.1.24]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.23...v0.1.24
[0.1.23]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.22...v0.1.23
[0.1.22]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.21...v0.1.22
[0.1.21]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.20...v0.1.21
[0.1.20]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.19...v0.1.20
[0.1.19]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.18...v0.1.19
[0.1.18]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.17...v0.1.18
[0.1.17]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.16...v0.1.17
[0.1.16]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.15...v0.1.16
[0.1.15]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.14...v0.1.15
[0.1.14]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.13...v0.1.14
[0.1.13]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.12...v0.1.13
[0.1.12]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.11...v0.1.12
[0.1.11]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.10...v0.1.11
[0.1.10]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.9...v0.1.10
[0.1.9]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.8...v0.1.9
[0.1.8]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.7...v0.1.8
[0.1.7]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/alisonpezzott/pyfabricops/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/alisonpezzott/pyfabricops/releases/tag/v0.1.0
