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
- the `ref` lines Fabric adds to `model.tmdl` to order a model's tables.

A difference names the parts of the definition that differ.

## With a deployment state

The deployment state records a hash of what the last successful deployment
sent. With it, a difference tells where it comes from:

- the source is as it was deployed, so the workspace changed:
  `WORKSPACE_DRIFT`;
- the source changed since: `SOURCE_CHANGED`, which the next selective
  deployment will send.

It tells the same of a folder: moved in the workspace, or in the source.

## What it does not do

- It never changes the workspace. Deploy to bring back what differs, and
  delete unmanaged items by hand when they should go.
- It reads the definitions one after the other, which takes a while on a
  large workspace.

## Reference

::: pyfabricops.helpers.reconciliation

::: pyfabricops.helpers.drift
