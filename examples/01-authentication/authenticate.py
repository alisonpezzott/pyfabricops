"""
Authenticate with a service principal and list the workspaces it sees.

The credentials come from a ``.env`` file in the working directory, or
from the environment: ``FAB_CLIENT_ID``, ``FAB_CLIENT_SECRET`` and
``FAB_TENANT_ID``. Keep the ``.env`` file out of Git.

Other ways to authenticate:

- ``pf.set_auth_provider("env", credential_type="user")``: a user, with
  ``FAB_USERNAME``, ``FAB_PASSWORD``, ``FAB_CLIENT_ID`` and
  ``FAB_TENANT_ID``.
- ``pf.set_auth_provider("oauth")``: an interactive sign-in.
- ``pf.set_auth_provider("fabric")``: inside a Fabric notebook, as the
  user running it.

Usage::

    python examples/01-authentication/authenticate.py
"""

from __future__ import annotations

from dotenv import load_dotenv

import pyfabricops as pf


def main() -> None:
    """Authenticate, then print the workspaces the identity can see."""
    load_dotenv()
    pf.set_auth_provider("env")

    workspaces = pf.list_workspaces(df=False) or []
    print(f"{len(workspaces)} workspace(s) visible:")
    for workspace in workspaces:
        print(f"  {workspace['displayName']}")


if __name__ == "__main__":
    main()
