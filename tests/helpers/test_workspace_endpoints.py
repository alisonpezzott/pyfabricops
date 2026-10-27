"""Tests for the endpoints WorkspaceIdMap maps, and publish_data_agent."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pyfabricops.api.api import ApiResult
from pyfabricops.helpers.workspace_ids import WorkspaceIdMap, _fetch_endpoints
from pyfabricops.items.data_agents import publish_data_agent
from pyfabricops.utils.exceptions import RequestError, ResourceNotFoundError

SOURCE = "00000000-0000-4000-8000-0000000000a1"
TARGET = "00000000-0000-4000-8000-0000000000b1"
DEV_QUERY = "https://trd-dev.z1.kusto.fabric.microsoft.com"
DEV_INGEST = "https://ingest-trd-dev.z1.kusto.fabric.microsoft.com"
PRD_QUERY = "https://trd-prd.z1.kusto.fabric.microsoft.com"
PRD_INGEST = "https://ingest-trd-prd.z1.kusto.fabric.microsoft.com"
DEV_SQL = "dev-host.datawarehouse.fabric.microsoft.com"
PRD_SQL = "prd-host.datawarehouse.fabric.microsoft.com"


def _item(item_type: str, name: str, item_id: str) -> dict[str, str]:
    return {"type": item_type, "displayName": name, "id": item_id}


class FakeReader:
    """Endpoints by item ID, recording what is read."""

    def __init__(self, endpoints: dict[str, Sequence[str]]) -> None:
        self.endpoints = endpoints
        self.read: list[str] = []

    def __call__(
        self, workspace_id: str, item: Mapping[str, Any]
    ) -> Sequence[str]:
        self.read.append(str(item["id"]))
        return self.endpoints[str(item["id"])]


def _map(
    reader: FakeReader,
    source: list[dict[str, str]],
    target: list[dict[str, str]],
) -> WorkspaceIdMap:
    return WorkspaceIdMap(
        SOURCE,
        TARGET,
        source_items=source,
        target_items=target,
        endpoint_reader=reader,
    )


def test_the_uris_of_an_eventhouse_map_to_its_namesake(tmp_path: Path) -> None:
    reader = FakeReader(
        {"eh-dev": (DEV_QUERY, DEV_INGEST), "eh-prd": (PRD_QUERY, PRD_INGEST)}
    )
    ids = _map(
        reader,
        [_item("Eventhouse", "Telemetry", "eh-dev")],
        [_item("Eventhouse", "Telemetry", "eh-prd")],
    )
    queryset = tmp_path / "Logs.KQLDatabase" / "EmbeddedRealTimeQueryset.json"
    queryset.parent.mkdir()
    queryset.write_text(f'{{"clusterUri": "{DEV_QUERY.upper()}"}}')

    ids.translate(tmp_path)

    assert ids.endpoints == {DEV_QUERY: PRD_QUERY, DEV_INGEST: PRD_INGEST}
    assert queryset.read_text() == f'{{"clusterUri": "{PRD_QUERY}"}}'


def test_the_uri_of_an_eventhouse_the_target_lacks_is_missing(
    tmp_path: Path,
) -> None:
    """An item that holds it waits for the eventhouse, as for an ID."""
    reader = FakeReader({"eh-dev": (DEV_QUERY, DEV_INGEST)})
    ids = _map(reader, [_item("Eventhouse", "Telemetry", "eh-dev")], [])
    binding = tmp_path / "Plant.Ontology" / "b.json"
    binding.parent.mkdir()
    binding.write_text(f'{{"clusterUri": "{DEV_QUERY}"}}')

    references = ids.references(("Ontology", "Plant"), binding.parent)

    assert references.missing == {("Eventhouse", "Telemetry")}
    assert ids.endpoints == {}


def test_the_sql_endpoint_of_a_workspace_takes_one_pair() -> None:
    reader = FakeReader(
        {
            "lh-dev": (DEV_SQL,),
            "lh-prd": (PRD_SQL,),
            "wh-dev": (DEV_SQL,),
            "wh-prd": (PRD_SQL,),
        }
    )
    ids = _map(
        reader,
        [
            _item("Lakehouse", "Bronze", "lh-dev"),
            _item("Warehouse", "Gold", "wh-dev"),
        ],
        [
            _item("Lakehouse", "Bronze", "lh-prd"),
            _item("Warehouse", "Gold", "wh-prd"),
        ],
    )

    assert ids.endpoints == {DEV_SQL: PRD_SQL}
    assert reader.read == ["lh-dev", "lh-prd"]


def test_an_endpoint_not_provisioned_yet_is_read_again() -> None:
    """A new eventhouse gets its URIs a while after it is created."""
    reader = FakeReader(
        {"eh-dev": (DEV_QUERY, DEV_INGEST), "eh-prd": ("", "")}
    )
    source = [_item("Eventhouse", "Telemetry", "eh-dev")]
    target = [_item("Eventhouse", "Telemetry", "eh-prd")]
    ids = _map(reader, source, target)
    assert ids.endpoints == {}

    reader.endpoints["eh-prd"] = (PRD_QUERY, PRD_INGEST)
    with patch(
        "pyfabricops.helpers.workspace_ids.list_items", return_value=target
    ):
        ids.reload_target()

    assert ids.endpoints == {DEV_QUERY: PRD_QUERY, DEV_INGEST: PRD_INGEST}
    # The source, provisioned, was read once.
    assert reader.read.count("eh-dev") == 1


def test_without_a_reader_no_endpoint_maps() -> None:
    ids = WorkspaceIdMap(
        SOURCE,
        TARGET,
        source_items=[_item("Eventhouse", "Telemetry", "eh-dev")],
        target_items=[_item("Eventhouse", "Telemetry", "eh-prd")],
    )

    assert ids.endpoints == {}


@pytest.mark.parametrize(
    ("item_type", "properties", "expected"),
    [
        (
            "Eventhouse",
            {"queryServiceUri": DEV_QUERY, "ingestionServiceUri": DEV_INGEST},
            (DEV_QUERY, DEV_INGEST),
        ),
        (
            "Lakehouse",
            {"sqlEndpointProperties": {"connectionString": DEV_SQL}},
            (DEV_SQL,),
        ),
        ("Warehouse", {"connectionString": DEV_SQL}, (DEV_SQL,)),
        ("Lakehouse", {"sqlEndpointProperties": None}, ("",)),
    ],
)
def test_endpoints_are_read_from_the_properties(
    item_type: str, properties: dict[str, Any], expected: tuple[str, ...]
) -> None:
    with patch(
        "pyfabricops.helpers.workspace_ids.api_request",
        return_value=ApiResult(True, 200, data={"properties": properties}),
    ) as request:
        found = _fetch_endpoints(SOURCE, _item(item_type, "X", "x-1"))

    assert found == expected
    assert request.call_args.args[0].endswith("/x-1")


def test_endpoints_that_cannot_be_read_are_empty() -> None:
    with patch(
        "pyfabricops.helpers.workspace_ids.api_request",
        return_value=ApiResult(False, 403, error="Forbidden"),
    ):
        found = _fetch_endpoints(SOURCE, _item("Eventhouse", "X", "x-1"))

    assert found == ("", "")


_AGENTS = "pyfabricops.items.data_agents"


def test_publish_data_agent_by_name() -> None:
    with (
        patch(f"{_AGENTS}.resolve_workspace", return_value=TARGET),
        patch(
            f"{_AGENTS}.list_items",
            return_value=[_item("DataAgent", "Sales", "da-1")],
        ),
        patch(
            f"{_AGENTS}.api_request", return_value=ApiResult(True, 200)
        ) as request,
    ):
        publish_data_agent("Sales-PRD", "Sales", "Deployed by CI")

    assert request.call_args.args[0] == (
        f"/workspaces/{TARGET}/dataAgents/da-1/staging/publish"
    )
    assert request.call_args.kwargs["payload"] == {
        "publishedDescription": "Deployed by CI"
    }


def test_publish_data_agent_raises_when_fabric_refuses() -> None:
    with (
        patch(f"{_AGENTS}.resolve_workspace", return_value=TARGET),
        patch(
            f"{_AGENTS}.api_request",
            return_value=ApiResult(False, 400, error="Nope"),
        ),
        pytest.raises(RequestError, match="Nope"),
    ):
        publish_data_agent("Sales-PRD", "00000000-0000-4000-8000-00000000da01")


def test_publish_data_agent_raises_when_it_is_not_found() -> None:
    with (
        patch(f"{_AGENTS}.resolve_workspace", return_value=TARGET),
        patch(f"{_AGENTS}.list_items", return_value=[]),
        pytest.raises(ResourceNotFoundError),
    ):
        publish_data_agent("Sales-PRD", "Sales")
