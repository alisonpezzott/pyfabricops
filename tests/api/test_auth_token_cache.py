"""Tests for the token cache: one entry per identity, in a private file."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from pathlib import Path
from typing import Literal
from unittest.mock import patch

import pytest

from pyfabricops.api.auth import TokenCache, TokenManager

_POSIX_ONLY = pytest.mark.skipif(
    not hasattr(os, "getuid"), reason="file ownership and modes are POSIX"
)
_IDENTITY = {
    "FAB_TENANT_ID": "tenant-a",
    "FAB_CLIENT_ID": "client-a",
    "FAB_CLIENT_SECRET": "secret-a",
    "FAB_USERNAME": "user-a@example.com",
    "FAB_PASSWORD": "password-a",
}


@pytest.fixture()
def identity(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    """Credentials in the environment, with no .env file loaded over them."""
    for name, value in _IDENTITY.items():
        monkeypatch.setenv(name, value)
    with patch("pyfabricops.api.auth.load_dotenv"):
        yield monkeypatch


def _manager(
    tmp_path: Path, credential_type: Literal["spn", "user"] = "spn"
) -> TokenManager:
    """A manager on the env provider, with its cache file in tmp_path."""
    manager = TokenManager()
    manager.set_auth_provider("env", credential_type=credential_type)
    manager.cache = TokenCache(str(tmp_path / "token_cache.json"))
    return manager


def _responses(*tokens: str) -> list[dict[str, object]]:
    """Token responses as the identity platform returns them."""
    return [{"access_token": token, "expires_in": 3600} for token in tokens]


@pytest.mark.parametrize(
    ("credential_type", "variable"),
    [
        ("spn", "FAB_TENANT_ID"),
        ("spn", "FAB_CLIENT_ID"),
        ("user", "FAB_USERNAME"),
    ],
)
def test_another_identity_gets_its_own_token(
    identity: pytest.MonkeyPatch,
    tmp_path: Path,
    credential_type: Literal["spn", "user"],
    variable: str,
) -> None:
    """Switching credentials never reuses the previous identity's token."""
    manager = _manager(tmp_path, credential_type)

    with patch.object(
        manager,
        "_retrieve_token_from_api",
        side_effect=_responses("token-a", "token-b"),
    ) as retrieve:
        first = manager.get_token("fabric")["access_token"]
        identity.setenv(variable, "another")
        second = manager.get_token("fabric")["access_token"]
        identity.setenv(variable, _IDENTITY[variable])
        again = manager.get_token("fabric")["access_token"]

    assert (first, second, again) == ("token-a", "token-b", "token-a")
    assert retrieve.call_count == 2


def test_the_cache_lists_no_secret_and_no_identity(
    identity: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Identities are hashed, and secrets never reach the file."""
    manager = _manager(tmp_path, "user")

    with patch.object(
        manager, "_retrieve_token_from_api", side_effect=_responses("token-a")
    ):
        manager.get_token("fabric")

    content = (tmp_path / "token_cache.json").read_text(encoding="utf-8")
    assert "token-a" in content
    for value in _IDENTITY.values():
        assert value not in content


def test_clearing_the_cache_forgets_every_identity(
    identity: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """After clear_cache, each identity asks for a new token."""
    manager = _manager(tmp_path)

    with patch.object(
        manager,
        "_retrieve_token_from_api",
        side_effect=_responses("token-a", "token-b", "token-c"),
    ) as retrieve:
        manager.get_token("fabric")
        identity.setenv("FAB_CLIENT_ID", "client-b")
        manager.get_token("fabric")
        manager.cache.clear_cache()
        assert not (tmp_path / "token_cache.json").exists()
        token = manager.get_token("fabric")["access_token"]

    assert token == "token-c"
    assert retrieve.call_count == 3


def test_the_default_cache_is_private_to_the_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Not the shared temporary folder, and nothing is written up front."""
    for name in ("HOME", "USERPROFILE", "LOCALAPPDATA", "XDG_CACHE_HOME"):
        monkeypatch.setenv(name, str(tmp_path))

    cache = TokenCache()
    path = Path(cache.cache_file)

    assert (path.parent.name, path.name) == ("pyfabricops", "token_cache.json")
    assert tmp_path in path.parents
    assert not path.exists()

    cache.store_token("KEY", "token-a", 3600)

    assert (cache.get_token("KEY") or {}).get("access_token") == "token-a"
    if hasattr(os, "getuid"):
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


@_POSIX_ONLY
def test_the_cache_file_is_readable_by_its_owner_only(tmp_path: Path) -> None:
    """Other users of the machine cannot read the tokens."""
    path = tmp_path / "token_cache.json"
    path.write_text("{}", encoding="utf-8")
    path.chmod(0o644)

    TokenCache(str(path)).store_token("KEY", "token-a", 3600)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_a_cache_file_of_another_user_is_never_used(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A planted file neither feeds tokens nor receives them."""
    path = tmp_path / "token_cache.json"
    planted = '{"KEY": {"access_token": "planted", "expires_at": 9e9}}'
    path.write_text(planted, encoding="utf-8")
    owner = path.stat().st_uid
    # Windows has no getuid; faking one runs the same check there.
    monkeypatch.setattr(os, "getuid", lambda: owner + 1, raising=False)
    cache = TokenCache(str(path))

    assert cache.get_token("KEY") is None
    cache.store_token("KEY", "token-a", 3600)

    assert (cache.get_token("KEY") or {}).get("access_token") == "token-a"
    assert path.read_text(encoding="utf-8") == planted


def test_tokens_stay_in_memory_when_the_file_cannot_be_written(
    tmp_path: Path,
) -> None:
    """An unusable cache folder does not break authentication."""
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("", encoding="utf-8")
    cache = TokenCache(str(blocker / "token_cache.json"))

    cache.store_token("KEY", "token-a", 3600)

    assert (cache.get_token("KEY") or {}).get("access_token") == "token-a"
    assert cache.is_token_valid("KEY")
