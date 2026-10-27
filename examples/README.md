# pyfabricops examples

Runnable examples of pyfabricops. Everything here is made up: no real
tenant, workspace or data.

> Never commit credentials, real workspace IDs or client data. Keep
> secrets in a `.env` file outside Git, or in your CI secret store.

## Before you start

- **pyfabricops 0.10.0 or later**, which deploys eventhouses, KQL
  databases, eventstreams, ontologies and data agents, and keeps the
  deployment state on a branch of the repository, as the template does:

  ```bash
  pip install -U "pyfabricops>=0.10.0"
  ```

  The CI definitions of the template install `pyfabricops>=0.10.0,<0.11.0`:
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

Run them from the repository root, for example:

```bash
python examples/02-export/export_workspace.py --workspace <workspace-name> --path exported
```

`tests/test_examples.py` checks that no ID other than the made-up ones gets
into this folder.

## Template repository

To deploy a workspace from CI, start from
[pyfabricops-template](https://github.com/alisonpezzott/pyfabricops-template): a repository with the script and the
pipelines, for GitHub Actions and Azure DevOps, that deploy the items of a
Fabric workspace to one workspace per environment. It used to be
`examples/03-template-repo`; its README tells how to set it up and run it.
