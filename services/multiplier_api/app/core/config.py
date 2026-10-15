# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
# De pydantic_settings.BaseSettings se heredan las clases de configuración de la app.


class Settings(BaseSettings):
    # Sin valor por defecto: si falta, la app falla al arrancar
    # en vez de conectarse a una base equivocada.
    database_url: str
    # Umbral de frescura de computed_at (RNF-02: 5 min por defecto).
    freshness_threshold_seconds: int = 300
    # 

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()