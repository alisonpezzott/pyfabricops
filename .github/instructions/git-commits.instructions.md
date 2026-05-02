---
description: "Use when writing git commit messages, PR titles, or CHANGELOG entries. Enforces Conventional Commits format."
---

# Git Commit Conventions

Follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).

## Format

```
<type>(optional scope): <short description>

[optional body]

[optional footer(s)]
```

## Types

| Type | When to use |
|------|-------------|
| `feat` | A new feature visible to the user |
| `fix` | A bug fix |
| `docs` | Documentation only |
| `style` | Formatting, whitespace — no logic change |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `test` | Adding or correcting tests |
| `chore` | Maintenance: deps, CI, build config |
| `perf` | Performance improvement |
| `ci` | CI/CD configuration changes |

## Rules

- Subject line: **imperative mood**, lowercase, no period, max 72 chars.
- Body: explain *why*, not *what*. Wrap at 72 chars.
- Breaking changes: add `!` after type/scope and `BREAKING CHANGE:` footer.
- Reference issues in the footer: `Closes #42`, `Fixes #7`.

## Examples

```
feat(auth): add JWT refresh token support

Refresh tokens are stored in an HttpOnly cookie to prevent XSS.
Access tokens expire after 15 minutes.

Closes #12
```

```
fix(api): handle empty payload in POST /items

Previously raised an unhandled KeyError when the request body
was missing the "name" field.

Fixes #34
```

```
feat!: drop support for Python 3.10

BREAKING CHANGE: minimum supported version is now Python 3.11.
```
