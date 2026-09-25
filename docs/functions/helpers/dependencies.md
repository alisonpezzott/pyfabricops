# Dependencies

With `resolve_dependencies=True`, the default, `plan_all_items()` and
`deploy_all_items()` read what the selected items refer to, and deploy each
item after what it needs, even in a run that deploys only what changed.

## References read

| Item | Needs | Read from |
| :--- | :--- | :--- |
| Report | SemanticModel | `definition.pbir`: the folder in `datasetReference.byPath`, or the `initial catalog` of `byConnection` |
| Notebook | Lakehouse | The default lakehouse: by logical ID, as Fabric writes a lakehouse of the same workspace, or else by `default_lakehouse_name` |
| Notebook | Environment | The attached environment, by logical ID |
| Notebook | Notebook | `%run <notebook>` (`%run -b` runs a script of the notebook's resources, not a notebook) |

A reference to something outside the source, such as a semantic model of
another workspace, is left out: it is neither deployed nor blocking.

## What the plan does with them

Say `Orders.Notebook` changed, and its default lakehouse is
`Bronze.Lakehouse`, which did not.

The workspace has the lakehouse: it is checked, not deployed.

```text
NOOP     Bronze.Lakehouse  DEPENDENCY_REQUIRED: Required by Orders.Notebook (notebook default lakehouse); already in the workspace.
UPDATE   Orders.Notebook  SOURCE_CHANGED
```

The workspace lacks it, as when someone deleted it by hand: it is created
first.

```text
CREATE   Bronze.Lakehouse  DEPENDENCY_REQUIRED: Required by Orders.Notebook (notebook default lakehouse) and missing from the workspace.
UPDATE   Orders.Notebook  SOURCE_CHANGED
```

It cannot be created, because the run deploys only
`item_types=["Notebook"]` or because the source does not define it: the
notebook is blocked.

```text
BLOCKED  Orders.Notebook  SOURCE_CHANGED: Needs Bronze.Lakehouse, which is missing from the workspace and not among the item types of this run.
```

An item is blocked too when a reference of its definition is broken, such
as a report whose `byPath` folder is missing or holds no semantic model, or
when it is part of a dependency cycle, such as two notebooks that `%run`
each other. What needs a blocked item is blocked in turn. A blocked item is
reported as failed, so the deployment state does not move.

## When an item fails

The plan lists in each action's `needs` the items of the plan it needs.
When one of them fails to deploy, the item is not sent without it: it is
reported as skipped, and so is what needs a skipped item.

```python
report = deploy_all_items("Sales-PRD", "stg/workspace", ...)
[(r.display_name, r.action, r.error) for r in report.results]
# [('Bronze', 'failed', 'Create failed with 400: ...'),
#  ('Orders', 'skipped', 'Needs Bronze.Lakehouse, which failed.')]
```

The rest of the run goes on, and the deployment state does not move, so
the next run tries both again.

## Data pipelines

A data pipeline refers to notebooks, pipelines, dataflows and other items
by ID, which only the workspace can resolve. After staging, every ID that
points to the target workspace, nested activities included, is checked
against it. An ID the workspace lacks, or a value that is no ID, such as a
placeholder left unreplaced, gives a warning in the plan and in the log:

```text
UPDATE   Load.DataPipeline  SOURCE_CHANGED: Warning: Activity 'Run Orders' refers to notebook '#{orders_notebook_id}#', which is not an ID (a placeholder left unreplaced?).
```

The pipeline is still deployed: an item created in the same run gets its ID
only when it is created. References to other workspaces are not checked.

## Turning it off

`resolve_dependencies=False` deploys the selected items in `DEPLOY_ORDER`
without reading their references, as before: no item needs another, so a
failure skips nothing.

## Reference

::: pyfabricops.helpers.dependencies

::: pyfabricops.helpers.dependency_graph
