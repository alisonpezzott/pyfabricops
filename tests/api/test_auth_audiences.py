"""Tests for the token audiences: the Fabric, Power BI and Graph APIs, and
OneLake storage."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from pyfabricops.api.auth import (
    FabricNotebookProvider,
    OAuthProvider,
    TokenCache,
    TokenManager,
)
from pyfabricops.api.scopes import (
    FABRIC_SCOPE,
    GRAPH_SCOPE,
    POWERBI_SCOPE,
    STORAGE_SCOPE,
)
from pyfabricops.utils.exceptions import OptionNotAvailableError

_CREDENTIALS = {
    "fab_client_id": "client",
    "fab_client_secret": "not-a-secret",
    "fab_tenant_id": "tenant",
}


@pytest.mark.parametrize(
    ("audience", "scope"),
    [
        ("fabric", FABRIC_SCOPE),
        ("powerbi", POWERBI_SCOPE),
        ("graph", GRAPH_SCOPE),
        ("storage", STORAGE_SCOPE),
    ],
)
def test_each_audience_asks_for_its_scope(audience: str, scope: str) -> None:
    """A service principal's token request names the audience's scope."""
    payload = TokenManager()._build_token_payload(
        audience,  # type: ignore[arg-type]
        "spn",
        _CREDENTIALS,
    )

    assert payload["scope"] == scope


def test_a_storage_token_is_kept_apart_from_a_fabric_token(
    tmp_path: Path,
) -> None:
    """Each audience has its own cache entry, reused while it is valid."""
    manager = TokenManager()
    manager.cache = TokenCache(str(tmp_path / "token_cache.json"))
    answers = [
        {"access_token": "for-fabric", "expires_in": 3600},
        {"access_token": "for-storage", "expires_in": 3600},
    ]

    with (
        patch.object(
            manager._credential_providers["env"],
            "get_credentials",
            return_value=_CREDENTIALS,
        ),
        patch.object(
            manager, "_retrieve_token_from_api", side_effect=answers
        ) as retrieve,
    ):
        tokens = [
            manager.get_token("fabric")["access_token"],
            manager.get_token("storage")["access_token"],
            manager.get_token("storage")["access_token"],
        ]

    assert tokens == ["for-fabric", "for-storage", "for-storage"]
    assert [c.args[0] for c in retrieve.call_args_list] == [
        "fabric",
        "storage",
    ]


def test_an_interactive_storage_token_asks_for_the_storage_scope(
    tmp_path: Path,
) -> None:
    """The browser sign-in requests the scope of the audience."""
    provider = OAuthProvider(TokenCache(str(tmp_path / "token_cache.json")))
    credential = MagicMock()
    credential.get_token.return_value = SimpleNamespace(
        token="for-storage", expires_on=4_102_444_800
    )

    with patch(
        "pyfabricops.api.auth.InteractiveBrowserCredential",
        return_value=credential,
    ):
        token = provider.get_token("storage")

    credential.get_token.assert_called_once_with(STORAGE_SCOPE)
    assert token["access_token"] == "for-storage"


def test_an_unknown_audience_is_refused(tmp_path: Path) -> None:
    """The error lists the audiences there are."""
    provider = OAuthProvider(TokenCache(str(tmp_path / "token_cache.json")))

    with pytest.raises(OptionNotAvailableError, match="storage"):
        provider.get_token("onelake")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("audience", "resource"),
    [("storage", "storage"), ("fabric", "pbi"), ("powerbi", "pbi")],
)
def test_a_notebook_asks_notebookutils_for_the_matching_resource(
    tmp_path: Path, audience: str, resource: str
) -> None:
    """Inside Fabric, OneLake takes a token for "storage"."""
    provider = FabricNotebookProvider(
        TokenCache(str(tmp_path / "token_cache.json"))
    )
    credentials = MagicMock()
    credentials.getToken.return_value = "from-notebook"

    with patch.object(
        provider, "_get_notebookutils", return_value=credentials
    ):
        provider.get_token(audience)  # type: ignore[arg-type]

    credentials.getToken.assert_called_once_with(resource)
