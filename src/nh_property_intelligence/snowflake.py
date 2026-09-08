"""Shared Snowflake connection utilities."""

from __future__ import annotations

from typing import Any

import snowflake.connector

from .config import Settings


def connect_snowflake(settings: Settings) -> Any:
    """Create a Snowflake connection from validated application settings."""
    connection_options: dict[str, Any] = {
        "account": settings.snowflake_account,
        "user": settings.snowflake_user,
        "authenticator": settings.snowflake_authenticator,
        "role": settings.snowflake_role,
        "warehouse": settings.snowflake_warehouse,
        "database": settings.snowflake_database,
        "schema": settings.snowflake_schema,
        "autocommit": False,
    }
    if settings.snowflake_password is not None:
        connection_options["password"] = settings.snowflake_password.get_secret_value()

    return snowflake.connector.connect(**connection_options)
