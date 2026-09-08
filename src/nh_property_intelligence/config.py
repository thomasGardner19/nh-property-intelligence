"""Application settings loaded from environment variables."""

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    snowflake_account: str
    snowflake_user: str
    snowflake_authenticator: str = "externalbrowser"
    snowflake_password: SecretStr | None = None
    snowflake_role: str
    snowflake_warehouse: str
    snowflake_database: str = "NH_PROPERTY_INTELLIGENCE"
    census_api_key: SecretStr | None = None

    @model_validator(mode="after")
    def require_secret_for_noninteractive_authentication(self) -> "Settings":
        password_authenticators = {"snowflake", "programmatic_access_token"}
        if (
            self.snowflake_authenticator.lower() in password_authenticators
            and self.snowflake_password is None
        ):
            raise ValueError(
                "SNOWFLAKE_PASSWORD is required when using password or PAT authentication"
            )
        return self

    @property
    def snowflake_schema(self) -> str:
        return "RAW"
