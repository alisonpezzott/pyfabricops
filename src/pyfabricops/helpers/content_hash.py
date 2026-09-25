"""
Content hash: a fingerprint of what deploying an item sends to Fabric.

``definition_hash`` turns an item definition, as ``pack_item_definition``
builds it, into a SHA-256 hex digest that changes only when the definition
changes in substance. Parts are taken in path order; text loses a UTF-8
byte order mark and Windows line endings, so the same commit checked out on
Windows or Linux gives the same hash; JSON files are compared by content,
not by layout or key order.

Internal for now: nothing here is exported from ``pyfabricops``.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from typing import Any

__all__ = ["canonical_part", "definition_hash"]

# Parts whose content is JSON, compared by content rather than by layout.
_JSON_SUFFIXES = (".json", ".platform", ".pbir", ".pbism")


def definition_hash(definition: Mapping[str, Any]) -> str:
    """
    Hash an item definition after putting it in canonical form.

    Args:
        definition (Mapping[str, Any]): The definition, with ``parts`` of
            ``path`` and base64 ``payload``, as ``pack_item_definition``
            returns it.

    Returns:
        str: The SHA-256 hex digest.

    Examples:
        ```python
        definition_hash(pack_item_definition('workspace/Orders.Notebook'))
        ```
    """
    digest = hashlib.sha256()
    for part in sorted(definition.get("parts", []), key=lambda p: p["path"]):
        path = part["path"]
        content = canonical_part(path, base64.b64decode(part["payload"]))
        # Path and length first, so parts cannot run into each other.
        digest.update(f"{path}\0{len(content)}\0".encode())
        digest.update(content)
    return digest.hexdigest()


def canonical_part(path: str, content: bytes) -> bytes:
    """
    Put one part of a definition in canonical form.

    Text loses a UTF-8 byte order mark and Windows line endings, and JSON
    files are serialized with sorted keys and no layout. Bytes that are not
    UTF-8 stay as they are.

    Args:
        path (str): The part's path in the definition, which tells JSON
            files apart.
        content (bytes): The part's content, decoded from base64.

    Returns:
        bytes: The canonical content.
    """
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content

    text = text.removeprefix("﻿").replace("\r\n", "\n")
    if path.endswith(_JSON_SUFFIXES):
        try:
            return _canonical_json(text)
        except ValueError:
            # Not JSON after all: compare it as text.
            return text.encode("utf-8")
    return text.encode("utf-8")


def _canonical_json(text: str) -> bytes:
    """Serialize JSON with sorted keys and no layout."""
    data = json.loads(text)
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
