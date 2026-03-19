from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Atlas"
    debug: bool = True

    admin_username: str = "admin"
    admin_password: str = "atlas123"


settings = Settings()
