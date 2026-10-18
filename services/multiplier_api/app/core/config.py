# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://admin:admin1234@localhost:5438/rutaviva_db"
    freshness_threshold_seconds: int = 300
    auditor_api_key: str = "auditor-secret-token"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()