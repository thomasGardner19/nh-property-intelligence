"""Shared Snowflake connection utilities."""

from __future__ import annotations

from typing import Any

import snowflake.connector

from .config import Settings


def connect_snowflake(settings: Settings) -> Any:
    """Create a Snowflake connection from validated application settings."""
    return snowflake.connector.connect(
        account=settings.snowflake_account,
        user=settings.snowflake_user,
        password=settings.snowflake_password,
        role=settings.snowflake_role,
        warehouse=settings.snowflake_warehouse,
        database=settings.snowflake_database,
        schema=settings.snowflake_schema,
        autocommit=False,
    )
