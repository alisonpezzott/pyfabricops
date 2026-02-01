# Authentication Methods Guide

This guide explains the three authentication methods available in pyfabricops and when to use each one.

## Overview

pyfabricops supports three authentication methods:

1. **`env`** - Environment variables (Service Principal or User credentials)
2. **`oauth`** - Interactive browser authentication
3. **`fabric`** - Fabric notebook authenticated user (NEW!)

## Method 1: Environment Variables (`env`)

**Use when:** Running in CI/CD pipelines, GitHub Actions, Azure DevOps, or when you have service principal credentials.

**Setup:**

Create a `.env` file or set environment variables:

```env
FAB_CLIENT_ID=your_client_id_here
FAB_CLIENT_SECRET=your_client_secret_here
FAB_TENANT_ID=your_tenant_id_here
FAB_USERNAME=your_username_here    # Optional: for user-based auth
FAB_PASSWORD=your_password_here    # Optional: for user-based auth
```

**Usage:**

```python
import pyfabricops as pf

# This is the default, but you can set it explicitly
pf.set_auth_provider("env")

# Now use the library
workspaces = pf.list_workspaces()
```

**Pros:**
- ✅ Works everywhere (local, CI/CD, containers)
- ✅ Service principal support
- ✅ Secure credential management
- ✅ No user interaction required

**Cons:**
- ❌ Requires credential management
- ❌ Need to configure environment variables

---

## Method 2: OAuth Interactive (`oauth`)

**Use when:** Running locally in VSCode, Jupyter notebooks (outside Fabric), or any interactive environment.

**Setup:**

No setup required, but you need Azure AD permissions.

**Usage:**

```python
import pyfabricops as pf

pf.set_auth_provider("oauth")

# First call will open a browser for authentication
workspaces = pf.list_workspaces()
```

**Pros:**
- ✅ Easy to use - no credentials to manage
- ✅ Uses your Azure AD account
- ✅ Token is cached for reuse
- ✅ Great for development

**Cons:**
- ❌ Requires browser access
- ❌ Not suitable for automation
- ❌ Doesn't work in headless environments

---

## Method 3: Fabric Notebook (`fabric`) 🆕

**Use when:** Running inside Microsoft Fabric notebooks where the user is already authenticated.

**Setup:**

No setup required! The authenticated user's token is automatically retrieved.

**Usage:**

```python
import pyfabricops as pf

pf.set_auth_provider("fabric")

# Uses the authenticated user's token automatically
workspaces = pf.list_workspaces()
```

**How it works:**

Under the hood, this method uses:
```python
from notebookutils import credentials
access_token = credentials.getToken('pbi')
```

**Pros:**
- ✅ Zero configuration needed
- ✅ No browser popup
- ✅ Uses logged-in user's permissions
- ✅ Perfect for Fabric notebooks
- ✅ Token automatically cached and refreshed

**Cons:**
- ❌ Only works inside Microsoft Fabric notebooks
- ❌ Will fail outside Fabric environment

---

## Comparison Table

| Feature | `env` | `oauth` | `fabric` |
|---------|-------|---------|----------|
| Works in Fabric notebooks | ✅ | ✅ | ✅ |
| Works in VSCode | ✅ | ✅ | ❌ |
| Works in CI/CD | ✅ | ❌ | ❌ |
| Requires credentials | ✅ | ❌ | ❌ |
| Requires browser | ❌ | ✅ | ❌ |
| Service Principal support | ✅ | ❌ | ❌ |
| User token | Optional | ✅ | ✅ |
| Auto-refresh | ✅ | ✅ | ✅ |

---

## Examples

### Example 1: Local Development (VSCode)

```python
import pyfabricops as pf

# Use OAuth for easy local development
pf.set_auth_provider("oauth")
pf.setup_logging(level='info')

workspaces = pf.list_workspaces()
print(f"Found {len(workspaces)} workspaces")
```

### Example 2: Fabric Notebook

```python
import pyfabricops as pf

# Use fabric method - no credentials needed!
pf.set_auth_provider("fabric")

# Get current workspace info
workspace = pf.get_workspace("my-workspace-name")
print(workspace)

# List items
items = pf.list_items(workspace['id'])
for item in items:
    print(f"- {item['displayName']} ({item['type']})")
```

### Example 3: CI/CD Pipeline

```python
import pyfabricops as pf
import os

# Use env method with service principal
pf.set_auth_provider("env")

# Credentials come from environment variables
# These should be set in GitHub Secrets or Azure DevOps variables
workspaces = pf.list_workspaces()

# Deploy items
pf.deploy_item("my-workspace", "my-item", source_path="./artifacts")
```

---

## Switching Between Methods

You can switch authentication methods at runtime:

```python
import pyfabricops as pf

# Start with OAuth
pf.set_auth_provider("oauth")
workspaces = pf.list_workspaces()

# Switch to env for deployment
pf.set_auth_provider("env")
pf.deploy_item("workspace", "item", "./path")

# Switch to fabric if in Fabric notebook
try:
    pf.set_auth_provider("fabric")
    print("Running in Fabric!")
except Exception:
    print("Not in Fabric, using current method")
```

---

## Troubleshooting

### Error: "notebookutils is not available"

This means you're trying to use `fabric` authentication outside of a Microsoft Fabric notebook.

**Solution:** Use `oauth` or `env` instead:
```python
pf.set_auth_provider("oauth")  # or "env"
```

### Error: "Failed to retrieve token"

For `env` method, check that all required environment variables are set:
```python
import os
print("Client ID:", os.getenv("FAB_CLIENT_ID"))
print("Tenant ID:", os.getenv("FAB_TENANT_ID"))
```

For `oauth` method, ensure you have permissions to authenticate.

### Token Cache Issues

If you're having authentication issues, try clearing the token cache:
```python
pf.clear_token_cache()
pf.set_auth_provider("oauth")  # Re-authenticate
```

---

## Best Practices

1. **Use `fabric` in Fabric notebooks** - It's the simplest and most secure option when available
2. **Use `oauth` for local development** - Easy and no credential management
3. **Use `env` for automation** - Required for CI/CD and production deployments
4. **Never commit credentials** - Always use environment variables or secrets management
5. **Clear cache when switching identities** - Use `pf.clear_token_cache()` when needed

---

## Security Notes

- Tokens are cached in a temporary file: `pf_token_cache.json`
- Tokens automatically expire and are refreshed
- Service principal credentials should be stored securely (Key Vault, GitHub Secrets, etc.)
- The `fabric` method is the most secure for notebooks as it uses the platform's authentication
