---
description: "Use when writing, editing, or reviewing Python source files. Covers type hints, Ruff, docstrings and project structure conventions."
applyTo: "**/*.py"
---

# Python Conventions

## Type Hints

- All function and method signatures **must** have type annotations.
- Use `from __future__ import annotations` for forward references.
- Prefer `X | None` over `Optional[X]` (Python 3.10+).
- Use `TypeAlias` for complex type aliases.

## Formatting & Linting

- Code is formatted with **Ruff** (`ruff format .`). Never change formatting manually.
- Linting is enforced with `ruff check .`. Fix all warnings; never use `# noqa` without a comment explaining why.
- Max line length: defined in `pyproject.toml` (79).

## Docstrings

- Use [Google style](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings) docstrings.
- Every public function, class and method must have a docstring.
- Private helpers (`_name`) are exempt but encouraged.

```python
def parse_date(value: str) -> datetime:
    """Parse an ISO 8601 date string into a datetime object.

    Args:
        value: The date string to parse, e.g. ``"2026-01-01"``.

    Returns:
        A timezone-aware ``datetime`` in UTC.

    Raises:
        ValueError: If ``value`` is not a valid ISO 8601 string.
    """
```

## Project Structure

```
src/
  <package>/
    __init__.py
    module.py
tests/
  <package>/
    test_module.py   # mirrors src/ structure
```

- Source code lives under `src/<package>/`.
- Tests mirror the source tree under `tests/`.
- Never import from `tests/` in source code.

## Error Handling

- Raise specific exceptions (`ValueError`, `TypeError`, custom exceptions) — never bare `Exception`.
- Custom exceptions live in `exceptions.py` and inherit from a base project exception.
- Never silence exceptions with empty `except` blocks.

## Environment Variables

- Access env vars via a dedicated `config.py` using `python-dotenv`.
- Never call `os.environ` directly in business logic.
