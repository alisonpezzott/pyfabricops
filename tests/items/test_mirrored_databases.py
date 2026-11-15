"""Tests for the mirroring of a mirrored database."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock, call, patch

import pytest

from pyfabricops.api.api import ApiResult
from pyfabricops.helpers.deployment import DEPLOY_ORDER
from pyfabricops.items.mirrored_databases import (
    get_mirroring_status,
    get_tables_mirroring_status,
    start_mirroring,
    start_mirroring_and_wait,
    stop_mirroring,
)
from pyfabricops.utils.exceptions import RequestError, ResourceNotFoundError

_MODULE = "pyfabricops.items.mirrored_databases"

WORKSPACE = "00000000-0000-4000-8000-000000000001"
DATABASE = "00000000-0000-4000-8000-000000000002"
ENDPOINT = f"/workspaces/{WORKSPACE}/mirroredDatabases/{DATABASE}"
STATUS = call(
    f"{ENDPOINT}/getMirroringStatus", method="post", return_result=True
)
START = call(f"{ENDPOINT}/startMirroring", method="post", return_result=True)


def status(value: str) -> ApiResult:
    """The mirroring status, as getMirroringStatus returns it."""
    return ApiResult(True, 200, data={"status": value})


def ok() -> ApiResult:
    """A request that succeeded, without a body."""
    return ApiResult(True, 200, data=None)


def failed() -> ApiResult:
    """A request that failed."""
    return ApiResult(False, 400, error="Bad request")


@pytest.fixture()
def api() -> Iterator[MagicMock]:
    """api_request, with the workspace resolved."""
    with (
        patch(f"{_MODULE}.resolve_workspace", return_value=WORKSPACE),
        patch(f"{_MODULE}.api_request") as api_request,
    ):
        yield api_request


def test_a_mirrored_database_deploys_before_the_lakehouses() -> None:
    order = list(DEPLOY_ORDER)
    assert order.index("MirroredDatabase") < order.index("Lakehouse")


class TestResolve:
    def test_finds_a_mirrored_database_by_name(self, api: MagicMock) -> None:
        api.return_value = status("Running")
        items = [
            {"id": "other", "type": "Lakehouse", "displayName": "ERP"},
            {"id": DATABASE, "type": "MirroredDatabase", "displayName": "ERP"},
        ]
        with patch(f"{_MODULE}.list_items", return_value=items):
            assert get_mirroring_status("PRD", "ERP") == "Running"
        api.assert_called_once_with(
            f"{ENDPOINT}/getMirroringStatus", method="post", return_result=True
        )

    def test_raises_when_it_is_not_found(self, api: MagicMock) -> None:
        with (
            patch(f"{_MODULE}.list_items", return_value=[]),
            pytest.raises(ResourceNotFoundError),
        ):
            get_mirroring_status("PRD", "ERP")
        api.assert_not_called()

    def test_raises_when_the_workspace_is_not_found(self) -> None:
        with (
            patch(f"{_MODULE}.resolve_workspace", return_value=None),
            pytest.raises(ResourceNotFoundError),
        ):
            get_mirroring_status("PRD", DATABASE)


class TestGetMirroringStatus:
    def test_returns_the_status(self, api: MagicMock) -> None:
        api.return_value = status("Stopped")

        assert get_mirroring_status("PRD", DATABASE) == "Stopped"

    def test_raises_when_it_cannot_be_read(self, api: MagicMock) -> None:
        api.return_value = failed()

        with pytest.raises(RequestError):
            get_mirroring_status("PRD", DATABASE)


class TestStartMirroring:
    def test_starts_a_stopped_database(self, api: MagicMock) -> None:
        api.side_effect = [status("Stopped"), ok()]

        start_mirroring("PRD", DATABASE)

        assert api.call_args_list == [STATUS, START]

    @pytest.mark.parametrize("value", ["Running", "Starting", "Initializing"])
    def test_sends_nothing_when_it_runs_or_starts(
        self, api: MagicMock, value: str
    ) -> None:
        api.return_value = status(value)

        start_mirroring("PRD", DATABASE)

        assert api.call_args_list == [STATUS]

    def test_raises_when_it_cannot_start(self, api: MagicMock) -> None:
        api.side_effect = [status("Stopped"), failed()]

        with pytest.raises(RequestError, match="start the mirroring"):
            start_mirroring("PRD", DATABASE)


class TestStopMirroring:
    def test_stops_it(self, api: MagicMock) -> None:
        api.return_value = ok()

        stop_mirroring("PRD", DATABASE)

        api.assert_called_once_with(
            f"{ENDPOINT}/stopMirroring", method="post", return_result=True
        )

    def test_raises_when_it_cannot_stop(self, api: MagicMock) -> None:
        api.return_value = failed()

        with pytest.raises(RequestError, match="stop the mirroring"):
            stop_mirroring("PRD", DATABASE)


class TestStartMirroringAndWait:
    def test_starts_and_waits_until_it_runs(self, api: MagicMock) -> None:
        api.side_effect = [
            status("Stopped"),
            ok(),
            status("Starting"),
            status("Running"),
        ]

        with patch(f"{_MODULE}.time.sleep") as sleep:
            assert start_mirroring_and_wait("PRD", DATABASE) == "Running"

        assert api.call_args_list == [STATUS, START, STATUS, STATUS]
        sleep.assert_called_once_with(15)

    def test_only_waits_when_it_is_starting(self, api: MagicMock) -> None:
        api.side_effect = [status("Initialized"), status("Running")]

        with patch(f"{_MODULE}.time.sleep"):
            start_mirroring_and_wait("PRD", DATABASE)

        assert START not in api.call_args_list

    def test_raises_when_it_stops_on_its_way_up(self, api: MagicMock) -> None:
        api.side_effect = [status("Stopped"), ok(), status("Stopped")]

        with pytest.raises(RequestError, match="managed identity"):
            start_mirroring_and_wait("PRD", DATABASE)

    def test_raises_when_it_does_not_run_in_time(self, api: MagicMock) -> None:
        api.side_effect = [status("Starting")] * 3

        with (
            patch(f"{_MODULE}.time.sleep"),
            patch(f"{_MODULE}.time.monotonic", side_effect=[0, 0, 20, 40]),
            pytest.raises(TimeoutError),
        ):
            start_mirroring_and_wait(
                "PRD", DATABASE, timeout=30, poll_interval=15
            )


class TestGetTablesMirroringStatus:
    def test_reads_every_page(self, api: MagicMock) -> None:
        api.side_effect = [
            ApiResult(
                True,
                200,
                data={
                    "data": [{"sourceTableName": "a"}],
                    "continuationToken": "next",
                },
            ),
            ApiResult(True, 200, data={"data": [{"sourceTableName": "b"}]}),
        ]

        tables = get_tables_mirroring_status("PRD", DATABASE)

        assert [t["sourceTableName"] for t in tables] == ["a", "b"]
        assert api.call_args_list[1].kwargs["params"] == {
            "continuationToken": "next"
        }

    def test_raises_when_it_cannot_be_read(self, api: MagicMock) -> None:
        api.return_value = failed()

        with pytest.raises(RequestError):
            get_tables_mirroring_status("PRD", DATABASE)
