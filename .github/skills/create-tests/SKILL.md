---
name: create-tests
description: "Generate pytest tests for Python code. Use when asked to write, add or scaffold tests for a function, class or module. Covers happy path, edge cases, exceptions and parametrize patterns."
argument-hint: "Source file or function to test"
---

# Create Tests

Generates idiomatic **pytest** test files for Python source code.

## When to Use

- Writing tests for a new function or class.
- Adding missing coverage to an existing module.
- Scaffolding a test file from scratch.

## Procedure

1. **Read** the target source file to understand the public API and types.
2. **Check** `tests/` for existing `conftest.py`, fixtures, and naming patterns.
3. **Consult** [pytest patterns reference](./references/pytest-patterns.md) for idiomatic examples.
4. **Determine** test file path: mirror source under `tests/`
   - `src/pkg/module.py` → `tests/pkg/test_module.py`
5. **Write** tests covering:
   - Happy path (expected inputs/outputs)
   - Edge cases (empty, boundary, large values)
   - Error scenarios (`pytest.raises` with `match=`)
   - Multiple inputs (`pytest.mark.parametrize`)
6. **Mock** all external dependencies (HTTP, DB, file I/O) with `unittest.mock` (stdlib) or `pytest-mock` if already available.
7. **Report** what was created and any coverage gaps.

## Requirements

- Type-annotate all test functions: `-> None`.
- Each test has a one-line docstring.
- Test names follow `test_<function>_<scenario>`.
- No repeated setup code — use fixtures or `parametrize`.
