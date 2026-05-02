# pytest Patterns Reference

## Basic test

```python
def test_add_two_positive_numbers() -> None:
    """add returns the correct sum of two positive integers."""
    assert add(2, 3) == 5
```

## Parametrize

```python
@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (1, 2, 3),
        (0, 0, 0),
        (-1, 1, 0),
    ],
)
def test_add_parametrized(a: int, b: int, expected: int) -> None:
    """add returns the correct sum for various input pairs."""
    assert add(a, b) == expected
```

## Exception assertion

```python
def test_divide_by_zero_raises_value_error() -> None:
    """divide raises ValueError when divisor is zero."""
    with pytest.raises(ValueError, match="division by zero"):
        divide(10, 0)
```

## Fixture

```python
@pytest.fixture()
def sample_user() -> User:
    return User(id=1, name="Alice", email="alice@example.com")


def test_user_display_name(sample_user: User) -> None:
    """display_name returns the user's full name."""
    assert sample_user.display_name() == "Alice"
```

## Mocking external I/O (pytest-mock)

```python
def test_fetch_user_calls_api(mocker: MockerFixture) -> None:
    """fetch_user calls the remote API with the correct user ID."""
    mock_get = mocker.patch("myapp.client.httpx.get")
    mock_get.return_value.json.return_value = {"id": 1, "name": "Alice"}

    result = fetch_user(1)

    mock_get.assert_called_once_with("https://api.example.com/users/1")
    assert result.name == "Alice"
```

## Mocking file I/O

```python
def test_read_config_parses_file(tmp_path: Path) -> None:
    """read_config returns parsed values from a TOML file."""
    config_file = tmp_path / "config.toml"
    config_file.write_text('[app]\nname = "test"\n')

    config = read_config(config_file)

    assert config.app_name == "test"
```

## Async tests

```python
@pytest.mark.asyncio
async def test_async_fetch_returns_data() -> None:
    """async_fetch returns the expected payload."""
    result = await async_fetch("https://example.com/data")
    assert result is not None
```

## Markers

```python
@pytest.mark.slow
def test_heavy_computation() -> None: ...

@pytest.mark.integration
def test_database_insert() -> None: ...
```

Register custom markers in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "slow: marks tests as slow (deselect with '-m not slow')",
    "integration: marks tests that require external services",
]
```
