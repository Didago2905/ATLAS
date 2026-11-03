from pydantic_settings import BaseSettings
from pydantic import Field, SecretStr


class Settings(BaseSettings):
    app_name: str = "Atlas"
    secret_key: str
    database_url: str
    debug: bool = True
    issue_report_rate_limit: int = Field(default=6, ge=1, le=1000)
    issue_report_rate_window_seconds: int = Field(default=600, ge=1, le=86400)
    issue_report_global_per_minute: int = Field(default=60, ge=1, le=10000)
    telegram_incidents_enabled: bool = False
    telegram_incidents_bot_token: SecretStr | None = None
    telegram_incidents_chat_id: SecretStr | None = None
    telegram_incidents_max_attempts: int = Field(default=6, ge=1, le=20)

    admin_username: str = "admin"
    admin_password: str = "atlas123"

    class Config:
        env_file = ".env"
        hide_input_in_errors = True


settings = Settings()
