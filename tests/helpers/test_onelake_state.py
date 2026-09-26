"""Tests for OneLakeStateBackend, against blobs kept in memory."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from pyfabricops.helpers.deployment_state import (
    DeploymentLock,
    DeploymentState,
    LockingStateBackend,
)
from pyfabricops.helpers.onelake_state import OneLakeStateBackend
from pyfabricops.utils.exceptions import (
    AuthenticationError,
    ConfigurationError,
    DeploymentLockedError,
    RequestError,
)

_MODULE = "pyfabricops.helpers.onelake_state"
_WORKSPACE_ID = "00000000-0000-0000-0000-00000000000a"
_LAKEHOUSE_ID = "00000000-0000-0000-0000-00000000000b"
_FOLDER = (
    f"https://onelake.blob.fabric.microsoft.com/{_WORKSPACE_ID}/"
    f"{_LAKEHOUSE_ID}/Files/pyfabricops/state"
)


class FakeOneLake:
    """Blobs in memory, answering as OneLake answered in a sandbox."""

    def __init__(self) -> None:
        self.blobs: dict[str, tuple[bytes, str, datetime]] = {}
        self.requests: list[dict[str, Any]] = []
        # Apply the next write, then answer as the request tried again would.
        self.lose_next_answer = False
        self._versions = 0

    def send(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        data: bytes | None = None,
        timeout: float,
        retry_transient: bool = False,
    ) -> requests.Response:
        self.requests.append(
            {"method": method, "url": url, "headers": headers, "data": data}
        )
        current = self.blobs.get(url)
        if method == "GET":
            if current is None:
                return _answer(404, code="BlobNotFound")
            content, etag, changed = current
            return _answer(200, content, etag=etag, changed=changed)

        wanted = headers.get("If-Match")
        if method == "PUT":
            if headers.get("If-None-Match") == "*" and current is not None:
                return _answer(409, code="BlobAlreadyExists")
            if wanted is not None and (
                current is None or current[1] != wanted
            ):
                return _answer(412, code="ConditionNotMet")
            assert data is not None
            etag = self.write(url, data)
            if self.lose_next_answer:
                self.lose_next_answer = False
                if headers.get("If-None-Match") == "*":
                    return _answer(409, code="BlobAlreadyExists")
                if wanted is not None:
                    return _answer(412, code="ConditionNotMet")
            return _answer(201, etag=etag)

        assert method == "DELETE"
        if current is None:
            return _answer(404, code="BlobNotFound")
        if wanted is not None and current[1] != wanted:
            return _answer(412, code="ConditionNotMet")
        del self.blobs[url]
        return _answer(202)

    def write(
        self, url: str, content: bytes, changed: datetime | None = None
    ) -> str:
        """Store a blob, as another run would; return its new ETag."""
        self._versions += 1
        etag = f'"0x{self._versions:04X}"'
        self.blobs[url] = (
            content,
            etag,
            changed or datetime.now(timezone.utc),
        )
        return etag


def _answer(
    status: int,
    content: bytes = b"",
    *,
    etag: str | None = None,
    code: str | None = None,
    changed: datetime | None = None,
) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = content
    if etag is not None:
        response.headers["ETag"] = etag
    if code is not None:
        response.headers["x-ms-error-code"] = code
    if changed is not None:
        response.headers["Last-Modified"] = format_datetime(
            changed, usegmt=True
        )
    return response


@pytest.fixture()
def onelake() -> Iterator[SimpleNamespace]:
    """Patch OneLake, the storage token and the name lookups."""
    fake = FakeOneLake()
    with (
        patch(f"{_MODULE}._send", side_effect=fake.send),
        patch(
            f"{_MODULE}._get_token", return_value={"access_token": "token"}
        ) as token,
        patch(
            f"{_MODULE}.resolve_workspace", return_value=_WORKSPACE_ID
        ) as resolve_workspace,
        patch(
            f"{_MODULE}.resolve_lakehouse", return_value=_LAKEHOUSE_ID
        ) as resolve_lakehouse,
    ):
        yield SimpleNamespace(
            fake=fake,
            token=token,
            resolve_workspace=resolve_workspace,
            resolve_lakehouse=resolve_lakehouse,
        )


def _state(
    environment: str = "prod", commit: str = "a" * 40
) -> DeploymentState:
    return DeploymentState(
        environment=environment,
        workspace="Sales-PRD",
        workspace_id="00000000-0000-0000-0000-000000000001",
        source_commit=commit,
        commits={"Notebook": commit},
        deployed_at_utc="2026-09-25T12:00:00Z",
    )


def _backend(**kwargs: Any) -> OneLakeStateBackend:
    return OneLakeStateBackend("Ops", "State", **kwargs)


def _other_lock(**changes: str) -> bytes:
    fields = {
        "environment": "prod",
        "lock_id": "other-run",
        "holder": "ci@runner",
        "acquired_at_utc": "2026-09-25T10:00:00Z",
        "expires_at_utc": "2999-01-01T00:00:00Z",
    }
    fields.update(changes)
    return json.dumps(fields).encode("utf-8")


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------


def test_the_onelake_backend_locks() -> None:
    """It keeps runs apart, as the local backend does."""
    assert isinstance(_backend(), LockingStateBackend)


def test_an_environment_without_a_state_loads_none(
    onelake: SimpleNamespace,
) -> None:
    """No file yet means no deployment recorded yet."""
    assert _backend().load("prod") is None


def test_a_state_survives_a_round_trip_through_onelake(
    onelake: SimpleNamespace,
) -> None:
    """Saved as JSON in the lakehouse Files, reached by IDs."""
    backend = _backend()
    backend.load("prod")

    backend.save("prod", _state())

    assert _backend().load("prod") == _state()
    assert list(onelake.fake.blobs) == [f"{_FOLDER}/prod.json"]


def test_every_request_carries_a_storage_token_and_the_api_version(
    onelake: SimpleNamespace,
) -> None:
    """OneLake accepts tokens for the Azure Storage audience only."""
    _backend().load("prod")

    onelake.token.assert_called_with(audience="storage")
    (request,) = onelake.fake.requests
    assert request["headers"]["Authorization"] == "Bearer token"
    assert request["headers"]["x-ms-version"] == "2021-06-08"


def test_the_first_state_is_saved_only_where_there_is_none(
    onelake: SimpleNamespace,
) -> None:
    """load found nothing, so save must not overwrite another run's."""
    backend = _backend()
    backend.load("prod")
    onelake.fake.write(
        f"{_FOLDER}/prod.json", json.dumps(_state().to_dict()).encode()
    )

    with pytest.raises(RequestError, match="changed in .* since this run"):
        backend.save("prod", _state(commit="b" * 40))

    assert onelake.fake.requests[1]["headers"]["If-None-Match"] == "*"


def test_a_state_is_saved_only_over_the_one_loaded(
    onelake: SimpleNamespace,
) -> None:
    """Another run saved in between: its state is left as it is."""
    first = _backend()
    first.load("prod")
    first.save("prod", _state())
    backend = _backend()
    backend.load("prod")
    first.save("prod", _state(commit="c" * 40))

    with pytest.raises(RequestError) as caught:
        backend.save("prod", _state(commit="b" * 40))

    assert str(caught.value) == (
        "Deployment state 'prod' changed in Ops/State/Files/pyfabricops/"
        "state/prod.json since this run read it, so it was not "
        "overwritten: another run deployed to the environment meanwhile."
    )
    assert _backend().load("prod") == _state(commit="c" * 40)


def test_consecutive_saves_of_one_run_follow_their_own_etag(
    onelake: SimpleNamespace,
) -> None:
    """Each save knows the version it wrote."""
    backend = _backend()
    backend.load("prod")

    backend.save("prod", _state())
    backend.save("prod", _state(commit="b" * 40))

    assert _backend().load("prod") == _state(commit="b" * 40)


def test_a_save_whose_answer_was_lost_is_not_a_conflict(
    onelake: SimpleNamespace,
) -> None:
    """Tried again, the request finds its own write, not another run's."""
    backend = _backend()
    backend.load("prod")
    onelake.fake.lose_next_answer = True

    backend.save("prod", _state())

    assert _backend().load("prod") == _state()


def test_a_save_without_a_load_writes_whatever_is_there(
    onelake: SimpleNamespace,
) -> None:
    """Nothing was read, so there is nothing to compare with."""
    onelake.fake.write(
        f"{_FOLDER}/prod.json", json.dumps(_state().to_dict()).encode()
    )

    _backend().save("prod", _state(commit="b" * 40))

    headers = onelake.fake.requests[-1]["headers"]
    assert "If-Match" not in headers and "If-None-Match" not in headers


def test_names_are_looked_up_once(onelake: SimpleNamespace) -> None:
    """Then the workspace and lakehouse are reached by ID."""
    backend = _backend()
    backend.load("prod")
    backend.save("prod", _state())
    with backend.lock("prod"):
        pass

    onelake.resolve_workspace.assert_called_once_with("Ops")
    onelake.resolve_lakehouse.assert_called_once_with(_WORKSPACE_ID, "State")


def test_a_regional_endpoint_and_another_folder_can_be_given(
    onelake: SimpleNamespace,
) -> None:
    """A regional endpoint keeps the data in its region."""
    backend = OneLakeStateBackend(
        "Ops",
        "State",
        "/",
        endpoint="https://westus-onelake.blob.fabric.microsoft.com/",
    )

    backend.load("prod")

    assert onelake.fake.requests[0]["url"] == (
        f"https://westus-onelake.blob.fabric.microsoft.com/{_WORKSPACE_ID}/"
        f"{_LAKEHOUSE_ID}/Files/prod.json"
    )


def test_a_missing_workspace_or_lakehouse_is_a_configuration_error(
    onelake: SimpleNamespace,
) -> None:
    """Nothing is sent to OneLake without both."""
    onelake.resolve_lakehouse.return_value = None
    with pytest.raises(ConfigurationError, match="Lakehouse 'State' not"):
        _backend().load("prod")

    onelake.resolve_workspace.return_value = None
    with pytest.raises(ConfigurationError, match="Workspace 'Ops' not"):
        _backend().load("prod")

    assert onelake.fake.requests == []


def test_a_state_of_another_environment_is_rejected(
    onelake: SimpleNamespace,
) -> None:
    """The environment inside the file must be the one asked for."""
    onelake.fake.write(
        f"{_FOLDER}/prod.json",
        json.dumps(_state("dev").to_dict()).encode(),
    )

    with pytest.raises(ConfigurationError, match="environment 'dev'"):
        _backend().load("prod")


def test_an_invalid_state_file_is_a_configuration_error(
    onelake: SimpleNamespace,
) -> None:
    """What is in the lakehouse is named in the error."""
    onelake.fake.write(f"{_FOLDER}/prod.json", b"{not json")

    with pytest.raises(ConfigurationError, match="prod.json is not valid"):
        _backend().load("prod")


def test_a_failed_request_names_the_status_and_error_code(
    onelake: SimpleNamespace,
) -> None:
    """Such as an identity that cannot read the lakehouse."""
    with patch(
        f"{_MODULE}._send",
        return_value=_answer(403, code="AuthorizationPermissionMismatch"),
    ):
        with pytest.raises(RequestError) as caught:
            _backend().load("prod")

    assert str(caught.value) == (
        "OneLake could not read Ops/State/Files/pyfabricops/state/"
        "prod.json: 403 AuthorizationPermissionMismatch."
    )


def test_onelake_out_of_reach_is_a_request_error(
    onelake: SimpleNamespace,
) -> None:
    """A connection that keeps failing, after the retries."""
    with patch(
        f"{_MODULE}._send",
        side_effect=requests.exceptions.ConnectionError("no route"),
    ):
        with pytest.raises(RequestError, match="could not be reached"):
            _backend().load("prod")


def test_every_request_may_be_tried_again(onelake: SimpleNamespace) -> None:
    """The backend tells its own writes from another run's."""
    with patch(f"{_MODULE}._send", return_value=_answer(404)) as send:
        _backend().load("prod")

    assert send.call_args.kwargs["retry_transient"] is True


def test_no_token_is_an_authentication_error(
    onelake: SimpleNamespace,
) -> None:
    """Without a storage token, OneLake is not called."""
    onelake.token.return_value = None

    with pytest.raises(AuthenticationError, match="token for OneLake"):
        _backend().load("prod")


# ---------------------------------------------------------------------------
# Locks
# ---------------------------------------------------------------------------


def test_a_lock_is_created_only_where_there_is_none(
    onelake: SimpleNamespace,
) -> None:
    """The lock file holds who and until when, and goes on release."""
    backend = _backend()

    with backend.lock("prod") as held:
        content = onelake.fake.blobs[f"{_FOLDER}/prod.lock"][0]
        assert json.loads(content) == held.to_dict()
        assert onelake.fake.requests[0]["headers"]["If-None-Match"] == "*"

    assert f"{_FOLDER}/prod.lock" not in onelake.fake.blobs
    assert onelake.fake.requests[-1]["method"] == "DELETE"
    assert "If-Match" in onelake.fake.requests[-1]["headers"]


def test_a_lock_another_run_holds_fails_at_once(
    onelake: SimpleNamespace,
) -> None:
    """The error says who holds it and until when."""
    onelake.fake.write(f"{_FOLDER}/prod.lock", _other_lock())

    with pytest.raises(DeploymentLockedError, match="held by ci@runner"):
        with _backend().lock("prod"):
            pass


def test_an_expired_lock_is_taken_over_by_its_etag(
    onelake: SimpleNamespace,
) -> None:
    """Only the expired lock read is replaced."""
    etag = onelake.fake.write(
        f"{_FOLDER}/prod.lock",
        _other_lock(expires_at_utc="2026-09-25T12:00:00Z"),
    )

    with _backend().lock("prod") as held:
        assert held.lock_id != "other-run"

    takeover = next(
        r
        for r in onelake.fake.requests
        if r["method"] == "PUT" and "If-Match" in r["headers"]
    )
    assert takeover["headers"]["If-Match"] == etag


def test_a_lock_taken_over_first_by_another_run_stays_its(
    onelake: SimpleNamespace,
) -> None:
    """Two runs take over one expired lock: only one of them wins."""
    url = f"{_FOLDER}/prod.lock"
    onelake.fake.write(url, _other_lock(expires_at_utc="2026-09-25T12:00:00Z"))
    send = onelake.fake.send

    def another_run_first(**request: Any) -> requests.Response:
        if request["method"] == "PUT" and "If-Match" in request["headers"]:
            onelake.fake.write(url, _other_lock(lock_id="third-run"))
        return send(**request)

    with patch(f"{_MODULE}._send", side_effect=another_run_first):
        with pytest.raises(DeploymentLockedError):
            with _backend().lock("prod"):
                pass

    assert json.loads(onelake.fake.blobs[url][0])["lock_id"] == "third-run"


def test_a_lock_whose_answer_was_lost_is_known_as_this_runs(
    onelake: SimpleNamespace,
) -> None:
    """Tried again, the create finds the run's own lock."""
    onelake.fake.lose_next_answer = True

    with _backend().lock("prod"):
        pass

    assert onelake.fake.blobs == {}


def test_an_unreadable_lock_holds_until_its_ttl_from_its_last_change(
    onelake: SimpleNamespace,
) -> None:
    """Then another run may take it over."""
    url = f"{_FOLDER}/prod.lock"
    onelake.fake.write(url, b"")
    with pytest.raises(DeploymentLockedError, match="an unknown run"):
        with _backend().lock("prod"):
            pass

    hours_ago = datetime.now(timezone.utc) - timedelta(hours=3)
    onelake.fake.write(url, b"", changed=hours_ago)
    with _backend().lock("prod") as held:
        assert held.holder != "an unknown run"


def test_force_unlock_removes_the_lock_whoever_holds_it(
    onelake: SimpleNamespace,
) -> None:
    """It says whose lock it removed."""
    onelake.fake.write(f"{_FOLDER}/prod.lock", _other_lock())

    removed = _backend().force_unlock("prod")

    assert isinstance(removed, DeploymentLock)
    assert removed.lock_id == "other-run"
    assert _backend().force_unlock("prod") is None


def test_a_lock_timeout_waits_on_onelake_too(
    onelake: SimpleNamespace,
) -> None:
    """The other run releases it during the wait."""
    url = f"{_FOLDER}/prod.lock"
    onelake.fake.write(url, _other_lock())
    released = MagicMock(
        side_effect=lambda seconds: onelake.fake.blobs.pop(url)
    )

    with patch("pyfabricops.helpers.deployment_state.time.sleep", released):
        with _backend(lock_timeout=30).lock("prod") as held:
            assert held.lock_id != "other-run"

    released.assert_called_once()
