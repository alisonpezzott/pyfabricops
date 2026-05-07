"""Tests for pyfabricops.utils.utils.parse_tmdl_parameters (issue #75)."""

from __future__ import annotations

import pytest

from pyfabricops.utils.utils import parse_tmdl_parameters

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_tmdl(tmp_path, content: str):
    """Write a TMDL expressions file and return its path."""
    p = tmp_path / "expressions.tmdl"
    p.write_text(content, encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# Pattern 1 – string parameters (quoted)
# ---------------------------------------------------------------------------


def test_parse_string_parameter(tmp_path) -> None:
    """String parameters enclosed in double quotes are parsed correctly."""
    content = (
        'expression p_env = "prod" meta [IsParameterQuery=true, '
        'Type="Text", IsParameterQueryRequired=true]\n'
    )
    result = parse_tmdl_parameters(_write_tmdl(tmp_path, content))
    assert result == {"p_env": "prod"}


# ---------------------------------------------------------------------------
# Pattern 4 – numeric parameters (unquoted) — the bug fix
# ---------------------------------------------------------------------------


def test_parse_integer_parameter(tmp_path) -> None:
    """Whole-number parameters without quotes are parsed correctly."""
    content = (
        "expression p_multiplicador = 12 meta [IsParameterQuery=true, "
        'Type="Number", IsParameterQueryRequired=true]\n'
    )
    result = parse_tmdl_parameters(_write_tmdl(tmp_path, content))
    assert result == {"p_multiplicador": "12"}


def test_parse_decimal_parameter(tmp_path) -> None:
    """Decimal Number parameters without quotes are parsed correctly."""
    content = (
        "expression p_taxa = 3.14 meta [IsParameterQuery=true, "
        'Type="Number", IsParameterQueryRequired=true]\n'
    )
    result = parse_tmdl_parameters(_write_tmdl(tmp_path, content))
    assert result == {"p_taxa": "3.14"}


def test_parse_negative_numeric_parameter(tmp_path) -> None:
    """Negative numeric parameters are parsed correctly."""
    content = (
        "expression p_offset = -5 meta [IsParameterQuery=true, "
        'Type="Number", IsParameterQueryRequired=true]\n'
    )
    result = parse_tmdl_parameters(_write_tmdl(tmp_path, content))
    assert result == {"p_offset": "-5"}


def test_parse_negative_decimal_parameter(tmp_path) -> None:
    """Negative decimal parameters are parsed correctly."""
    content = (
        "expression p_rate = -0.75 meta [IsParameterQuery=true, "
        'Type="Number", IsParameterQueryRequired=true]\n'
    )
    result = parse_tmdl_parameters(_write_tmdl(tmp_path, content))
    assert result == {"p_rate": "-0.75"}


# ---------------------------------------------------------------------------
# Mixed – multiple parameter types in the same file
# ---------------------------------------------------------------------------


def test_parse_mixed_string_and_numeric_parameters(tmp_path) -> None:
    """Files with both string and numeric parameters are fully parsed."""
    content = (
        'expression p_env = "prod" meta [IsParameterQuery=true, '
        'Type="Text", IsParameterQueryRequired=true]\n'
        "expression p_multiplicador = 12 meta [IsParameterQuery=true, "
        'Type="Number", IsParameterQueryRequired=true]\n'
    )
    result = parse_tmdl_parameters(_write_tmdl(tmp_path, content))
    assert result == {"p_env": "prod", "p_multiplicador": "12"}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_numeric_value_not_captured_without_meta_clause(tmp_path) -> None:
    """A bare numeric assignment without meta [IsParameterQuery is not captured."""
    # Prevents false positives from ordinary measures with numeric defaults
    content = "expression SomeCalc = 42\n"
    result = parse_tmdl_parameters(_write_tmdl(tmp_path, content))
    assert "SomeCalc" not in result


def test_empty_file_returns_empty_dict(tmp_path) -> None:
    """An empty TMDL file returns an empty dict (with a warning)."""
    result = parse_tmdl_parameters(_write_tmdl(tmp_path, ""))
    assert result == {}


def test_file_not_found_raises(tmp_path) -> None:
    """A missing file raises PyFabricOpsFileNotFoundError."""
    from pyfabricops.utils.exceptions import PyFabricOpsFileNotFoundError

    with pytest.raises(PyFabricOpsFileNotFoundError):
        parse_tmdl_parameters(str(tmp_path / "nonexistent.tmdl"))
