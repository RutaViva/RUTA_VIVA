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
                    WITH operational_vehicles AS (
                        SELECT
                            state.vehicle_id,
                            state.zone_id,
                            state.latitude,
                            state.longitude,
                            state.status,
                            ROW_NUMBER() OVER (
                                PARTITION BY vehicle.driver_id
                                ORDER BY
                                    CASE state.status WHEN 'busy' THEN 0 ELSE 1 END,
                                    state.vehicle_id
                            ) AS driver_vehicle_rank
                        FROM vehicle_state AS state
                        JOIN vehicle
                            ON vehicle.vehicle_id = state.vehicle_id
                        WHERE state.status IN ('available', 'busy')
                    )
                    SELECT vehicle_id, zone_id, latitude, longitude, status
                    FROM operational_vehicles
                    WHERE driver_vehicle_rank = 1
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
