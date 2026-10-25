# Workspace IDs

Fabric Git integration writes the items of a workspace with the IDs of that
workspace: the default lakehouse of a notebook, the OneLake path of a Direct
Lake model, the items a pipeline runs, the target of a shortcut. Sent as
they are from the repository of DEV to PRD, they would read and write DEV.

`WorkspaceIdMap` maps each ID of the source workspace to the ID of the item
of the same type and display name in the target, by its ID and by its
logical ID, and the source workspace to the target.

```python
staging = copy_to_staging("workspace", staging_dir=tempfile.mkdtemp())
ids = WorkspaceIdMap.load("Sales-DEV", "Sales-PRD", staging)
ids.translate(staging)
report = deploy_all_items("Sales-PRD", staging, start_path=staging)
```

## What is translated

| Where | What |
| :--- | :--- |
| Every file but `.platform` and those of a variable library | Each ID and logical ID of an item of the source, and the ID of the source workspace |
| `pipeline-content.json`, `notebook-content.*` | The empty GUID of `workspaceId` and `default_lakehouse_workspace_id`, which Fabric writes for "this workspace", gets the ID of the target |
| `shortcuts.metadata.json` of a lakehouse | A OneLake shortcut to an item of the source gets the logical ID of the item in the target, or its ID with the ID of the target workspace when it has none. A shortcut to another workspace stays |

A variable library is left as it is: its value sets hold the values of each
environment.

## Items the target lacks yet

An ID whose item the target lacks stays as it is. `references()` tells,
item by item, what still refers to the source:

```python
found = ids.references(("DataPipeline", "orchestrator"), folder)
found.missing            # the items of the source the target lacks
found.source_workspace   # whether it refers to the source workspace
found.ok                 # neither
```

A run can then deploy first the items the others refer to, call
`reload_target()` to list the target again, and `translate()` the staging
copy again. The shortcuts are translated from what they were the first
time, so a shortcut waiting for its lakehouse gets it on the next pass. An
item still referring to the source must not be sent: it would read and
write the source workspace. The
[template repository](https://github.com/alisonpezzott/pyfabricops-template) does this, one item type at a time.

::: pyfabricops.helpers.workspace_ids
