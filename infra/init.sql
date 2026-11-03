-- ==============================================================================
-- RutaViva Movilidad - Script de Inicialización Automática de Base de Datos
-- Este script se ejecuta en /docker-entrypoint-initdb.d/ al iniciar PostgreSQL
-- ==============================================================================

-- 1. Catálogo de Zonas (F2)
CREATE TABLE IF NOT EXISTS zone (
    zone_id    INTEGER PRIMARY KEY,
    borough    TEXT NOT NULL,
    zone_name  TEXT NOT NULL
);

-- 2. Reglas de Tarifa Versionadas (RF-08, RN-12)
CREATE TABLE IF NOT EXISTS tariff_rule_version (
    rule_version_id INTEGER PRIMARY KEY,
    valid_from      DATE NOT NULL,
    valid_to        DATE,
    rules           JSONB NOT NULL,
    CONSTRAINT ck_rule_vigencia CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

-- 3. Clima y Lluvia Horaria (F3, RN-04)
CREATE TABLE IF NOT EXISTS weather_current (
    valid_hour TIMESTAMPTZ PRIMARY KEY,
    rain_mm_h  DOUBLE PRECISION NOT NULL CHECK (rain_mm_h >= 0)
);

-- 4. Conductores (F6, RN-09, CA-06)
CREATE TABLE IF NOT EXISTS driver (
    driver_id UUID PRIMARY KEY,
    status    TEXT NOT NULL CHECK (status IN ('active', 'inactive', 'suspended')),
    full_name TEXT NOT NULL
);

-- 5. Vehículos (F6)
CREATE TABLE IF NOT EXISTS vehicle (
    vehicle_id UUID PRIMARY KEY,
    driver_id  UUID NOT NULL REFERENCES driver(driver_id),
    plate      TEXT NOT NULL UNIQUE
);

-- 6. Licencias de Conducir (RN-09)
CREATE TABLE IF NOT EXISTS license (
    license_id UUID PRIMARY KEY,
    driver_id  UUID NOT NULL REFERENCES driver(driver_id),
    expires_on DATE NOT NULL
);

-- 7. Sanciones Administrativas (RN-09)
CREATE TABLE IF NOT EXISTS sanction (
    sanction_id UUID PRIMARY KEY,
    driver_id   UUID NOT NULL REFERENCES driver(driver_id),
    starts_on   DATE NOT NULL,
    ends_on     DATE NOT NULL,
    CONSTRAINT ck_sanction_fechas CHECK (ends_on >= starts_on)
);

-- 8. Estado en Vivo de Vehículos (F4, RN-10)
CREATE TABLE IF NOT EXISTS vehicle_state (
    vehicle_id   UUID PRIMARY KEY REFERENCES vehicle(vehicle_id),
    zone_id      INTEGER REFERENCES zone(zone_id),
    latitude     DOUBLE PRECISION,
    longitude    DOUBLE PRECISION,
    status       TEXT NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL
);

-- 9. Estado Precomputado por Zona (F5, RN-02, RN-03, RN-05)
CREATE TABLE IF NOT EXISTS zone_state (
    zone_id             INTEGER PRIMARY KEY REFERENCES zone(zone_id),
    computed_at         TIMESTAMPTZ NOT NULL,
    pressure_index      DOUBLE PRECISION NOT NULL CHECK (pressure_index >= 0),
    multiplier          NUMERIC(3,2) NOT NULL DEFAULT 1.0 CHECK (multiplier BETWEEN 1.0 AND 2.0),
    free_vehicles       INTEGER NOT NULL CHECK (free_vehicles >= 0),
    requests_last_10min INTEGER NOT NULL CHECK (requests_last_10min >= 0)
);

-- 10. Histórico de Estados por Zona (RN-08)
CREATE TABLE IF NOT EXISTS zone_state_history (
    zone_id                INTEGER NOT NULL REFERENCES zone(zone_id),
    interval_start         TIMESTAMPTZ NOT NULL,
    requests               INTEGER NOT NULL CHECK (requests >= 0),
    free_vehicles          INTEGER NOT NULL CHECK (free_vehicles >= 0),
    pressure_index         DOUBLE PRECISION NOT NULL CHECK (pressure_index >= 0),
    multiplier             NUMERIC(3,2) NOT NULL CHECK (multiplier BETWEEN 1.0 AND 2.0),
    estimated_wait_minutes DOUBLE PRECISION CHECK (estimated_wait_minutes >= 0),
    PRIMARY KEY (zone_id, interval_start)
);

-- 11. Eventos Especiales y Emergencias (F7, RN-06)
CREATE TABLE IF NOT EXISTS special_event (
    event_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zone_id      INTEGER NOT NULL REFERENCES zone(zone_id),
    starts_at    TIMESTAMPTZ NOT NULL,
    ends_at      TIMESTAMPTZ NOT NULL,
    is_emergency BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT ck_event_fechas CHECK (ends_at > starts_at)
);

-- 12. Solicitudes de Viaje (F5, RN-07)
CREATE TABLE IF NOT EXISTS trip_request (
    trip_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zone_id      INTEGER NOT NULL REFERENCES zone(zone_id),
    requested_at TIMESTAMPTZ NOT NULL,
    status       TEXT NOT NULL DEFAULT 'created' CHECK (status IN ('created', 'cancelled', 'assigned'))
);

-- 13. Auditoría Inmutable de Tarifas (RN-12, RNF-05, RNF-06)
CREATE TABLE IF NOT EXISTS fare_audit (
    trip_id         UUID PRIMARY KEY REFERENCES trip_request(trip_id),
    base_fare       NUMERIC(10,2) NOT NULL CHECK (base_fare > 0),
    multiplier      NUMERIC(3,2)  NOT NULL CHECK (multiplier BETWEEN 1.0 AND 2.0),
    charged_fare    NUMERIC(10,2) NOT NULL CHECK (charged_fare > 0),
    pressure_index  DOUBLE PRECISION NOT NULL,
    rain_mm_h       DOUBLE PRECISION NOT NULL DEFAULT 0,
    rule_version_id INTEGER NOT NULL REFERENCES tariff_rule_version(rule_version_id)
);

-- Índices de Alto Rendimiento
CREATE INDEX IF NOT EXISTS ix_vehicle_driver        ON vehicle(driver_id);
CREATE INDEX IF NOT EXISTS ix_license_driver        ON license(driver_id);
CREATE INDEX IF NOT EXISTS ix_sanction_driver       ON sanction(driver_id);
CREATE INDEX IF NOT EXISTS ix_vehicle_state_zone    ON vehicle_state(zone_id, status);
CREATE INDEX IF NOT EXISTS ix_special_event_zone    ON special_event(zone_id, starts_at, ends_at);
CREATE INDEX IF NOT EXISTS ix_trip_request_zone_ts  ON trip_request(zone_id, requested_at);

-- Registro de Versión de Migraciones Alembic
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL PRIMARY KEY
);

INSERT INTO alembic_version (version_num)
VALUES ('1c747396d464')
ON CONFLICT (version_num) DO NOTHING;
