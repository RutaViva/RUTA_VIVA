from typing import TypedDict

from sqlalchemy import create_engine, text

from config import DATABASE_URL, ESTADOS


class EstadoInicialVehiculo(TypedDict):
    vehicle_id: str
    zone_id: int
    latitude: float
    longitude: float
    status: str


def cargar_estados_iniciales() -> list[EstadoInicialVehiculo]:
    """Carga desde PostgreSQL los vehículos y su último estado sembrado."""
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT vehicle_id, zone_id, latitude, longitude, status
                    FROM vehicle_state
                    ORDER BY vehicle_id
                    """
                )
            ).mappings().all()
    finally:
        engine.dispose()

    if not rows:
        raise RuntimeError(
            "No hay vehículos en vehicle_state; ejecuta el seeder antes del simulador."
        )

    estados_iniciales: list[EstadoInicialVehiculo] = []
    for row in rows:
        status = row["status"]
        if status not in ESTADOS:
            raise ValueError(
                f"El vehículo {row['vehicle_id']} tiene un estado no configurado: {status!r}."
            )
        estados_iniciales.append(
            {
                "vehicle_id": str(row["vehicle_id"]),
                "zone_id": int(row["zone_id"]),
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "status": status,
            }
        )

    return estados_iniciales
