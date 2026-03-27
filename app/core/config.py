from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Atlas"
    secret_key: str
    database_url: str
    debug: bool = True

    admin_username: str = "admin"
    admin_password: str = "atlas123"

    class Config:
        env_file = ".env"


settings = Settings()