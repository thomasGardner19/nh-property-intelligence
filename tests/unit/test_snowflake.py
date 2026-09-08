from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from nh_property_intelligence.config import Settings
from nh_property_intelligence.snowflake import connect_snowflake


def _settings(**overrides: object) -> Settings:
    values = {
        "snowflake_account": "example-account",
        "snowflake_user": "example-user",
        "snowflake_authenticator": "externalbrowser",
        "snowflake_role": "NHPI_ENGINEER",
        "snowflake_warehouse": "NHPI_XS",
    }
    values.update(overrides)
    return Settings(**values)


def test_external_browser_connection_does_not_send_password() -> None:
    settings = _settings()

    with patch("nh_property_intelligence.snowflake.snowflake.connector.connect") as connect:
        connect_snowflake(settings)

    options = connect.call_args.kwargs
    assert options["authenticator"] == "externalbrowser"
    assert "password" not in options


def test_native_authentication_unwraps_password_only_at_connection_boundary() -> None:
    settings = _settings(snowflake_authenticator="snowflake", snowflake_password="secret")

    with patch("nh_property_intelligence.snowflake.snowflake.connector.connect") as connect:
        connect_snowflake(settings)

    assert connect.call_args.kwargs["password"] == "secret"
    assert "secret" not in repr(settings)


def test_native_authentication_requires_password() -> None:
    with pytest.raises(ValidationError, match="password or PAT authentication"):
        _settings(snowflake_authenticator="snowflake")


def test_programmatic_access_token_uses_password_boundary() -> None:
    settings = _settings(
        snowflake_authenticator="PROGRAMMATIC_ACCESS_TOKEN",
        snowflake_password="token-secret",
    )

    with patch("nh_property_intelligence.snowflake.snowflake.connector.connect") as connect:
        connect_snowflake(settings)

    assert connect.call_args.kwargs["authenticator"] == "PROGRAMMATIC_ACCESS_TOKEN"
    assert connect.call_args.kwargs["password"] == "token-secret"
    assert "token-secret" not in repr(settings)


def test_programmatic_access_token_requires_secret() -> None:
    with pytest.raises(ValidationError, match="password or PAT authentication"):
        _settings(snowflake_authenticator="PROGRAMMATIC_ACCESS_TOKEN")
