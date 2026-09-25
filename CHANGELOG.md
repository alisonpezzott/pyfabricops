# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `deploy_all_items()` accepts `item_types`, to deploy only some item types
  (e.g. `["Notebook", "DataPipeline"]` on every merge), and `fail_fast`. It
  returns a `DeploymentReport` with the outcome and duration of each item:
  `report.failed`, `report.summary()`, `report.durations_by_type()` and
  `report.to_df()`.
- `DEPLOY_ORDER` — the item types `deploy_all_items()` deploys by default, in
  dependency order.
- Selective deployment: `deploy_all_items(baseline_commit=...)` deploys only
  the items changed in Git between that commit and HEAD, and
  `repository_path` names the repository folder to compare when `path` is a
  staging copy (as made by `copy_to_staging()`). An item deleted since the
  baseline is reported as failed while the workspace still has it, because
  deleting is not supported yet, and needs nothing once it is gone. Git must
  be on PATH and the baseline commit in the local history; a shallow clone
  may lack it.
- Deployment state: `deploy_all_items(state_backend=..., environment=...)`
  takes the baseline from the last successful deployment to the environment,
  instead of a manual `baseline_commit`. The state keeps one commit per item
  type, so a run limited by `item_types` advances only its types and a later
  full run still deploys what changed in the others. HEAD is recorded only
  when every item succeeded; a type never deployed gets every item. A state
  recorded for another workspace is ignored. `LocalJsonStateBackend` keeps
  states as JSON files in a folder; any object with `load(environment)` and
  `save(environment, state)` is a `DeploymentStateBackend`. States hold no
  secrets.
- Content hash: with a deployment state, an item whose definition and
  folder are those its last successful deployment sent is skipped, even
  when Git lists it as changed, and one whose folder only changed is moved
  (`MOVE` in the plan, `"moved"` in the report) without sending its
  definition again, to the workspace root too. The hash is taken on what
  would be sent (after placeholders are replaced, so it is per environment)
  and ignores part order, UTF-8 byte order marks, Windows line endings and
  the layout and key order of JSON files. The state records it per item;
  states written without it still load. Without a state, nothing is
  skipped or moved without its definition.
- `plan_all_items()` shows what `deploy_all_items()` would do with the
  same arguments, without doing it: it returns the `DeploymentPlan`, one
  action per item saying what would happen and why (`plan.describe()` gives
  it as text), and only reads the local items, Git and one listing of the
  workspace. The deployment state is read, never updated.
  `DeploymentPlan`, `DeploymentAction`, `DeploymentActionType` and
  `DeploymentReason` are exported.
- `set_lro_options()` — configures the long-running operation timeout
  (default 600 s) and the maximum polling interval (default 5 s).
- `get_item_definition()` accepts an optional `format` (e.g. `"TMDL"`).
- `create_item()` accepts `item_type`, sent as the `type` property the Create
  Item API documents as required. `deploy_item()` now passes it.
- `api_request()` accepts `return_result=True` to get the final `ApiResult`
  after pagination or LRO polling, so callers can tell a failure from a
  success without data.
- `copy_to_staging()` accepts `staging_dir`, the folder to copy into (as
  `<staging_dir>/<folder name>`), such as a temporary folder of the CI run.
  Without it the copy still goes to `_stg` inside the installed package,
  which every run using the installation shares and which cannot be
  written on a read-only install.
- Dependency resolution: `deploy_all_items()` and `plan_all_items()` read
  the references between local items:
  - a report's semantic model;
  - a notebook's default lakehouse, by logical ID or else by name;
  - a notebook's environment, by logical ID;
  - the notebooks a notebook runs with `%run`.

  With `resolve_dependencies=True`, the default, each item is deployed
  after what it needs.
  - A needed item that is not selected is validated when the workspace has
    it (`DeploymentReason.DEPENDENCY_REQUIRED`).
  - Otherwise it is created, when it is in the source and among
    `item_types`.
  - An item is blocked when a reference of its definition is broken, when it
    is part of a dependency cycle, or when something it needs is blocked or
    cannot be created.
  - Each action lists in `DeploymentAction.needs` the items of the plan it
    needs. When one of them fails to deploy, the item is skipped, and so is
    what needs a skipped item; the rest of the run goes on, and since the
    deployment state does not move, the next run tries them again.
  - A data pipeline's references by ID (notebooks, pipelines, dataflows,
    lakehouses and other items, nested activities included) are checked
    against the workspace after staging. An ID the workspace lacks, or a
    value that is no ID (a placeholder left unreplaced), gives a warning in
    the plan and in the log, without blocking, since an item created in the
    same run gets its ID when created. References to other workspaces are
    not checked.

  `resolve_dependencies=False` keeps the earlier behavior. The Dependencies
  page of the documentation shows what the plan does in each case.
- Reports whose `definition.pbir` points to their semantic model by path
  (`byPath`), as Fabric Git integration and Power BI projects write it, can
  be deployed. `deploy_all_items()` sends the reference as a connection to
  the model's ID in the target workspace (`byConnection`), the only form
  the Fabric API accepts, using the model created earlier in the run or the
  one already there. The file is unchanged. Without such a model the report
  fails with the reason, and nothing is sent.
- `reconcile_items()` tells how a workspace stands against the source,
  changing nothing. It returns a `Reconciliation`:
  - a plan of what would bring the workspace back: `CREATE` for an item it
    lacks, with the new reason `TARGET_MISSING`; `UPDATE` for one whose
    definition differs, with the new reason `WORKSPACE_DRIFT`, or
    `SOURCE_CHANGED` when the deployment state shows the source changed
    since the last deployment; `MOVE` for one in another folder;
  - the items the workspace holds and the source does not
    (`UnmanagedItem`), of any type but the SQL endpoint of a lakehouse;
  - the items whose definition could not be compared, and the items in
    sync.

  Each definition is compared with the one the workspace returns, leaving
  out what Fabric rewrites by itself: layout, the logical ID in
  `.platform`, a report's reference to its model, the `ref` lines of
  `model.tmdl`, and the empty parts it adds, such as a lakehouse's
  `shortcuts.metadata.json`. A difference names the parts that differ.
  `Reconciliation` and `UnmanagedItem` are exported. The Reconciliation
  page of the documentation explains each finding.
- An `examples/` folder, in the repository but not in the package:
  - a sample workspace in Fabric's Git format, with a lakehouse, notebooks,
    a pipeline, a semantic model and a report that refer to one another;
  - scripts that authenticate, export a workspace, and deploy the sample
    fully or only what changed since the last deployment;
  - Azure DevOps and GitHub Actions definitions that run the selective
    deployment;
  - a reconciliation that reports drift, with scheduled Azure DevOps and
    GitHub Actions definitions that fail when anything differs.

  `tests/test_examples.py` checks the plan the sample gives, and that no
  ID other than its own made-up ones gets into the folder.

### Changed
- `deploy_all_items()` and the `deploy_all_*` helpers for notebooks, semantic
  models, reports, environments, data pipelines and dataflows gen2 share one
  engine and now return a `DeploymentReport` instead of `None`:
  - the workspace items and folders are listed once per run, not once per
    item;
  - item types are deployed in dependency order (VariableLibrary → Lakehouse
    → Warehouse → Environment → Notebook → Dataflow → CopyJob → DataPipeline
    → SemanticModel → Report);
  - items are created through the generic Create Item API, with `type`;
  - existing items are moved only when their folder differs;
  - a failed item no longer aborts the run, and the final message is a
    success only when every item succeeded.
- The engine behind `deploy_all_items()` now plans before it deploys: a
  planner decides, from the local items and the workspace listing, whether
  each item is created, updated or blocked (and why), without changing the
  workspace; an executor then applies that plan. Functions, arguments and
  `DeploymentReport` are unchanged. The plan model
  (`pyfabricops.helpers.deployment_plan`) is internal for now.
- Long-running operations are polled with a backoff (1 s, 2 s, 4 s, up to
  5 s) until a 600 s timeout, instead of every 5 s for at most 50 s.
- Throttled requests (429) are retried after the `Retry-After` seconds the
  service returns, up to 3 times and for waits of up to 60 s.
- Pagination follows the `continuationUri` returned by the service, which
  keeps the original query parameters.
- The error of a failed item in a `DeploymentReport`, and of a failed
  long-running operation, goes on with the messages of the service's
  `moreDetails`, which often hold the cause: `InvalidInput - The request has
  an invalid input` is followed by, say, `DisplayName is Invalid for
  ArtifactType. DisplayName: Bronze-Raw`.

### Fixed
- `copy_to_staging()` refuses a staging folder that is the source folder,
  holds it or lies inside it, since replacing it would delete the source or
  copy it into itself. A source path ending with a separator no longer
  stages into the parent folder itself.
- A long-running operation that had already succeeded at the first status
  check returned no data, so `get_item_definition()` and the export helpers
  could intermittently get `None`. The result is now fetched from the URL
  the service advertises.
- A failed long-running operation was reported as a success: the operation
  state came back as if it were the result.
- The `export_all_*` helpers for items, notebooks, semantic models, reports,
  environments, data pipelines and dataflows gen2 stopped at the first item
  whose definition could not be read. They now log it, skip it and go on,
  without leaving an empty folder behind.
- `deploy_environment()` and `deploy_all_environments()` passed
  `item_definition=` to functions that take `environment_definition`, and
  failed with `TypeError`.
- Two local folders with the same type and display name were deployed onto
  the same item, the last one silently winning. `deploy_all_items()` now
  reports the second one as failed.
- `pack_item_definition()` return annotation is now `dict[str, Any]`.
- Cached access tokens are kept per identity (tenant, client ID and, for
  `credential_type="user"`, the username), so switching credentials no
  longer reuses the previous identity's token. The cache moved from the
  shared temporary folder to `pyfabricops/token_cache.json` in the user's
  cache folder, in a folder and a file only that user can read, and it is
  no longer created on import. `set_auth_provider()` and
  `clear_token_cache()` are unchanged.
- `docs/functions/items/environments.md` referenced the removed
  `pyfabricops.items.environments_gen2` module (renamed to `environments` in
  an earlier refactor), which made `mkdocs build` fail outright and broke
  the entire generated API reference, not just that one page.
- `create_workspace_custom_pool()` docstring documented a `workspace_custom_pool`
  parameter that isn't part of its signature (copy-pasted from
  `update_workspace_custom_pool`), and mislabeled `display_name` in the
  example. Corrected the `Args`, `Returns`, and example to match the actual
  function.

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
