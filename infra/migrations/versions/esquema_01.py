"""Esquema operacional v1 (13 entidades del MER, PostgreSQL).

Revision ID: 0001
Revises: (ninguna, es la primera)

Fuente: "Documentación de Arquitectura (Base de datos) v1", sección 2.1 MER.
Decisiones que NO vienen literales del MER están marcadas con "DECISIÓN".
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Orden de creación: primero tablas "padre" (sin FK), luego las que dependen de ellas.
    op.execute(
        """
        -- ───────────── Catálogos y reglas (sin dependencias) ─────────────

        -- Catálogo de las 265 zonas (F2). zone_id es int, no UUID (viene del dataset F1/F2).
        CREATE TABLE zone (
            zone_id    INTEGER PRIMARY KEY,
            borough    TEXT NOT NULL,
            zone_name  TEXT NOT NULL
        );

        -- Reglas de tarifa con vigencia (RF-08). 'rules' guarda los umbrales como JSON.
        CREATE TABLE tariff_rule_version (
            rule_version_id INTEGER PRIMARY KEY,
            valid_from      DATE  NOT NULL,
            valid_to        DATE,                       -- NULL = vigente sin fecha de fin
            rules           JSONB NOT NULL,             -- DECISIÓN: JSONB en vez de JSON (indexable, validado)
            CONSTRAINT ck_rule_vigencia CHECK (valid_to IS NULL OR valid_to >= valid_from)
        );

        -- Lluvia actual por hora (F3), cargada por el DAG horario. Evita llamar a la API externa en cada cálculo (RN-04).
        CREATE TABLE weather_current (
            valid_hour TIMESTAMPTZ PRIMARY KEY,
            rain_mm_h  DOUBLE PRECISION NOT NULL CHECK (rain_mm_h >= 0)
        );

        -- ───────────── Conductores (los puebla el seed, F6) ─────────────
        -- Sin DEFAULT en los ids: el seed los genera deterministas (uuid5) para ser reproducible.

        CREATE TABLE driver (
            driver_id UUID PRIMARY KEY,
            -- DECISIÓN: el documento dice "activo o suspendido" (RN-09); se fija en inglés como valores técnicos.
            status    TEXT NOT NULL CHECK (status IN ('active', 'suspended')),
            full_name TEXT NOT NULL
        );

        CREATE TABLE vehicle (
            vehicle_id UUID PRIMARY KEY,
            driver_id  UUID NOT NULL REFERENCES driver(driver_id),
            plate      TEXT NOT NULL UNIQUE             -- DECISIÓN: una placa identifica un solo vehículo
        );

        CREATE TABLE license (
            license_id UUID PRIMARY KEY,
            driver_id  UUID NOT NULL REFERENCES driver(driver_id),
            expires_on DATE NOT NULL                    -- licencia vencida => fuera de oferta (RN-09, CA-06)
        );

        CREATE TABLE sanction (
            sanction_id UUID PRIMARY KEY,
            driver_id   UUID NOT NULL REFERENCES driver(driver_id),
            starts_on   DATE NOT NULL,
            ends_on     DATE NOT NULL,
            CONSTRAINT ck_sanction_fechas CHECK (ends_on >= starts_on)
        );

        -- ───────────── Estado en vivo (lo escribe el pressure-worker) ─────────────

        -- Última posición/estado de cada vehículo (1 fila por vehículo). last_seen_at sirve para RN-10 (2 min).
        CREATE TABLE vehicle_state (
            vehicle_id   UUID PRIMARY KEY REFERENCES vehicle(vehicle_id),
            zone_id      INTEGER REFERENCES zone(zone_id),   -- DECISIÓN: nullable (coordenadas fuera de ciudad, 5.3)
            latitude     DOUBLE PRECISION,
            longitude    DOUBLE PRECISION,
            status       TEXT NOT NULL,                      -- valores los define el worker (p. ej. free/busy/out_of_service)
            last_seen_at TIMESTAMPTZ NOT NULL
        );

        -- Valor vigente por zona (1 fila por zona): la API lo lee por clave primaria.
        CREATE TABLE zone_state (
            zone_id            INTEGER PRIMARY KEY REFERENCES zone(zone_id),
            computed_at        TIMESTAMPTZ NOT NULL,         -- detecta dato obsoleto (RNF-02, RNF-04)
            pressure_index     DOUBLE PRECISION NOT NULL CHECK (pressure_index >= 0),
            multiplier         NUMERIC(3,2) NOT NULL DEFAULT 1.0
                               CHECK (multiplier BETWEEN 1.0 AND 2.0),   -- RN-05: tope 2,0
            free_vehicles      INTEGER NOT NULL CHECK (free_vehicles >= 0),
            requests_last_10min INTEGER NOT NULL CHECK (requests_last_10min >= 0)
        );

        -- Historia por zona e intervalo; alimenta FACT_ZONE_INTERVAL. Tabla aparte para no frenar la lectura de zone_state.
        CREATE TABLE zone_state_history (
            zone_id                 INTEGER NOT NULL REFERENCES zone(zone_id),
            interval_start          TIMESTAMPTZ NOT NULL,
            requests                INTEGER NOT NULL CHECK (requests >= 0),
            free_vehicles           INTEGER NOT NULL CHECK (free_vehicles >= 0),
            pressure_index          DOUBLE PRECISION NOT NULL CHECK (pressure_index >= 0),
            multiplier              NUMERIC(3,2) NOT NULL CHECK (multiplier BETWEEN 1.0 AND 2.0),
            estimated_wait_minutes  DOUBLE PRECISION CHECK (estimated_wait_minutes >= 0),  -- RN-08
            PRIMARY KEY (zone_id, interval_start)
        );

        -- Eventos/emergencias por zona (F7). Con is_emergency el multiplicador se fuerza a 1,0 (RN-06).
        CREATE TABLE special_event (
            event_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            zone_id      INTEGER NOT NULL REFERENCES zone(zone_id),
            starts_at    TIMESTAMPTZ NOT NULL,
            ends_at      TIMESTAMPTZ NOT NULL,
            is_emergency BOOLEAN NOT NULL DEFAULT FALSE,
            CONSTRAINT ck_event_fechas CHECK (ends_at > starts_at)
        );

        -- ───────────── Solicitudes y auditoría (las escribe la API) ─────────────

        -- requested_at fija el multiplicador que se cobra (RN-07), aunque la asignación ocurra después.
        CREATE TABLE trip_request (
            trip_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            zone_id      INTEGER NOT NULL REFERENCES zone(zone_id),   -- zona de origen
            requested_at TIMESTAMPTZ NOT NULL,
            -- DECISIÓN: estados tomados de la doc ("creada, cancelada, asignada"); ajustar si el equipo define más.
            status       TEXT NOT NULL DEFAULT 'created'
                         CHECK (status IN ('created', 'cancelled', 'assigned'))
        );

        -- Registro INMUTABLE de cómo se calculó cada tarifa (RN-12). 1 fila por solicitud.
        -- DECISIÓN: dinero en NUMERIC(10,2) en vez de float (evita errores de redondeo en tarifas).
        CREATE TABLE fare_audit (
            trip_id         UUID PRIMARY KEY REFERENCES trip_request(trip_id),
            base_fare       NUMERIC(10,2) NOT NULL CHECK (base_fare > 0),
            multiplier      NUMERIC(3,2)  NOT NULL CHECK (multiplier BETWEEN 1.0 AND 2.0),
            charged_fare    NUMERIC(10,2) NOT NULL CHECK (charged_fare > 0),
            pressure_index  DOUBLE PRECISION NOT NULL,
            rain_mm_h       DOUBLE PRECISION NOT NULL DEFAULT 0,
            rule_version_id INTEGER NOT NULL REFERENCES tariff_rule_version(rule_version_id)
        );

        -- ───────────── Índices sobre llaves foráneas y consultas calientes ─────────────
        -- (PostgreSQL NO indexa las FK automáticamente.)
        CREATE INDEX ix_vehicle_driver        ON vehicle(driver_id);
        CREATE INDEX ix_license_driver        ON license(driver_id);
        CREATE INDEX ix_sanction_driver       ON sanction(driver_id);
        CREATE INDEX ix_vehicle_state_zone    ON vehicle_state(zone_id, status);   -- contar libres por zona
        CREATE INDEX ix_special_event_zone    ON special_event(zone_id, starts_at, ends_at);
        CREATE INDEX ix_trip_request_zone_ts  ON trip_request(zone_id, requested_at); -- ventana de 10 min (RN-02)
        """
    )


def downgrade() -> None:
    # Se borra en orden inverso a la creación (primero hijos, luego padres).
    op.execute(
        """
        DROP TABLE IF EXISTS fare_audit, trip_request, special_event, zone_state_history,
            zone_state, vehicle_state, sanction, license, vehicle, driver,
            weather_current, tariff_rule_version, zone CASCADE;
        """
    )