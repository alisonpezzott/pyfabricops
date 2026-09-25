# Deletions

`deploy_all_items()` deletes from the workspace an item deleted from Git,
and only when the run allows it with `allow_deletions=True`. Without it,
the deletion blocks the run, so it is never missed.

```python
arguments = dict(
    start_path=staging,
    repository_path="workspace",
    state_backend=LocalJsonStateBackend(".deploy-state"),
    environment="PRD",
    allow_deletions=True,
)
print(plan_all_items("Sales-PRD", staging, **arguments).describe())
report = deploy_all_items("Sales-PRD", staging, **arguments)
```

`plan_all_items()` takes the flag too, so the plan shows what the
deployment would delete.

## What counts as a deletion

Only an item folder deleted in Git between the baseline (the
`baseline_commit` given, or the last successful deployment the state
records) and HEAD. The workspace item is the one with the item's type and
display name, as they were at the baseline commit.

```text
DELETE   Old.Notebook  ITEM_DELETED
```

Nothing else deletes an item:

- A run without a baseline, which deploys every item, deletes nothing.
- An item type left out of `item_types` loses nothing.
- An item the source still defines, as when its folder moved, needs
  nothing: `NOOP ... Still defined at Archive/Old.Notebook.` The whole
  source counts, not only what the run selects.
- An item the workspace no longer has needs nothing either.
- `reconcile_items()` reports the items only the workspace has, and never
  deletes them.

## Without `allow_deletions`

```text
BLOCKED  Old.Notebook  ITEM_DELETED: Deletions are not allowed in this run: pass allow_deletions=True, or delete it from the workspace by hand.
```

The item is reported as failed, so the deployment state does not move and
the next run finds the deletion again. Once the item is deleted by hand, it
needs nothing.

## What still refers to it

A deletion is blocked while an item that stays in the source refers to the
item, even with `allow_deletions`:

```text
BLOCKED  Sales.SemanticModel  ITEM_DELETED: Still referred to by Sales.Report (definition.pbir byPath).
```

Two kinds of reference count:

- The references the engine reads to order a deployment (see
  [Dependencies](dependencies.md)): a report's semantic model, and a
  notebook's default lakehouse, environment and `%run`. They are checked
  against the item as it was at the baseline commit, by its folder,
  display name and logical ID.
- The item's ID in the workspace, in any file of an item that stays; for a
  lakehouse, the ID of its SQL analytics endpoint too. That finds a Direct
  Lake semantic model on the lakehouse, or a pipeline that runs a notebook:
  `Still referred to by Sales.SemanticModel (the ID of its SQL analytics
  endpoint, in definition/expressions.tmdl).`

Delete the item that refers to it in the same commit, or point it
elsewhere. Items deleted together do not block each other. No item is
deleted because another one is.

What is not checked: items only the workspace has, such as one created by
hand; a reference by name inside code, such as a notebook that reads a
lakehouse by its path; and an ID that is still a placeholder in the files
the run reads, such as one replaced only before a later run.

## How the deletions run

- Last, after every other item, and by type in the reverse of
  `DEPLOY_ORDER`: reports first, lakehouses near the end, so an item goes
  before what it refers to.
- Only when every item before them succeeded. Otherwise they are skipped
  (`Not deleted: an item before it failed or was skipped.`); the state does
  not move, so the next run plans them again. A deletion that fails or is
  blocked holds back the ones after it in the same way.
- An item someone deleted since the workspace was listed counts as
  deleted.

The report says `deleted` for each (`report.summary()["deleted"]`), and the
state forgets a deleted item once the whole run succeeds.

## What Fabric keeps

The engine deletes an item as the Fabric API does by default. When the item
type supports it, Fabric moves the item to the workspace recycle bin, where
it can be restored for the retention period the tenant admin sets: 3 days
by default, up to 90, or none when item recovery is off. Lakehouses,
warehouses, notebooks, data pipelines, environments, variable libraries and
copy jobs are among those types; semantic models, reports and dataflows are
not, so Fabric deletes them for good. Their definition is still in Git at
the baseline commit, but a recreated item gets a new ID, and an import
model needs a refresh. See Microsoft's
[retention and recovery](https://learn.microsoft.com/en-us/fabric/admin/retention-recovery)
page for the current list, and
[recover or permanently delete items](https://learn.microsoft.com/en-us/fabric/admin/item-recovery)
to restore one.

pyfabricops never deletes an item permanently, and never deletes a
workspace folder, even one left empty.
