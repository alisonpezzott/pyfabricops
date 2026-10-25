# Contributing

Thank you for taking the time to contribute! All contributions are welcome.

## Getting Started

1. **Fork** the repository and clone your fork.
2. Create a new branch from `develop`:
   ```bash
   git checkout develop
   git checkout -b feat/your-feature-name
   ```
3. Make your changes and **commit** following the conventions below.
4. Push your branch and open a **Pull Request** to `develop`. `main` takes
   the releases.

## Development Setup

```bash
# Install uv (if not already installed)
pip install uv

# Sync dev dependencies (creates .venv automatically)
uv sync --group dev

# Copy environment file
cp .env.example .env
```

## Code Style

This project uses the following tools (configured in `pyproject.toml`):

| Tool | Purpose |
|------|---------|
| [Ruff](https://github.com/astral-sh/ruff) | Linting & formatting |

Run checks before committing:

```bash
ruff check . --fix
ruff format .
```

## Tests

```bash
uv run pytest -m "not live"
```

runs what CI runs on every push and pull request to `develop` and `main`:
the unit tests, with the Fabric API mocked, and the offline runs of the
end-to-end scripts. `uv run pytest -m live` calls the real API with the
credentials of `.env`.

### End-to-end, against a real workspace

`tests/e2e/` holds two scripts that run what a deployment pipeline runs
against a sandbox workspace, and delete what they created at the end. The
unit tests check the library against the API as the tests mock it; these
check that the API behaves that way.

| Script | What it runs |
| :--- | :--- |
| `e2e_deployment.py` | The deployment engine: a bootstrap without a state, selective deployments, folders, a failed run and its resume from the journal, deletions, dependencies, report binding, reconcile and restore. |
| `e2e_state.py` | The remote state backends: `OneLakeStateBackend`, or `GitStateBackend` with `--git-remote`, with refused saves, held, expired and forced locks, and a deployment whose state and journal are remote. |

`test_e2e_deployment.py` and `test_e2e_state.py` run the same steps
against an in-memory workspace, so a change to the engine that breaks a
script fails in CI. The scripts themselves need:

- a service principal in an `.env` file (`FAB_CLIENT_ID`,
  `FAB_CLIENT_SECRET`, `FAB_TENANT_ID`), in a tenant that lets service
  principals use Fabric APIs;
- a sandbox workspace on a Fabric capacity, with the service principal as
  Contributor or above, holding nothing but what the scripts create;
- git on `PATH`, and for `--git-remote` a private repository: the lock
  records the user and host that took it.

```bash
uv run --frozen python tests/e2e/e2e_deployment.py --workspace pyfabricops-e2e --env-file .env
uv run --frozen python tests/e2e/e2e_state.py --workspace pyfabricops-e2e --env-file .env
```

Each runs only with an explicit workspace (`--workspace` or
`PYFABRICOPS_E2E_WORKSPACE`), so a CI job with Fabric credentials never
starts one by accident. Use a sandbox tenant or workspace, never one that
holds client data.

## Before a release

1. CI is green on `develop`.
2. When the release changes the deployment engine or a state backend, run
   both end-to-end scripts against the sandbox workspace.
3. Run [pyfabricops-template](https://github.com/alisonpezzott/pyfabricops-template)
   against the release candidate, installed from its branch
   (`pip install "pyfabricops @ git+https://github.com/alisonpezzott/pyfabricops@<branch>"`):
   once from a DEV workspace connected to Git to PRD, and once with a Pro
   workspace.
4. `CHANGELOG.md` has the release under its version and date, and
   `pyproject.toml` and `src/pyfabricops/_version.py` carry that version.
   The release tag is `v<version>`: the release workflow checks it.

## Commit Conventions

This project follows [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(optional scope): <short description>

[optional body]

[optional footer]
```

Common types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`.

**Examples:**

```
feat(auth): add JWT token refresh
fix(api): handle empty response from upstream
docs: update installation instructions
```

## Branch Naming

| Pattern          | When to use              |
|------------------|--------------------------|
| `feat/<name>`    | New features             |
| `fix/<name>`     | Bug fixes                |
| `docs/<name>`    | Documentation only       |
| `chore/<name>`   | Maintenance, dependencies|
| `refactor/<name>`| Code refactoring         |

## Pull Requests

- Keep PRs focused — one feature or fix per PR.
- Fill out the PR template completely.
- Ensure all checks pass before requesting a review.
- Squash commits if the history is noisy.

## Reporting Issues

Use the issue templates provided and include as much detail as possible.

## Code of Conduct

By participating in this project, you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).
