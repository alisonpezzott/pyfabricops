---
description: "Generate pytest tests for the selected or specified Python code. Covers happy path, edge cases and error scenarios."
agent: agent
argument-hint: "Function or class to test (leave blank to use editor selection)"
---

Generate comprehensive **pytest** test cases for the following code:

```python
#file
```

### Requirements

- Mirror the source file path: `src/utils/parser.py` → `tests/utils/test_parser.py`.
- Use `pytest` fixtures for shared setup — no repeated boilerplate.
- Cover:
  - **Happy path** — expected inputs and outputs.
  - **Edge cases** — empty inputs, boundary values, large inputs.
  - **Error scenarios** — invalid types, missing required args, expected exceptions.
- Use `pytest.raises` to assert exceptions with specific messages where applicable.
- Use `pytest.mark.parametrize` for multiple input/output combinations.
- Mock external dependencies (`httpx`, database calls, file I/O) with `pytest-mock` or `unittest.mock`.
- Test names must follow the pattern `test_<function>_<scenario>`.
- Add a brief docstring to each test explaining what it verifies.

### Example output structure

```python
import pytest
from src.utils.parser import parse_date


def test_parse_date_valid_iso_string() -> None:
    """parse_date returns a UTC datetime for a valid ISO 8601 string."""
    ...


def test_parse_date_invalid_string_raises_value_error() -> None:
    """parse_date raises ValueError for a non-ISO string."""
    with pytest.raises(ValueError, match="invalid"):
        parse_date("not-a-date")


@pytest.mark.parametrize("value", ["", "  ", None])
def test_parse_date_empty_input_raises(value: str | None) -> None:
    """parse_date raises ValueError for empty or None input."""
    with pytest.raises(ValueError):
        parse_date(value)
```
