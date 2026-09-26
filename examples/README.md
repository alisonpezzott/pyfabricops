# pyfabricops examples

Runnable examples of pyfabricops. Everything here is made up: no real
tenant, workspace or data.

> Never commit credentials, real workspace IDs or client data. Keep
> secrets in a `.env` file outside Git, or in your CI secret store.

## Before you start

- **pyfabricops 0.7.0 or later**, the first release with the deployment
  engine these examples use:

  ```bash
  pip install -U "pyfabricops>=0.7.0"
  ```

  The CI definitions install `pyfabricops>=0.7.0,<0.8.0`: before 1.0, a
  new minor version may change behavior, so move to one on purpose.

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
| `Adventure-Works-LT/` | A medallion project as Fabric Git integration writes it, deployed from a DEV workspace connected to Git to PRD: the IDs of DEV become those of PRD, the value set of PRD is made active, and a drift report can restore what changed by hand. With CI for Azure DevOps and GitHub Actions. |

Run the first two from the repository root, for example:

```bash
python examples/02-export/export_workspace.py --workspace <workspace-name> --path exported
```

`Adventure-Works-LT/` is the root of a repository of its own: its README
tells how to set it up and run it. `tests/test_examples.py` checks it: what
the deployment engine plans for it, how its script translates each
reference, and that no ID other than its made-up ones gets into this
folder.
