from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Atlas"
    debug: bool = True


settings = Settings()
