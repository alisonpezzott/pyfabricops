# Deploy a workspace, on a Fabric capacity or not

A Power BI Project, as Power BI Desktop saves it, and the script that deploys
it to two workspaces, DEV from the `develop` branch and PRD from `main`,
whether each is on a Fabric capacity or is a Pro workspace, without one. The
names, servers and IDs in it are made up; in your repository, Power BI
Desktop writes its own.

No workspace is connected to Git: the repository is the source of both
environments, and the pipeline deploys each of them with pyfabricops. The
same run serves both kinds of workspace, and the environments may mix them,
such as DEV on Pro and PRD on a capacity: a file per environment, in Git,
tells them apart.

This folder is the root of a repository:

```text
.
├── fabric-workspace/                 the Power BI Project: one model, two reports
├── environments/DEV.json             DEV: its workspace and the model parameters
├── environments/PRD.json             PRD: its workspace and the model parameters
├── deploy.py                         deploys, plans, reconciles, restores
├── azure-pipelines.yml               Azure DevOps: deploy when develop or main changes
├── azure-pipelines-reconcile.yml     Azure DevOps: drift report, weekdays
├── .github/workflows/deploy.yml      GitHub Actions: deploy when develop or main changes
├── .github/workflows/reconcile.yml   GitHub Actions: drift report, weekdays
└── .env.example                      the credentials, for local runs
```

| Branch | Environment | Workspace |
| :--- | :--- | :--- |
| `develop` | DEV | `Deploy-Workspace-DEV` |
| `main` | PRD | `Deploy-Workspace-PRD` |

## The items

| Item | What it is |
| :--- | :--- |
| `Main.SemanticModel` | An import model on Azure SQL, with two text parameters, `Server` and `Database` |
| `Main.Report` | A report on the model, bound to it by path |
| `Secondary.Report` | Another report on the same model, also bound by path |

The script deploys semantic models and reports, which any workspace holds.
It stops before it deploys anything when the repository has:

- any other item, such as a lakehouse, a notebook or a variable library;
- a Direct Lake model: its source is a lakehouse or a warehouse by ID, which
  the script does not translate, so PRD would read the data of DEV;
- a model saved as `model.bim`: the script reads the parameters of TMDL
  only, so the model would keep the values of DEV.

You work in Power BI Desktop: open `fabric-workspace/Main.pbip`, which opens
against DEV, save, and commit to a feature branch. A pull request to
`develop` deploys to DEV, and one from `develop` to `main` deploys to PRD.
Never publish to PRD from Power BI Desktop: the next deployment overwrites
it, and the reconcile job reports it as drift.

In the sample, the IDs follow a pattern, to be read at a glance:

| ID | Stands for |
| :--- | :--- |
| `00000000-0000-4000-8000-0000000001NN` | the logical ID of item NN, in its `.platform`: `Main.Report` (01), `Main.SemanticModel` (02), `Secondary.Report` (03) |
| `00000000-0000-4000-8000-000000001NNN` | lineage tags, the tables of the automatic date hierarchy, and the relationships of the model |

## The environments

Everything that tells DEV from PRD is in `environments/<ENV>.json`, in Git
and reviewed in pull requests like the items: the workspace, and the
parameter values of each semantic model.

```json
{
  "workspace": "Deploy-Workspace-PRD",
  "parameters": {
    "Main": {
      "Server": "your-prd-server.database.windows.net",
      "Database": "adventureworkslt"
    }
  }
}
```

The pipelines only pick the environment of their branch and run
`deploy.py --environment <ENV>`, which reads that file. The name also keys
the deployment state. The file must give every text parameter of every model
in the repository, and nothing else, so that no model keeps a value of DEV by
omission. Whether the workspace is on a capacity is not in the file: the
script does the same in both.

The repository keeps the values Power BI Desktop opens with, those of DEV.
`deploy.py` copies the items to a staging folder and sets the parameters of
the environment there; the repository is never changed.

## What a deployment does

For the environment of the branch, `deploy.py`:

1. Copies `fabric-workspace/` to a staging folder, without what Git ignores
   (the data cache and local settings of `.pbi`) and without
   `diagramLayout.json`, which the service does not keep: sent, a
   reconciliation would never find the model in sync.
2. Stops when the staging copy has what it cannot deploy (see
   [The items](#the-items)).
3. Sets the text parameters of each model in the staging copy.
4. Plans and deploys the semantic models, then the reports. A report bound to
   its model by path goes bound to the ID of the model in the workspace. With
   the deployment state, only what changed in Git since the last successful
   deployment is sent. A model whose parameters in the workspace differ from
   the file, as after a change of the file alone, is sent again.
5. For each model deployed, never refreshed, or whose last refresh failed:
   the service principal takes the model over; each SQL data source is bound
   to the **shareable cloud connection** of the same `server;database`; and
   the model is refreshed, without the options of an enhanced refresh, which
   a workspace without a capacity refuses: the plain refresh serves both. The
   run waits for the refresh.

The run fails when any step fails, and the next run retries a model that was
deployed but neither bound nor refreshed.

## Before you start

- **pyfabricops 0.8.1 or later.**
- **A service principal**, allowed to call the Fabric and Power BI APIs by
  the tenant settings, and a Contributor of both workspaces.
- **A shareable cloud connection per environment** to its SQL server and
  database, with the service principal as a user of it. `deploy.py` finds
  it by server and database, so no connection name or ID is configured.
- **The right for the pipeline to push to this repository.** The deployment
  state lives on `pyfabricops/state`, a branch of this repository that the
  first deployment creates. On your machine, `--state-dir` keeps it in a
  folder instead.
- **A `.env` file**, copied from `.env.example`, with the credentials of the
  service principal. Keep it out of Git.

## Run it

From this folder:

```bash
python deploy.py --environment DEV --plan
```

- Without `--plan`, it deploys, binds and refreshes.
- `--reconcile` tells how the workspace stands against the repository, the
  parameters of the models included, and changes nothing. It exits with 1
  when anything differs.
- `--restore` brings back what drifted, binds and refreshes the models it
  restored, and deletes nothing.
- `--state-branch pyfabricops/state`, or `--state-dir`, makes a deployment
  send only what changed in Git since the last successful one, and holds a
  lock, so that two runs never deploy at a time.
- `--workspace` deploys to another workspace than the one of the file.
- `--no-refresh` binds the models but does not refresh them.
- An item deleted in Git fails the deployment until it is deleted by hand, or
  the run is given `--allow-deletions`.

## Deploy from CI

The pipelines run the same script. The branch picks the environment:
`develop` deploys to DEV, `main` to PRD, and any other branch to nothing.

| | Azure DevOps | GitHub Actions |
| :--- | :--- | :--- |
| Definitions | `azure-pipelines.yml`, `azure-pipelines-reconcile.yml` | `.github/workflows/deploy.yml`, `.github/workflows/reconcile.yml` |
| Credentials | the variable group `fabric` | the secrets of the environments `dev` and `prd` |
| Environment of a run | picked from the branch when the pipeline is compiled: a run holds the stage of its own environment only, and nothing is edited at queue time | picked from the branch by the job |
| Approval | an Approval check on the environment `PRD` | required reviewers on the environment `prd` |
| One run at a time | an Exclusive Lock check on each environment | `concurrency`, per branch |
| History | `fetchDepth: 0` | `fetch-depth: 0` |
| Deployment state | Contribute and Create branch for the build service of the project, and `persistCredentials: true` on the checkout | `permissions: contents: write`, or `contents: read` to reconcile |

In Azure DevOps, allow both pipelines to use the variable group and the
environments, or **Permit** them on the first run of each branch; until
then, a run fails with "Variable group was not found or is not authorized
for use". In GitHub Actions, create the environments, with their secrets and
reviewers, before the first push: a job creates an environment it names
that does not exist, with no protection rule.

## Good to know

- **A model carries no credentials, and an import model arrives empty.**
  That is why each deployed model is bound and refreshed. A workspace without
  a capacity refreshes a model at most eight times a day, and each
  deployment of a model uses one.
- **A scheduled refresh is no part of the definition.** Set it once on the
  model in PRD; no deployment sets or changes it.
- **The service principal owns the models it deploys.** It also takes over a
  model first published to the workspace by someone else from Power BI
  Desktop.
- **Moving a workspace to a capacity, or off one, changes nothing here.** The
  script does the same in both, so neither the files nor the pipelines
  change.
- **Pointing an environment at another workspace is safe.** The state
  recorded for the old workspace is ignored, so the first run deploys every
  item to the new one.
- **The branch of the state is no branch of code.** Each deployment pushes
  commits to `pyfabricops/state`, marked `[skip ci]`. Never merge it, and
  leave it out of the rules that ask for a pull request or signed commits.
  Its history keeps who took each lock: in a public repository, that is
  public.
