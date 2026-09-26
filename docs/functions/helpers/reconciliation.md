# Reconciliation

`reconcile_items()` tells how a workspace stands against the source: what
the workspace lacks, what changed in it, and what it holds that the source
does not. It changes nothing. It reads the definition of every item found
on both sides, so it suits a scheduled run, or a check before a release,
more than every deployment.

```python
staging = copy_to_staging("workspace", staging_dir=tmp)
find_and_replace(staging, {(r".*\.tmdl$", r"#\{environment\}#"): "PRD"})

reconciliation = reconcile_items(
    "Sales-PRD",
    staging,
    start_path=staging,
    state_backend=LocalJsonStateBackend(".deploy-state"),
    environment="PRD",
)
print(reconciliation.describe())
if not reconciliation.ok:
    raise SystemExit(1)
```

Compare the staging copy, with the placeholders of the environment
replaced, as a deployment would send it.

## What it finds

```text
UPDATE   Orders.Notebook  WORKSPACE_DRIFT: Changed in the workspace since the last deployment: notebook-content.py.
CREATE   Sales.Report  TARGET_MISSING: Deleted from the workspace since the last deployment.
MOVE     Utils.Notebook  WORKSPACE_DRIFT: Moved to 'Archive' in the workspace since the last deployment; the source has it in 'Data'.
UNMANAGED Draft.Notebook: in the workspace, not in the source.
UNCHECKED Logs.Eventhouse: Fabric returned no definition: 400: OperationNotSupportedForItem - ...
3 in sync, 1 create, 1 update, 1 move, 0 blocked, 1 unmanaged, 1 unchecked
```

| Line | Meaning |
| :--- | :--- |
| `CREATE` `TARGET_MISSING` | In the source, not in the workspace. |
| `UPDATE` `WORKSPACE_DRIFT` | The definition differs: changed in the workspace since the last deployment or, without a deployment state, different from the source. |
| `UPDATE` `SOURCE_CHANGED` | Changed in the source since the last deployment: a deployment still to run, not drift. |
| `MOVE` | In another workspace folder than the source says. |
| `BLOCKED` | A local item that cannot be read, or that the source defines twice. |
| `UNMANAGED` | In the workspace, not in the source, of any type but the SQL endpoint that comes with a lakehouse. Types pyfabricops does not deploy are pointed out. |
| `UNCHECKED` | Fabric returned no definition to compare, so only the item's presence and folder were checked. |

`Reconciliation.plan` holds what would bring the workspace back to the
source, as a `DeploymentPlan`; `unmanaged`, `unchecked` and `in_sync` hold
the rest. `ok` is True when nothing differs and nothing is unmanaged. An
unchecked item does not count, as some item types never return a
definition.

## How definitions are compared

Each item's definition in the source is compared with the one the
workspace returns. Fabric rewrites some parts on its own; measured against
a workspace, a definition read back right after a deployment differs only
in these, which the comparison leaves out:

- the layout: line endings, the end of a file, JSON indentation and key
  order;
- the logical ID in `.platform`, which Fabric assigns to each item;
- a report's reference to its semantic model: by path in Git, by
  connection in the workspace. Both are compared by the model they point
  to;
- the `ref` lines Fabric adds to `model.tmdl` to order a model's tables;
- a part that holds nothing, such as the empty `shortcuts.metadata.json`
  Fabric adds to a lakehouse sent without one, when the other side lacks
  it.

A difference names the parts of the definition that differ.

## With a deployment state

The deployment state records a hash of what the last successful deployment
sent. With it, a difference tells where it comes from:

- the source is as it was deployed, so the workspace changed:
  `WORKSPACE_DRIFT`;
- the source changed since: `SOURCE_CHANGED`, which the next selective
  deployment will send.

It tells the same of a folder: moved in the workspace, or in the source.

## Restoring what drifted

`restore_items()` takes the same arguments, and brings the workspace back
to the source where it drifted: it reconciles, then applies what undoes
the drift, as `deploy_all_items()` applies a plan.

```python
report = restore_items(
    "Sales-PRD",
    staging,
    start_path=staging,
    state_backend=OneLakeStateBackend("Ops", "DeploymentState"),
    environment="PRD",
)
print(report.describe())
```

```text
updated  Orders.Notebook  (2.4s)
moved    Utils.Notebook  (0.6s)
created  Sales.Report  (3.1s)
1 created, 1 updated, 1 moved, 0 deleted, 0 failed, 0 skipped in 6.1s
```

- An item deleted from the workspace is created again (`TARGET_MISSING`),
  and one edited or moved there is updated or moved back
  (`WORKSPACE_DRIFT`). A report goes back bound to its semantic model's ID.
- An item changed in the source since the last deployment
  (`SOURCE_CHANGED`) is left to the next deployment, which records the
  state. Without a deployment state every difference counts as drift, so
  the workspace gets the source as it is, pending deployments included:
  pass the state to leave those alone.
- Nothing is deleted: an unmanaged item is only reported. An item whose
  definition could not be compared is not touched.
- It holds the lock of the environment, as a deployment does, and never
  records the state: what goes back is what the last deployment sent.
- It returns a `DeploymentReport`; a local item that cannot be read is
  reported as failed.

## What it does not do

- `reconcile_items()` never changes the workspace; `restore_items()`
  changes only what drifted. Delete unmanaged items by hand when they
  should go.
- It reads the definitions one after the other, which takes a while on a
  large workspace.

## Reference

::: pyfabricops.helpers.reconciliation

::: pyfabricops.helpers.drift
