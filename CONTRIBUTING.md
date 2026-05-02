# Contributing

Thank you for taking the time to contribute! All contributions are welcome.

## Getting Started

1. **Fork** the repository and clone your fork.
2. Create a new branch from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```
3. Make your changes and **commit** following the conventions below.
4. Push your branch and open a **Pull Request**.

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
