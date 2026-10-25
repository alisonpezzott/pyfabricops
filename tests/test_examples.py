"""Tests for the examples folder: no ID of a real workspace gets into it."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
_GUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
_EMPTY = "00000000-0000-0000-0000-000000000000"
# The empty GUID, which Fabric writes for the workspace of an item of the
# same workspace, and the IDs made up for the examples.
_MADE_UP = re.compile(rf"{_EMPTY}|00000000-0000-4000-8000-\d{{12}}")

# The source distribution leaves the examples out.
pytestmark = pytest.mark.skipif(
    not _EXAMPLES.is_dir(), reason="examples/ is not in this copy"
)


def test_the_examples_hold_no_real_id() -> None:
    """Only the IDs made up for the examples, never one from a workspace."""
    found = {
        match.lower()
        for path in _EXAMPLES.rglob("*")
        # Credentials of a local run, which Git ignores.
        if path.is_file() and path.name != ".env"
        for match in _GUID.findall(
            path.read_text(encoding="utf-8", errors="ignore")
        )
    }

    assert {guid for guid in found if not _MADE_UP.fullmatch(guid)} == set()
