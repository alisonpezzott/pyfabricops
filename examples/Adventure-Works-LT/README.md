# Adventure Works LT: from a workspace connected to Git to production

A medallion project on Adventure Works LT, as Fabric Git integration writes
it, and the script that deploys it from DEV to PRD. The IDs in it are made
up; in your repository, Fabric writes its own.

This folder is the root of a repository:

```text
.
├── fabric-workspace/                 the items: the Git folder of DEV
├── deploy.py                         deploys, plans, reconciles, restores
├── azure-pipelines.yml               Azure DevOps: deploy when main changes
├── azure-pipelines-reconcile.yml     Azure DevOps: drift report, weekdays
├── .github/workflows/deploy.yml      GitHub Actions: deploy when main changes
├── .github/workflows/reconcile.yml   GitHub Actions: drift report, weekdays
└── .env.example                      the credentials, for local runs
```

- **DEV** is connected to `fabric-workspace` with Fabric Git integration, on
  the `develop` branch. You work there, and commit from the workspace.
- **PRD** has no Git connection. It gets what reaches `main`, through a pull
  request from `develop`: the pipeline deploys it with pyfabricops.

## The items

| Item | What it does |
| :--- | :--- |
| `variables.VariableLibrary` | The database connection of each environment: the default values for DEV, the `Production` value set for PRD |
| `bronze.Lakehouse` | The tables copied from Azure SQL, in the `SalesLT` schema |
| `silver.Lakehouse` | A shortcut, `SalesLT`, to the `SalesLT` tables of bronze |
| `silver_to_gold.Notebook` | Builds the gold tables from silver; its default lakehouse is gold |
| `gold.Lakehouse` | The star schema |
| `orchestrator.DataPipeline` | Copies each table from Azure SQL to bronze, then runs the notebook |
| `sm_adventure_works_lt.SemanticModel` | Direct Lake on the OneLake tables of gold |
| `rp_adventure_works_lt.Report` | A report on the model |

## What refers to what

The items of DEV refer to one another by the IDs of DEV. Sent as they are,
the items of PRD would read and write DEV. `deploy.py` copies them to a
staging folder, where each of these IDs becomes the ID of the same item,
by type and name, in PRD, as Fabric lists both workspaces at every run.
The repository is never changed.

| Reference | In Git | In PRD |
| :--- | :--- | :--- |
| Connection of the copy | the variable `datasource_connection_id` | the connection of the `Production` value set, made active by the script |
| Sink of the copy | bronze, by logical ID, in the empty workspace | bronze of PRD, by ID |
| Notebook the pipeline runs | its logical ID, in the empty workspace | the notebook of PRD, by ID |
| Shortcut of silver | bronze, by logical ID, in the empty workspace | bronze of PRD, by its logical ID there |
| Default lakehouse of the notebook | gold and silver, and the workspace, by the IDs of DEV | gold, silver and the workspace of PRD |
| Source of the model | the OneLake path of gold in DEV | the OneLake path of gold in PRD |
| Model of the report | its folder (`byPath`) | the model of PRD, which pyfabricops binds |

A rule decides what is translated: what a variable library holds is taken
as it is, since its value sets hold what differs between environments; any
other reference to an item follows the target workspace.

In the sample, the IDs follow a pattern, to be read at a glance:

| ID | Stands for |
| :--- | :--- |
| `00000000-0000-4000-8000-000000000001` | the DEV workspace |
| `00000000-0000-4000-8000-0000000001NN` | the logical ID of item NN, in its `.platform` |
| `00000000-0000-4000-8000-0000000002NN` | the ID of item NN in DEV |
| `00000000-0000-4000-8000-000000000301`, `...302` | the connections of DEV and PRD |
| `00000000-0000-4000-8000-0000000010NN` | lineage tags and relationships of the model |

The items are numbered in the order of their folders, from `bronze` (01) to
`variables` (08).

## Before you start

- **pyfabricops 0.7.0 or later.**
- **A service principal**, allowed to call the Fabric APIs by the tenant
  settings. It is a Viewer of DEV, to read its IDs, and a Contributor of
  PRD and of the workspace that keeps the deployment state. When it
  publishes the pipeline, the pipeline may run as it: it then needs to be
  a user of the connection of the `Production` value set.
- **A lakehouse for the deployment state**, in a workspace of its own, such
  as `Adventure-Works-LT-OPS`, not in DEV, which would commit it, nor in
  PRD, where it would be an item the source lacks. On your machine,
  `--state-dir` keeps the state in a folder instead.
- **A `.env` file**, copied from `.env.example`, with the credentials of the
  service principal. Keep it out of Git.

## Run it

From this folder, with the names of your workspaces:

```bash
python deploy.py --source-workspace Adventure-Works-LT-DEV --workspace Adventure-Works-LT-PRD --value-set Production --plan
```

- Without `--plan`, it deploys: each item type in turn, in the dependency
  order of pyfabricops, pipelines last. Within a type, the items the others
  refer to go first, such as bronze before silver. The run stops before it
  sends an item that would still refer to DEV.
- `--reconcile` tells how PRD stands against the repository, the active
  value sets included, and changes nothing. It exits with 1 when anything
  differs.
- `--restore` brings back what drifted in PRD: an item deleted, edited or
  moved there by hand, and the active value sets. Nothing is deleted.
- With `--state-workspace` and `--state-lakehouse`, or `--state-dir`, a
  deployment sends only what changed in Git since the last successful one,
  and holds a lock, so that two runs never deploy at a time. `--reconcile`
  and `--restore` read the state, to leave a deployment still to run alone.
- An item deleted in Git fails the deployment until it is deleted by hand,
  or the run is given `--allow-deletions`.

The first deployment creates everything. Then run the pipeline in PRD, once
by hand, and refresh the model: Direct Lake reads the gold tables only once
the pipeline has written them. Until bronze has its tables, the shortcut of
silver may show under Unidentified.

## Deploy from CI

The pipelines run the same script. They need only the history of the
repository, Python and the credentials:

| | Azure DevOps | GitHub Actions |
| :--- | :--- | :--- |
| Definitions | `azure-pipelines.yml`, `azure-pipelines-reconcile.yml` | `.github/workflows/deploy.yml`, `.github/workflows/reconcile.yml` |
| Credentials | the variable group `fabric-prd` | the secrets and variables of the environment `prd` |
| Approval | an Approval check on the environment `PRD` | required reviewers on the environment `prd` |
| One run at a time | an Exclusive Lock check | `concurrency` |
| History | `fetchDepth: 0` | `fetch-depth: 0` |

## Good to know

- **The active value set is no part of the definition.** A variable library
  created in PRD starts on its default values, those of DEV: without the
  script, the pipeline of PRD would read the database of DEV. The script
  makes the value set active and reads it back, and `--reconcile` checks it.
- **A shortcut to an item of the same workspace goes by logical ID.** Fabric
  looks the ID up among the logical IDs of the workspace, so the shortcut
  gets the logical ID of bronze in PRD. With its ID instead, the update of
  silver fails with `MissingShortcutDependency`.
- **The target tables are not deployed.** A deployment sends definitions,
  never data: the pipeline fills PRD.
