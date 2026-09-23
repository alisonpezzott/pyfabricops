"""Tests for the definition hash in pyfabricops.helpers.content_hash."""

from __future__ import annotations

import base64

from pyfabricops.helpers.content_hash import definition_hash


def _definition(*parts: tuple[str, bytes]) -> dict[str, list[dict[str, str]]]:
    """A definition shaped like pack_item_definition's, from raw parts."""
    return {
        "parts": [
            {
                "path": path,
                "payload": base64.b64encode(content).decode("ascii"),
                "payloadType": "InlineBase64",
            }
            for path, content in parts
        ]
    }


def _hash(*parts: tuple[str, bytes]) -> str:
    return definition_hash(_definition(*parts))


def test_the_same_definition_gives_the_same_hash() -> None:
    """A SHA-256 hex digest, stable for the same content."""
    digest = _hash(("notebook-content.py", b"print(1)\n"))

    assert digest == _hash(("notebook-content.py", b"print(1)\n"))
    assert len(digest) == 64


def test_a_changed_definition_gives_another_hash() -> None:
    """Any change of content is a change."""
    assert _hash(("a.py", b"print(1)\n")) != _hash(("a.py", b"print(2)\n"))


def test_file_paths_are_part_of_the_hash() -> None:
    """Moving content to another file changes the definition."""
    assert _hash(("a.py", b"x")) != _hash(("b.py", b"x"))


def test_the_order_of_the_parts_does_not_matter() -> None:
    """Parts are taken in path order, whatever order they came in."""
    assert _hash(("a.py", b"a"), ("b.py", b"b")) == _hash(
        ("b.py", b"b"), ("a.py", b"a")
    )


def test_line_endings_and_byte_order_marks_do_not_matter() -> None:
    """A Windows checkout and a Linux one give the same hash."""
    assert _hash(("a.py", b"x = 1\ny = 2\n")) == _hash(
        ("a.py", b"\xef\xbb\xbfx = 1\r\ny = 2\r\n")
    )


def test_json_layout_and_key_order_do_not_matter() -> None:
    """JSON files are compared by content."""
    compact = b'{"metadata":{"type":"Notebook","displayName":"Orders"}}'
    indented = (
        b'{\n  "metadata": {\n    "displayName": "Orders",\n'
        b'    "type": "Notebook"\n  }\n}\n'
    )

    assert _hash((".platform", compact)) == _hash((".platform", indented))


def test_layout_still_matters_outside_json() -> None:
    """Whitespace in code is content."""
    assert _hash(("a.py", b"if x:\n  y\n")) != _hash(
        ("a.py", b"if x:\n    y\n")
    )


def test_a_json_file_that_does_not_parse_is_compared_as_text() -> None:
    """Broken JSON does not break the hash; its text still counts."""
    assert _hash(("report.json", b"{not json")) == _hash(
        ("report.json", b"{not json")
    )
    assert _hash(("report.json", b"{not json")) != _hash(
        ("report.json", b"{not  json")
    )


def test_binary_parts_are_compared_byte_for_byte() -> None:
    """Bytes that are not UTF-8 text are never normalized."""
    image = b"\x89PNG\r\n\x1a\n\x00\xff"

    assert _hash(("logo.png", image)) != _hash(
        ("logo.png", image.replace(b"\r\n", b"\n"))
    )
