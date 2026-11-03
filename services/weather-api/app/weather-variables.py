import os
from datetime import UTC, datetime
from pathlib import Path

# Cargar automáticamente .env si no existe DATABASE_URL en el entorno
if not os.getenv("DATABASE_URL"):
    try:
        from dotenv import load_dotenv
        for parent in Path(__file__).resolve().parents:
            env_file = parent / ".env"
            if env_file.exists():
                load_dotenv(env_file)
                break
    except ImportError:
        pass

import requests
from sqlalchemy import create_engine, text

URL = "https://api.open-meteo.com/v1/forecast"
NYC_CENTER_LATITUDE = 40.7128
NYC_CENTER_LONGITUDE = -74.0060
HOURLY_RAIN_VARIABLE = "rain"
DEFAULT_LOCAL_DB_URL = "postgresql+psycopg://admin:admin1234@localhost:5438/rutaviva_db"
#Variable de entorno para la URL de la base de datos, si no se proporciona, se usa la predeterminada


def upload_current_weather() -> datetime:
    """Consulta la lluvia del centro de NYC y la guarda para la hora UTC actual."""
    database_url = os.getenv("DATABASE_URL") or DEFAULT_LOCAL_DB_URL

    params = {
        "latitude": NYC_CENTER_LATITUDE,
        "longitude": NYC_CENTER_LONGITUDE,
        "hourly": HOURLY_RAIN_VARIABLE,
        "timezone": "UTC",
    }

    current_hour = datetime.now(UTC).replace(
        minute=0, second=0, microsecond=0
    )

    response = requests.get(URL, params=params, timeout=10)
    response.raise_for_status()
    response_data = response.json()
    try:
        hourly_data = response_data["hourly"]
        times = hourly_data["time"]
        rainfall = hourly_data[HOURLY_RAIN_VARIABLE]
    except (KeyError, TypeError) as error:
        raise ValueError(
            "Open-Meteo devolvió una respuesta sin los datos horarios de lluvia esperados."
        ) from error

    try:
        current_index = times.index(current_hour.strftime("%Y-%m-%dT%H:%M"))
    except ValueError as error:
        raise ValueError(
            f"La API no devolvió datos para la hora UTC actual {current_hour.isoformat()}."
        ) from error

    try:
        rain_mm_h = float(rainfall[current_index])
    except (IndexError, TypeError, ValueError) as error:
        raise ValueError(
            f"Open-Meteo devolvió precipitación inválida para {current_hour.isoformat()}."
        ) from error
    if not 0 <= rain_mm_h < float("inf"):
        raise ValueError(
            f"La API devolvió un valor de precipitación inválido para "
            f"{current_hour.isoformat()}."
        )

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS weather_current (
                        valid_hour TIMESTAMPTZ PRIMARY KEY,
                        rain_mm_h  DOUBLE PRECISION NOT NULL CHECK (rain_mm_h >= 0)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO weather_current (valid_hour, rain_mm_h)
                    VALUES (:valid_hour, :rain_mm_h)
                    ON CONFLICT (valid_hour)
                    DO UPDATE SET rain_mm_h = EXCLUDED.rain_mm_h
                    """
                ),
                {"valid_hour": current_hour, "rain_mm_h": rain_mm_h},
            )
    finally:
        engine.dispose()

    return current_hour


if __name__ == "__main__":
    import sys
    import time
    run_once = "--once" in sys.argv
    while True:
        try:
            uploaded_hour = upload_current_weather()
            print(
                f"Precipitación para {uploaded_hour.isoformat()} "
                "guardada en weather_current."
            )
        except Exception as e:
            print(f"Error consultando el clima: {e}")

        if run_once:
            break
        time.sleep(3600)
