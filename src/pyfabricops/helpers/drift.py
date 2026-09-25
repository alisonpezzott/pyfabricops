"""
The form in which an item of the source and of the workspace are compared.

A reconciliation compares each item's definition in the source, after
staging, with the definition the workspace returns. Fabric rewrites some
parts on its own, so comparing bytes, or the content hash of what a
deployment sends, would report drift where there is none.
``comparable_parts`` starts from the canonical form of the content hash
(no byte order mark, Unix line endings, JSON by content) and also leaves
out what Fabric changes by itself, as measured against a workspace:

- the end of a text part: trailing whitespace and blank lines;
- the logical ID in ``.platform``, which Fabric assigns to each item;
- how a report's ``definition.pbir`` points to its semantic model: by the
  path of its folder in Git, by a connection in the workspace. Given the
  name of the model it points to, the reference is compared by that name;
- the ``ref`` lines Fabric adds to a semantic model's ``model.tmdl`` to
  order its tables and other objects.

Internal for now: nothing here is exported from ``pyfabricops``.
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Mapping
from typing import Any

from .content_hash import canonical_part

__all__ = ["comparable_parts", "differing_parts"]

_PLATFORM = ".platform"
_PBIR = "definition.pbir"
_MODEL_TMDL = "definition/model.tmdl"
# A line that only orders the objects of a model, such as "ref table Sales".
_TMDL_REF = re.compile(r"ref\s")
_BLANK_LINES = re.compile(r"\n{3,}")


def comparable_parts(
    definition: Mapping[str, Any],
    *,
    semantic_model: str | None = None,
) -> dict[str, bytes]:
    """
    Put each part of a definition in the form used to compare it.

    Args:
        definition (Mapping[str, Any]): The definition, with ``parts`` of
            ``path`` and base64 ``payload``: what ``pack_item_definition``
            builds from the source, or the ``definition`` the workspace
            returns.
        semantic_model (str, optional): For a report, the display name of
            the semantic model its ``definition.pbir`` points to, however it
            points to it. Without it, the reference is compared as it is.

    Returns:
        dict[str, bytes]: The comparable content of each part, by path.

    Examples:
        ```python
        source = comparable_parts(pack_item_definition(report_folder),
                                  semantic_model="Sales")
        ```
    """
    parts: dict[str, bytes] = {}
    for part in definition.get("parts", []):
        path = part["path"]
        content = canonical_part(path, base64.b64decode(part["payload"]))
        parts[path] = _comparable(path, content, semantic_model)
    return parts


def differing_parts(
    source: Mapping[str, bytes], workspace: Mapping[str, bytes]
) -> tuple[str, ...]:
    """
    Name the parts that differ between two definitions.

    A part that only one side has differs, except ``.platform``: when one
    side has none, it is left out, as not every item type returns one.

    Args:
        source (Mapping[str, bytes]): The comparable parts of the item in
            the source.
        workspace (Mapping[str, bytes]): The comparable parts of the item in
            the workspace.

    Returns:
        tuple[str, ...]: The paths of the parts that differ, in order; empty
            when the definitions match.
    """
    paths = set(source) | set(workspace)
    if _PLATFORM not in source or _PLATFORM not in workspace:
        paths.discard(_PLATFORM)
    return tuple(
        sorted(
            path for path in paths if source.get(path) != workspace.get(path)
        )
    )


def _comparable(
    path: str, content: bytes, semantic_model: str | None
) -> bytes:
    """Leave out of one canonical part what Fabric rewrites by itself."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content
    if path == _PLATFORM:
        text = _without_logical_id(text)
    elif path == _PBIR and semantic_model is not None:
        text = _pointing_to(text, semantic_model)
    elif path == _MODEL_TMDL:
        text = _without_refs(text)
    return text.rstrip().encode("utf-8")


def _without_logical_id(text: str) -> str:
    """Drop the logical ID from a canonical .platform file."""
    try:
        platform = json.loads(text)
    except ValueError:
        return text
    config = platform.get("config") if isinstance(platform, dict) else None
    if isinstance(config, dict):
        config.pop("logicalId", None)
    return _canonical_json(platform)


def _pointing_to(text: str, semantic_model: str) -> str:
    """Make a canonical definition.pbir point to its model by name."""
    try:
        pbir = json.loads(text)
    except ValueError:
        return text
    if not isinstance(pbir, dict) or "datasetReference" not in pbir:
        return text
    pbir["datasetReference"] = {"semanticModel": semantic_model}
    return _canonical_json(pbir)


def _without_refs(text: str) -> str:
    """Drop the ref lines of model.tmdl, and the blank lines they leave."""
    kept = "\n".join(
        line for line in text.split("\n") if not _TMDL_REF.match(line)
    )
    return _BLANK_LINES.sub("\n\n", kept)


def _canonical_json(data: Any) -> str:
    """Serialize JSON as the content hash does: sorted keys, no layout."""
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
