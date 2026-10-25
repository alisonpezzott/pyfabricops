# Deploy a Fabric workspace with pyfabricops

A template repository: the script and the pipelines that deploy the items of
a Fabric workspace, with pyfabricops, to one workspace per environment. DEV
deploys from the `develop` branch and PRD from `main`. Copy it into a new
repository, fill in the environment files, and put the items in
`fabric-workspace/`.

The repository can be written in two ways, and the script tells them apart
by the environment files:

- **DEV connected to Git** (the default of this template). Fabric Git
  integration syncs the DEV workspace with `fabric-workspace/`. The items it
  writes hold the IDs of DEV, so the script never deploys to DEV and, for
  PRD, maps each DEV ID to the ID of the same item in PRD before sending it.
  Every item type pyfabricops deploys can go this way.
- **No workspace connected to Git.** Power BI Desktop saves a Power BI
  Project, which holds no workspace IDs, and the repository is the source of
  every environment, DEV included. Only variable libraries, semantic models
  and reports go this way.

Either way, a workspace may be on a Fabric capacity or a Pro workspace,
without one, and the environments may mix them.

```text
.
├── fabric-workspace/                 the items: Git folder of DEV, or a Power BI Project
├── environments/DEV.json             DEV: its workspace, connected to Git
├── environments/PRD.json             PRD: its workspace and value set
├── scripts/deploy.py                 deploys, plans, reconciles, restores
├── azure-pipelines/deploy.yml        Azure DevOps: deploy when develop or main changes
├── azure-pipelines/reconcile.yml     Azure DevOps: drift report, weekdays
├── .github/workflows/deploy.yml      GitHub Actions: deploy when develop or main changes
├── .github/workflows/reconcile.yml   GitHub Actions: drift report, weekdays
└── .env.example                      the credentials, for local runs
```

| Branch | Environment | File | Who writes the workspace |
| :--- | :--- | :--- | :--- |
| `develop` | DEV | `environments/DEV.json` | Fabric Git integration |
| `main` | PRD | `environments/PRD.json` | `scripts/deploy.py` |

## Set up a new repository

1. **Copy this template** into the new repository and push `main` and
   `develop`.
2. **Fill in the environment files.** Replace `workspace-name-or-id-DEV` and
   `workspace-name-or-id-PRD` with the name or ID of each workspace. Keep
   `"gitConnected": true` in `DEV.json`. In `PRD.json`, keep `valueSet` only
   if the workspace will have a variable library with a value set of that
   exact name; otherwise remove it (see [The environments](#the-environments)).
3. **Connect DEV to Git** (Workspace settings > Git integration) on
   `develop`, with `fabric-workspace` as the Git folder.
4. **Commit the items of DEV** from **Source control** in the workspace.
   Fabric writes one folder per item into `fabric-workspace/`.
5. **Prepare the credentials and connections** listed in
   [Before you start](#before-you-start).
6. **Create the pipelines** of [Deploy from CI](#deploy-from-ci).
7. **Check the first deployment** before running it:
   `python scripts/deploy.py --environment PRD --plan`.

`fabric-workspace/README.md` only keeps the folder in Git while it has no
items. Fabric Git integration ignores it, and so does the script.

## What can go in `fabric-workspace/`

| DEV connected to Git | No workspace connected |
| :--- | :--- |
| Every item type pyfabricops deploys, such as lakehouses, notebooks, pipelines, Direct Lake models, variable libraries, semantic models and reports | Variable libraries, import or DirectQuery semantic models, and reports |

The script stops before it deploys anything when the repository has:

- an item of a type pyfabricops does not deploy;
- without an environment connected to Git, any item but a variable library,
  a semantic model or a report, or a Direct Lake model: their IDs would
  still point to DEV;
- for a Pro workspace, any item but a semantic model or a report;
- a model saved as `model.bim`: the script reads the parameters of TMDL
  only.

## How you work

1. Work in the DEV workspace, or in Power BI Desktop against DEV.
2. Commit from **Source control** in the DEV workspace to `develop`, or
   from a feature branch through a pull request to `develop`. The pipeline
   runs on `develop` too, but only reports that DEV is connected to Git and
   exits.
3. Open a pull request from `develop` to `main`. Once it is merged, the
   pipeline deploys to PRD.

Never edit or publish to PRD by hand: the next deployment overwrites it, and
the reconcile job reports it as drift.

## The environments

Everything that tells DEV from PRD is in `environments/<ENV>.json`, in Git
and reviewed in pull requests like the items. The file name is the
environment name passed to `--environment`, and it also keys the deployment
state.

The environment connected to Git gives its workspace and nothing else. At
most one environment may be connected:

```json
{
  "workspace": "workspace-name-or-id-DEV",
  "gitConnected": true
}
```

Every other environment gives its workspace and, optionally, the value set
of its variable libraries and the parameters of its semantic models:

```json
{
  "workspace": "workspace-name-or-id-PRD",
  "valueSet": "Production",
  "parameters": {
    "<model name>": {
      "<parameter name>": "<value in PRD>"
    }
  }
}
```

| Key | What it does |
| :--- | :--- |
| `workspace` | The workspace to deploy to, by name or ID. `--workspace` overrides it for a local run. |
| `gitConnected` | `true` for the environment Fabric Git integration writes. No run deploys to it, and the script reads its items to translate their IDs. |
| `valueSet` | The value set made active in every variable library after the deployment. Every library must have it, with this exact name, and the run stops when the repository has no variable library. Without it, the libraries keep their default values, which are those of DEV. |
| `parameters` | The text parameters of each semantic model, by model and parameter name. A parameter left out keeps the value of the repository, the one of DEV, and the run says which. A model or parameter the repository does not have stops the run, so a misspelled name never goes unnoticed. |

Whether the workspace is on a capacity is not in the file: the script reads
it from Fabric.

To add an environment, such as TST, add `environments/TST.json` and a
branch, stage or job that runs `--environment TST` in the pipelines.

## What a deployment does

For the environment of the branch, `scripts/deploy.py`:

1. Exits without doing anything when the environment is connected to Git.
2. Copies `fabric-workspace/` to a staging folder, without what Git ignores
   (the data cache and local settings of `.pbi`) and without
   `diagramLayout.json`, which the service does not keep. The repository is
   never changed.
3. Stops when the staging copy has what it cannot deploy (see
   [What can go in `fabric-workspace/`](#what-can-go-in-fabric-workspace)),
   and checks the environment file: its parameters and its value set.
4. Sets the text parameters of each model in the staging copy.
5. With DEV connected to Git, maps each ID of DEV in the staging copy to the
   ID of the same item, by type and name, in the target workspace. Fabric
   lists both workspaces at every run. This covers, for example, the
   default lakehouse of a notebook, the OneLake source of a Direct Lake
   model and the items a pipeline runs. A shortcut to an item of the same
   workspace gets the logical ID of that item in the target.
6. Deploys one item type at a time, in the dependency order of pyfabricops,
   with pipelines last. An item then refers by ID only to items already in
   the target, and a report bound to its model by path goes bound to the ID
   of the model there. Within a type, the items the others refer to go
   first, such as a lakehouse a shortcut points to. The run stops before it
   sends an item that would still refer to DEV.
7. With the deployment state, sends only what changed in Git since the last
   successful deployment. A model whose parameters in the workspace differ
   from those it is deployed with is sent again.
8. Makes the value set of the environment active in each variable library,
   and reads it back. The active value set is not part of the definition, so
   no deployment sets it otherwise.
9. For each import model deployed, never refreshed, or whose last refresh
   failed: the service principal takes the model over; each SQL data source
   is bound to the **shareable cloud connection** of the same
   `server;database`; and the model is refreshed and the run waits for it.
   The refresh is a plain one, without the options of an enhanced refresh,
   which a workspace without a capacity refuses. A Direct Lake model is left
   alone: it reads its tables as they are loaded.

The run fails when any step fails, and the next run retries a model that was
deployed but neither bound nor refreshed.

## Before you start

- **pyfabricops 0.8.1 or later.**
- **A service principal**, allowed to call the Fabric and Power BI APIs by
  the tenant settings, Contributor of each workspace it deploys to, and able
  to read the items of DEV when DEV is connected to Git.
- **A shareable cloud connection per environment** to each SQL server and
  database an import model reads, with the service principal as a user of
  it. The script finds it by server and database, so no connection name or
  ID is configured.
- **A place for the deployment state:**
  - `pyfabricops/state`, a branch of this repository that the first
    deployment creates (`--state-branch`), as the pipelines do. The pipeline
    needs the right to push to it.
  - A lakehouse (`--state-workspace` and `--state-lakehouse`).
  - A local folder (`--state-dir`), for runs on your machine.
- **A `.env` file**, copied from `.env.example`, with the credentials of the
  service principal. Keep it out of Git.

## Run it

From the root of the repository:

```bash
python scripts/deploy.py --environment PRD --plan
```

| Option | What it does |
| :--- | :--- |
| *(none)* | Deploys, activates the value set, binds and refreshes. |
| `--plan` | Prints the plan and changes nothing. |
| `--reconcile` | Reports how the workspace stands against the repository, including model parameters and active value sets, and changes nothing. Exits with 1 when anything differs. |
| `--restore` | Brings back what drifted, makes the value set active again, binds and refreshes the models it restored, and deletes nothing. |
| `--state-branch pyfabricops/state` | Keeps the deployment state on a branch: only what changed in Git since the last successful run is sent, and a lock keeps two runs from deploying at the same time. |
| `--state-workspace`, `--state-lakehouse` | Keeps the deployment state in a lakehouse instead. Both go together. |
| `--state-dir` | Keeps the deployment state in a local folder instead. |
| `--workspace` | Deploys to another workspace than the one of the file. |
| `--source` | Reads the items from another folder than `fabric-workspace`. |
| `--no-refresh` | Binds the models but does not refresh them. |
| `--allow-deletions` | Deletes from the workspace the items deleted in Git. Without it, an item deleted in Git fails the deployment until it is deleted by hand. |

## Deploy from CI

The pipelines run the same script. The branch picks the environment:
`develop` runs DEV, which exits at once because it is connected to Git;
`main` deploys to PRD; any other branch deploys to nothing.

| | Azure DevOps | GitHub Actions |
| :--- | :--- | :--- |
| Definitions | `azure-pipelines/deploy.yml`, `azure-pipelines/reconcile.yml` | `.github/workflows/deploy.yml`, `.github/workflows/reconcile.yml` |
| Credentials | the variable group `fabric` | the secrets of the environments `dev` and `prd` |
| Environment of a run | picked from the branch when the pipeline is compiled: a run holds the stage of its own environment only, and nothing is edited at queue time | picked from the branch by the job |
| Approval | an Approval check on the environment `PRD` | required reviewers on the environment `prd` |
| One run at a time | an Exclusive Lock check on each environment | `concurrency`, per branch |
| History | `fetchDepth: 0` | `fetch-depth: 0` |
| Deployment state | Contribute and Create branch for the build service of the project, and `persistCredentials: true` on the checkout | `permissions: contents: write`, or `contents: read` to reconcile |

In Azure DevOps, create each pipeline from **Existing Azure Pipelines YAML
file**, pointing at the file in `azure-pipelines/`. Allow both pipelines to
use the variable group and the environments, or **Permit** them on the first
run of each branch; until then, a run fails with "Variable group was not
found or is not authorized for use". In GitHub Actions, create the
environments, with their secrets and reviewers, before the first push: a job
creates an environment it names that does not exist, with no protection
rule.

## Good to know

- **A model carries no credentials, and an import model arrives empty.**
  That is why each deployed model is bound and refreshed. A workspace without
  a capacity refreshes a model at most eight times a day, and each
  deployment of a model uses one.
- **A scheduled refresh is not part of the definition.** Set it once on the
  model in PRD; no deployment sets or changes it.
- **An environment without `valueSet` stays on the default values.** The
  Fabric API documents no way back to them, so the script leaves the active
  value set of such an environment alone.
- **The service principal owns the models it deploys.** It also takes over a
  model first published to the workspace by someone else.
- **Moving a workspace to a capacity, or off one, changes nothing here,**
  unless the repository has items a Pro workspace cannot hold.
- **Pointing an environment at another workspace is safe.** The state
  recorded for the old workspace is ignored, so the first run deploys every
  item to the new one.
- **The state branch is not a code branch.** Each deployment pushes commits
  to `pyfabricops/state`, marked `[skip ci]`. Never merge it, and leave it
  out of the rules that ask for a pull request or signed commits. Its
  history keeps who took each lock: in a public repository, that is public.
