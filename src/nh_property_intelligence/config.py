"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    snowflake_account: str
    snowflake_user: str
    snowflake_password: str
    snowflake_role: str
    snowflake_warehouse: str
    snowflake_database: str = "NH_PROPERTY_INTELLIGENCE"
    census_api_key: str | None = None

    @property
    def snowflake_schema(self) -> str:
        return "RAW"
