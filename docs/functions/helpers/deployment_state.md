# Deployment State

The deployment state records what the last successful deployment to an
environment sent: the commit of each item type, and the hash and folder of
each item. With it, `deploy_all_items()` deploys only what changed since
then, and `reconcile_items()` tells drift in the workspace from a
deployment still to run. It is written only when every item of a run
succeeded, and it holds no secret.

A state backend keeps the states, one per environment. Pass it to
`deploy_all_items()`, `plan_all_items()` or `reconcile_items()` with the
environment's name:

```python
report = deploy_all_items(
    "Sales-PRD",
    staging,
    start_path=staging,
    repository_path="workspace",
    state_backend=OneLakeStateBackend("Ops", "DeploymentState"),
    environment="PRD",
)
```

## In a OneLake lakehouse

`OneLakeStateBackend(workspace, lakehouse)` keeps each state as
`Files/pyfabricops/state/<environment>.json` in a lakehouse, and survives
every CI run. Keep the lakehouse in a workspace of its own, such as one for
operations: in the workspace deployed to, `reconcile_items()` would report
it as unmanaged.

- The identity that deploys needs to write to that lakehouse, as a
  Contributor of its workspace. Its token for OneLake comes from
  `set_auth_provider()`, as for the Fabric API.
- The workspace and the lakehouse are given by name or ID, looked up once,
  then reached by ID.
- `folder` changes the folder under `Files`. `endpoint` takes a regional
  endpoint, such as `https://westus-onelake.blob.fabric.microsoft.com`, so
  the state stays in the region of the lakehouse's capacity.
- A state is saved only over the one the run read. When another run saved
  one in between, the save fails and the other run's state is kept:

  ```text
  Deployment state 'PRD' changed in Ops/DeploymentState/Files/pyfabricops/state/PRD.json since this run read it, so it was not overwritten: another run deployed to the environment meanwhile.
  ```

## On a branch of the repository

`GitStateBackend(repository, branch)` keeps each state as
`<environment>.json` on a branch of the repository itself,
`pyfabricops/state` by default. It needs no Fabric capacity and no storage
account, so a project whose workspaces have no capacity for a lakehouse
keeps its state where its code is:

```python
report = deploy_all_items(
    "Sales-PRD",
    staging,
    start_path=staging,
    repository_path="workspace",
    state_backend=GitStateBackend("workspace", "pyfabricops/state"),
    environment="PRD",
)
```

- `repository` is a folder inside the repository, such as the checkout of
  the pipeline; `remote` names its remote, `origin` by default, and
  `folder` a folder of the branch for the files.
- The first write creates the branch as an orphan, with no history in
  common with the others, holding a README that says what it is and a
  `.pyfabricops-state` marker. The backend writes to no branch without the
  marker: given `main` by mistake, it fails and changes nothing.
- Every change is a commit pushed without force, which the remote accepts
  only over the tip it was made on. A state is saved only over the one the
  run read, as in OneLake. When the branch moved because another
  environment wrote to it, the change is made again over the new tip.
- The commits leave the working tree, the index, HEAD and the branches of
  the checkout as they are. They say `[skip ci]`, so that no pipeline runs
  for them, and are pushed without the local pre-push hooks, which check
  code, not states. They are made by the Git identity of the repository,
  or by `pyfabricops <noreply@pyfabricops.invalid>` where there is none, as
  on a CI runner.
- git pushes with the credentials it already has; pyfabricops handles
  none. The pipeline needs the right to push to the branch, and to create
  it the first time:

  | | GitHub Actions | Azure DevOps |
  | :--- | :--- | :--- |
  | Deployment | `permissions: contents: write` | Contribute and Create branch for the build service of the project on the repository, and `persistCredentials: true` on the checkout |
  | `plan_all_items()`, `reconcile_items()` | `permissions: contents: read` | `persistCredentials: true` on the checkout |

- Block force pushes and deletion on the branch, which the backend never
  needs, and leave it out of the rules that ask for a pull request or
  signed commits. Merge it into nothing, and connect no workspace to it.
- What the backend writes stays in the history of the branch, the user and
  host that took each lock included. In a public repository, all of it is
  public, with the names of the items and the ID of each workspace.
- Each write is a push, which takes a second or two.

## In a local folder

`LocalJsonStateBackend(folder)` keeps each state as
`<folder>/<environment>.json`. Keep the folder between runs: without it, a
run deploys every item, which is safe but slower. A CI cache is not enough
for that, as GitHub drops a cache unused for 7 days, and Azure DevOps keeps
one per pipeline.

## Locks

A deployment holds the lock of its environment from before it reads the
state until after it records it, so two runs never deploy to one
environment at a time. Every backend keeps the lock next to the state, as
`<environment>.lock`, which says who holds it and until when:

```text
DeploymentLockedError: Deployment state 'PRD' is locked, held by runner@ci-host (GitHub Actions run 1234) since 2026-09-25T10:00:00Z, until 2026-09-25T12:00:00Z. Wait for that run to finish; if it is gone, call force_unlock('PRD') on the state backend.
```

- A run fails at once when another holds the lock, before it reads or
  deploys anything. `lock_timeout=<seconds>` on the backend waits for the
  lock instead.
- A lock holds for `lock_ttl` seconds, two hours by default, unless its run
  releases it; a failed run releases it too. After that another run takes
  it over, so a run that died holding it blocks the environment for no
  longer.
- `force_unlock(environment)` removes the lock whoever holds it, for a run
  that is gone. Make sure no run is deploying first.

  ```python
  OneLakeStateBackend("Ops", "DeploymentState").force_unlock("PRD")
  ```

- `plan_all_items()` and `reconcile_items()` only read the state, and take
  no lock.
- A lock holds no secret: the user and host that took it, the CI run when
  there is one, and when it was taken.

## Journal and resume

A deployment writes the journal of its run next to the state, as
`<environment>.journal.json`, each time an item ends: what it did to the
item, and the hash and folder it sent. When a run fails, or dies, before
it records the state, the next run knows what it already sent, and skips
each item still in the workspace that has not changed since:

```text
NOOP     Orders.Notebook  SOURCE_CHANGED: Definition and folder unchanged since an interrupted run sent it at 2026-09-26T10:04:12Z.
UPDATE   Daily.DataPipeline  SOURCE_CHANGED
```

- The state is still recorded only when a whole run succeeds; the journal
  never takes its place. The run that succeeds records what the
  interrupted runs sent, too.
- The journal holds the last run. A run that resumes another carries its
  entries over, so they are not lost if it is interrupted too.
- Each item costs one small write of the journal: a request of its own in
  OneLake, a push on a branch. A journal that cannot be written costs only
  the resume: the run warns and goes on.
- `plan_all_items()` shows the resume; it writes no journal.

## Other backends

Any object with `load(environment)` and `save(environment, state)` is a
`DeploymentStateBackend`. One that also has `lock(environment)` and
`force_unlock(environment)` is a `LockingStateBackend`, and deployments
hold its lock; one with `load_journal(environment)` and
`save_journal(environment, journal)` is a `JournalingStateBackend`, and
deployments keep their journal there. One without them works as well,
without a lock or a resume.

## Reference

::: pyfabricops.helpers.deployment_state

::: pyfabricops.helpers.onelake_state

::: pyfabricops.helpers.git_state
