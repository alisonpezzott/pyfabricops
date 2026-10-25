# pyfabricops examples

Runnable examples of pyfabricops. Everything here is made up: no real
tenant, workspace or data.

> Never commit credentials, real workspace IDs or client data. Keep
> secrets in a `.env` file outside Git, or in your CI secret store.

## Before you start

- **pyfabricops 0.8.1 or later**, which keeps the deployment state on a
  branch of the repository from the folder of the items, as the template
  does:

  ```bash
  pip install -U "pyfabricops>=0.8.1"
  ```

  The CI definitions of the template install `pyfabricops>=0.8.1,<0.9.0`:
  before 1.0, a new minor version may change behavior, so move to one on
  purpose.

- **A service principal** that can use the Fabric APIs, which is a tenant
  setting, with a role on the workspaces it works on.
- **A `.env` file** with its credentials, kept out of Git:

  ```text
  FAB_CLIENT_ID=<client-id>
  FAB_CLIENT_SECRET=<client-secret>
  FAB_TENANT_ID=<tenant-id>
  ```

## The examples

| Folder | What it shows |
| :--- | :--- |
| `01-authentication/` | Authenticating with a service principal from `.env`, and the other ways to sign in. |
| `02-export/` | Exporting a workspace to a folder, to start a repository from it. |
| `03-template-repo/` | A template repository: the script and the CI definitions, for Azure DevOps and GitHub Actions, that deploy the items of a Fabric workspace to one workspace per environment. With DEV connected to Git, every item type pyfabricops deploys goes to PRD, with the IDs of DEV mapped to those of PRD; with no workspace connected, the repository is the source of every environment, for variable libraries, semantic models and reports. A file per environment gives its workspace, value set and model parameters, and each workspace may be on a Fabric capacity or Pro. |

Run the first two from the repository root, for example:

```bash
python examples/02-export/export_workspace.py --workspace <workspace-name> --path exported
```

`03-template-repo/` is the root of a repository of its own: copy it into a
new repository, and its README tells how to set it up and run it.
`tests/test_examples.py` checks that no ID other than the made-up ones gets
into this folder.
