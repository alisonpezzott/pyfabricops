"""Tests for credential_type support in set_auth_provider (issue #76)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pyfabricops.api.auth import TokenManager, set_auth_provider
from pyfabricops.utils.exceptions import OptionNotAvailableError

# ---------------------------------------------------------------------------
# TokenManager — internal class
# ---------------------------------------------------------------------------


def test_token_manager_default_credential_type() -> None:
    """TokenManager defaults to 'spn' credential_type."""
    manager = TokenManager()
    assert manager.credential_type == "spn"


def test_token_manager_set_auth_provider_stores_credential_type() -> None:
    """set_auth_provider stores the given credential_type on the manager."""
    manager = TokenManager()
    manager.set_auth_provider("env", credential_type="user")
    assert manager.credential_type == "user"


def test_token_manager_set_auth_provider_defaults_to_spn() -> None:
    """set_auth_provider keeps 'spn' when credential_type is not passed."""
    manager = TokenManager()
    manager.set_auth_provider("env")
    assert manager.credential_type == "spn"


def test_token_manager_set_auth_provider_invalid_credential_type_raises() -> (
    None
):
    """set_auth_provider raises OptionNotAvailableError for unknown credential_type."""
    manager = TokenManager()
    with pytest.raises(OptionNotAvailableError):
        manager.set_auth_provider("env", credential_type="invalid")


# ---------------------------------------------------------------------------
# TokenManager.get_token — credential_type resolution
# ---------------------------------------------------------------------------


def test_get_token_uses_stored_credential_type_when_none_passed(
    tmp_path,
) -> None:
    """get_token uses self.credential_type when called without override."""
    manager = TokenManager()
    manager.credential_type = "user"
    # Use an isolated cache file so no stale tokens interfere
    manager.cache = manager.cache.__class__(str(tmp_path / "token_cache.json"))

    mock_response = {"access_token": "tok", "expires_in": 3600}

    with patch.object(
        manager, "_retrieve_token_from_api", return_value=mock_response
    ) as mock_retrieve:
        manager.get_token(audience="fabric")

    # Must have been called with credential_type="user" (resolved from state)
    mock_retrieve.assert_called_once_with("fabric", "user")


def test_get_token_override_beats_stored_credential_type(tmp_path) -> None:
    """An explicit credential_type kwarg overrides the stored value."""
    manager = TokenManager()
    manager.credential_type = "user"
    # Use an isolated cache file so no stale tokens interfere
    manager.cache = manager.cache.__class__(str(tmp_path / "token_cache.json"))

    mock_response = {"access_token": "tok", "expires_in": 3600}

    with patch.object(
        manager, "_retrieve_token_from_api", return_value=mock_response
    ) as mock_retrieve:
        manager.get_token(audience="fabric", credential_type="spn")

    mock_retrieve.assert_called_once_with("fabric", "spn")


# ---------------------------------------------------------------------------
# Public set_auth_provider
# ---------------------------------------------------------------------------


def test_public_set_auth_provider_sets_user_credential_type() -> None:
    """set_auth_provider('env', credential_type='user') propagates to _token_manager."""
    import pyfabricops.api.auth as auth_module

    original_manager = auth_module._token_manager
    try:
        auth_module._token_manager = TokenManager()
        set_auth_provider("env", credential_type="user")
        assert auth_module._token_manager.credential_type == "user"
        assert auth_module._token_manager.auth_provider == "env"
    finally:
        auth_module._token_manager = original_manager


def test_public_set_auth_provider_defaults_to_spn() -> None:
    """set_auth_provider('env') keeps credential_type as 'spn'."""
    import pyfabricops.api.auth as auth_module

    original_manager = auth_module._token_manager
    try:
        auth_module._token_manager = TokenManager()
        set_auth_provider("env")
        assert auth_module._token_manager.credential_type == "spn"
    finally:
        auth_module._token_manager = original_manager


def test_public_set_auth_provider_invalid_source_raises() -> None:
    """set_auth_provider raises OptionNotAvailableError for unknown source."""
    with pytest.raises(OptionNotAvailableError):
        set_auth_provider("invalid")


def test_public_set_auth_provider_invalid_credential_type_raises() -> None:
    """set_auth_provider raises OptionNotAvailableError for unknown credential_type."""
    with pytest.raises(OptionNotAvailableError):
        set_auth_provider("env", credential_type="invalid")
