# pyfabricops examples

Runnable examples of pyfabricops, and a sample workspace to deploy with
them. Everything here is made up: no real tenant, workspace or data.

> Never commit credentials, real workspace IDs or client data. Keep
> secrets in a `.env` file outside Git, or in your CI secret store, and
> use placeholders in item definitions.

## Before you start

- **pyfabricops.** These examples use features of the next release:
  dependency resolution, deployment state and planning. Until it is out,
  install from the repository:

  ```bash
  pip install "pyfabricops @ git+https://github.com/alisonpezzott/pyfabricops"
  ```

- **A service principal** that can use the Fabric APIs, which is a tenant
  setting, and is a Contributor, or above, on the target workspace.
- **A `.env` file** with its credentials, kept out of Git:

  ```text
  FAB_CLIENT_ID=<client-id>
  FAB_CLIENT_SECRET=<client-secret>
  FAB_TENANT_ID=<tenant-id>
  ```

- **A workspace on a Fabric capacity** to deploy to: a sandbox, the first
  time.

## The sample workspace

`sample-workspace/` holds six items in the format Fabric Git integration
writes. Its folders become workspace folders.

```text
sample-workspace/
├── Data/
│   ├── Bronze.Lakehouse         raw data, with schemas
│   ├── Utils.Notebook           helpers, loaded with %run Utils
│   ├── LoadOrders.Notebook      loads the sample orders into Bronze
│   └── DailyLoad.DataPipeline   runs LoadOrders
└── Reports/
    ├── Sales.SemanticModel      a sales model, with its data inline
    └── Sales.Report             one page on the Sales model
```

The items refer to one another, and the deployment engine follows these
references:

| Item | Needs | Through |
| :--- | :--- | :--- |
| LoadOrders.Notebook | Bronze.Lakehouse | its default lakehouse, by logical ID |
| LoadOrders.Notebook | Utils.Notebook | `%run Utils` |
| Sales.Report | Sales.SemanticModel | `definition.pbir`, by path |
| DailyLoad.DataPipeline | LoadOrders.Notebook | the notebook ID, known once it is deployed |

So the lakehouse and Utils are deployed before LoadOrders, and the model
before the report. The report, which points to the model by path in Git,
is sent bound to the model's ID in the target workspace.

Placeholders are replaced in a staging copy, never in Git:

| Placeholder | In | Replaced with |
| :--- | :--- | :--- |
| `#{environment}#` | `Sales.SemanticModel/definition/expressions.tmdl` | the environment name, which the report shows |
| `#{workspace_id}#` | `DailyLoad.DataPipeline/pipeline-content.json` | the ID of the target workspace |
| `#{load_orders_notebook_id}#` | `DailyLoad.DataPipeline/pipeline-content.json` | the ID of LoadOrders in the target workspace |

The model holds its data inline, so it deploys and refreshes without a
data source. A real model would read the lakehouse, with its connection in
`expressions.tmdl` replaced the same way.

## The examples

| Folder | What it shows |
| :--- | :--- |
| `01-authentication/` | Authenticating with a service principal from `.env`, and the other ways to sign in. |
| `02-export/` | Exporting a workspace to a folder, to start a repository from it. |
| `03-deploy-full/` | Deploying a folder of items: staging, placeholders, plan, then deploy, pipelines last. |
| `04-deploy-selective/` | Deploying only what changed in Git since the last successful deployment, with a deployment state. |
| `05-ci-azure-devops/` | An Azure Pipelines definition that runs the selective deployment. |
| `06-ci-github-actions/` | A GitHub Actions workflow that runs it. |
| `07-reconcile/` | Reporting drift: how the workspace stands against the source, with scheduled Azure DevOps and GitHub Actions definitions that fail when anything differs. |

Run the scripts from the repository root, for example:

```bash
python examples/03-deploy-full/deploy.py --workspace <workspace-name> --environment DEV
```

`03-deploy-full` and `04-deploy-selective` print the plan before they
deploy, and exit with 1 when an item fails. `07-reconcile` prints what
differs, changing nothing, and exits with 1 when anything does: an item
missing from the workspace, one changed or moved there by hand, or one the
source lacks. The sample workspace is what
`tests/test_examples.py` checks: the plan it gives, what each item needs,
and that no ID other than its own made-up ones gets into this folder.
