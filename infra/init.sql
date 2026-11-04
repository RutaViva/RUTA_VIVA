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

-- 14. Quejas Operacionales de Servicio (HU / F5)
CREATE TABLE IF NOT EXISTS service_complaint (
    complaint_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id      UUID NOT NULL REFERENCES trip_request(trip_id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    category     TEXT NOT NULL CHECK (category IN ('service', 'fare', 'safety', 'other'))
);

-- Índices de Alto Rendimiento
CREATE INDEX IF NOT EXISTS ix_vehicle_driver           ON vehicle(driver_id);
CREATE INDEX IF NOT EXISTS ix_license_driver           ON license(driver_id);
CREATE INDEX IF NOT EXISTS ix_sanction_driver          ON sanction(driver_id);
CREATE INDEX IF NOT EXISTS ix_vehicle_state_zone       ON vehicle_state(zone_id, status);
CREATE INDEX IF NOT EXISTS ix_special_event_zone       ON special_event(zone_id, starts_at, ends_at);
CREATE INDEX IF NOT EXISTS ix_trip_request_zone_ts     ON trip_request(zone_id, requested_at);
CREATE INDEX IF NOT EXISTS ix_service_complaint_created ON service_complaint(created_at);

-- Registro de Versión de Migraciones Alembic
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL PRIMARY KEY
);

INSERT INTO alembic_version (version_num)
VALUES ('7e2c9f4b1a63')
ON CONFLICT (version_num) DO UPDATE SET version_num = '7e2c9f4b1a63';

-- ==============================================================================
-- Datos Semilla Básicos: Catálogo de Zonas TLC (F2, 265 zonas) y Versión de Reglas
-- ==============================================================================

INSERT INTO tariff_rule_version (rule_version_id, valid_from, rules)
VALUES (1, '2026-01-01', '{"base_fare": 1.50, "per_km": 0.35, "per_minute": 0.15, "min_multiplier": 1.0, "max_multiplier": 2.0}'::jsonb)
ON CONFLICT (rule_version_id) DO NOTHING;

INSERT INTO zone (zone_id, borough, zone_name) VALUES
    (1, 'EWR', 'Newark Airport'),
    (2, 'Queens', 'Jamaica Bay'),
    (3, 'Bronx', 'Allerton/Pelham Gardens'),
    (4, 'Manhattan', 'Alphabet City'),
    (5, 'Staten Island', 'Arden Heights'),
    (6, 'Staten Island', 'Arrochar/Fort Wadsworth'),
    (7, 'Queens', 'Astoria'),
    (8, 'Queens', 'Astoria Park'),
    (9, 'Queens', 'Auburndale'),
    (10, 'Queens', 'Baisley Park'),
    (11, 'Brooklyn', 'Bath Beach'),
    (12, 'Manhattan', 'Battery Park'),
    (13, 'Manhattan', 'Battery Park City'),
    (14, 'Brooklyn', 'Bay Ridge'),
    (15, 'Queens', 'Bay Terrace/Fort Totten'),
    (16, 'Queens', 'Bayside'),
    (17, 'Brooklyn', 'Bedford'),
    (18, 'Bronx', 'Bedford Park'),
    (19, 'Queens', 'Bellerose'),
    (20, 'Bronx', 'Belmont'),
    (21, 'Brooklyn', 'Bensonhurst East'),
    (22, 'Brooklyn', 'Bensonhurst West'),
    (23, 'Staten Island', 'Bloomfield/Emerson Hill'),
    (24, 'Manhattan', 'Bloomingdale'),
    (25, 'Brooklyn', 'Boerum Hill'),
    (26, 'Brooklyn', 'Borough Park'),
    (27, 'Queens', 'Breezy Point/Fort Tilden/Riis Beach'),
    (28, 'Queens', 'Briarwood/Jamaica Hills'),
    (29, 'Brooklyn', 'Brighton Beach'),
    (30, 'Queens', 'Broad Channel'),
    (31, 'Bronx', 'Bronx Park'),
    (32, 'Bronx', 'Bronxdale'),
    (33, 'Brooklyn', 'Brooklyn Heights'),
    (34, 'Brooklyn', 'Brooklyn Navy Yard'),
    (35, 'Brooklyn', 'Brownsville'),
    (36, 'Brooklyn', 'Bushwick North'),
    (37, 'Brooklyn', 'Bushwick South'),
    (38, 'Queens', 'Cambria Heights'),
    (39, 'Brooklyn', 'Canarsie'),
    (40, 'Brooklyn', 'Carroll Gardens'),
    (41, 'Manhattan', 'Central Harlem'),
    (42, 'Manhattan', 'Central Harlem North'),
    (43, 'Manhattan', 'Central Park'),
    (44, 'Staten Island', 'Charleston/Tottenville'),
    (45, 'Manhattan', 'Chinatown'),
    (46, 'Bronx', 'City Island'),
    (47, 'Bronx', 'Claremont/Bathgate'),
    (48, 'Manhattan', 'Clinton East'),
    (49, 'Brooklyn', 'Clinton Hill'),
    (50, 'Manhattan', 'Clinton West'),
    (51, 'Bronx', 'Co-Op City'),
    (52, 'Brooklyn', 'Cobble Hill'),
    (53, 'Queens', 'College Point'),
    (54, 'Brooklyn', 'Columbia Street'),
    (55, 'Brooklyn', 'Coney Island'),
    (56, 'Queens', 'Corona'),
    (57, 'Queens', 'Corona'),
    (58, 'Bronx', 'Country Club'),
    (59, 'Bronx', 'Crotona Park'),
    (60, 'Bronx', 'Crotona Park East'),
    (61, 'Brooklyn', 'Crown Heights North'),
    (62, 'Brooklyn', 'Crown Heights South'),
    (63, 'Brooklyn', 'Cypress Hills'),
    (64, 'Queens', 'Douglaston'),
    (65, 'Brooklyn', 'Downtown Brooklyn/MetroTech'),
    (66, 'Brooklyn', 'DUMBO/Vinegar Hill'),
    (67, 'Brooklyn', 'Dyker Heights'),
    (68, 'Manhattan', 'East Chelsea'),
    (69, 'Bronx', 'East Concourse/Concourse Village'),
    (70, 'Queens', 'East Elmhurst'),
    (71, 'Brooklyn', 'East Flatbush/Farragut'),
    (72, 'Brooklyn', 'East Flatbush/Remsen Village'),
    (73, 'Queens', 'East Flushing'),
    (74, 'Manhattan', 'East Harlem North'),
    (75, 'Manhattan', 'East Harlem South'),
    (76, 'Brooklyn', 'East New York'),
    (77, 'Brooklyn', 'East New York/Pennsylvania Avenue'),
    (78, 'Bronx', 'East Tremont'),
    (79, 'Manhattan', 'East Village'),
    (80, 'Brooklyn', 'East Williamsburg'),
    (81, 'Bronx', 'Eastchester'),
    (82, 'Queens', 'Elmhurst'),
    (83, 'Queens', 'Elmhurst/Maspeth'),
    (84, 'Staten Island', 'Eltingville/Annadale/Princes Bay'),
    (85, 'Brooklyn', 'Erasmus'),
    (86, 'Queens', 'Far Rockaway'),
    (87, 'Manhattan', 'Financial District North'),
    (88, 'Manhattan', 'Financial District South'),
    (89, 'Brooklyn', 'Flatbush/Ditmas Park'),
    (90, 'Manhattan', 'Flatiron'),
    (91, 'Brooklyn', 'Flatlands'),
    (92, 'Queens', 'Flushing'),
    (93, 'Queens', 'Flushing Meadows-Corona Park'),
    (94, 'Bronx', 'Fordham South'),
    (95, 'Queens', 'Forest Hills'),
    (96, 'Queens', 'Forest Park/Highland Park'),
    (97, 'Brooklyn', 'Fort Greene'),
    (98, 'Queens', 'Fresh Meadows'),
    (99, 'Staten Island', 'Freshkills Park'),
    (100, 'Manhattan', 'Garment District'),
    (101, 'Queens', 'Glen Oaks'),
    (102, 'Queens', 'Glendale'),
    (103, 'Manhattan', 'Governors Island/Ellis Island/Liberty Island'),
    (104, 'Manhattan', 'Governors Island/Ellis Island/Liberty Island'),
    (105, 'Manhattan', 'Governors Island/Ellis Island/Liberty Island'),
    (106, 'Brooklyn', 'Gowanus'),
    (107, 'Manhattan', 'Gramercy'),
    (108, 'Brooklyn', 'Gravesend'),
    (109, 'Staten Island', 'Great Kills'),
    (110, 'Staten Island', 'Great Kills Park'),
    (111, 'Brooklyn', 'Green-Wood Cemetery'),
    (112, 'Brooklyn', 'Greenpoint'),
    (113, 'Manhattan', 'Greenwich Village North'),
    (114, 'Manhattan', 'Greenwich Village South'),
    (115, 'Staten Island', 'Grymes Hill/Clifton'),
    (116, 'Manhattan', 'Hamilton Heights'),
    (117, 'Queens', 'Hammels/Arverne'),
    (118, 'Staten Island', 'Heartland Village/Todt Hill'),
    (119, 'Bronx', 'Highbridge'),
    (120, 'Manhattan', 'Highbridge Park'),
    (121, 'Queens', 'Hillcrest/Pomonok'),
    (122, 'Queens', 'Hollis'),
    (123, 'Brooklyn', 'Homecrest'),
    (124, 'Queens', 'Howard Beach'),
    (125, 'Manhattan', 'Hudson Sq'),
    (126, 'Bronx', 'Hunts Point'),
    (127, 'Manhattan', 'Inwood'),
    (128, 'Manhattan', 'Inwood Hill Park'),
    (129, 'Queens', 'Jackson Heights'),
    (130, 'Queens', 'Jamaica'),
    (131, 'Queens', 'Jamaica Estates'),
    (132, 'Queens', 'JFK Airport'),
    (133, 'Brooklyn', 'Kensington'),
    (134, 'Queens', 'Kew Gardens'),
    (135, 'Queens', 'Kew Gardens Hills'),
    (136, 'Bronx', 'Kingsbridge Heights'),
    (137, 'Manhattan', 'Kips Bay'),
    (138, 'Queens', 'LaGuardia Airport'),
    (139, 'Queens', 'Laurelton'),
    (140, 'Manhattan', 'Lenox Hill East'),
    (141, 'Manhattan', 'Lenox Hill West'),
    (142, 'Manhattan', 'Lincoln Square East'),
    (143, 'Manhattan', 'Lincoln Square West'),
    (144, 'Manhattan', 'Little Italy/NoLiTa'),
    (145, 'Queens', 'Long Island City/Hunters Point'),
    (146, 'Queens', 'Long Island City/Queens Plaza'),
    (147, 'Bronx', 'Longwood'),
    (148, 'Manhattan', 'Lower East Side'),
    (149, 'Brooklyn', 'Madison'),
    (150, 'Brooklyn', 'Manhattan Beach'),
    (151, 'Manhattan', 'Manhattan Valley'),
    (152, 'Manhattan', 'Manhattanville'),
    (153, 'Manhattan', 'Marble Hill'),
    (154, 'Brooklyn', 'Marine Park/Floyd Bennett Field'),
    (155, 'Brooklyn', 'Marine Park/Mill Basin'),
    (156, 'Staten Island', 'Mariners Harbor'),
    (157, 'Queens', 'Maspeth'),
    (158, 'Manhattan', 'Meatpacking/West Village West'),
    (159, 'Bronx', 'Melrose South'),
    (160, 'Queens', 'Middle Village'),
    (161, 'Manhattan', 'Midtown Center'),
    (162, 'Manhattan', 'Midtown East'),
    (163, 'Manhattan', 'Midtown North'),
    (164, 'Manhattan', 'Midtown South'),
    (165, 'Brooklyn', 'Midwood'),
    (166, 'Manhattan', 'Morningside Heights'),
    (167, 'Bronx', 'Morrisania/Melrose'),
    (168, 'Bronx', 'Mott Haven/Port Morris'),
    (169, 'Bronx', 'Mount Hope'),
    (170, 'Manhattan', 'Murray Hill'),
    (171, 'Queens', 'Murray Hill-Queens'),
    (172, 'Staten Island', 'New Dorp/Midland Beach'),
    (173, 'Queens', 'North Corona'),
    (174, 'Bronx', 'Norwood'),
    (175, 'Queens', 'Oakland Gardens'),
    (176, 'Staten Island', 'Oakwood'),
    (177, 'Brooklyn', 'Ocean Hill'),
    (178, 'Brooklyn', 'Ocean Parkway South'),
    (179, 'Queens', 'Old Astoria'),
    (180, 'Queens', 'Ozone Park'),
    (181, 'Brooklyn', 'Park Slope'),
    (182, 'Bronx', 'Parkchester'),
    (183, 'Bronx', 'Pelham Bay'),
    (184, 'Bronx', 'Pelham Bay Park'),
    (185, 'Bronx', 'Pelham Parkway'),
    (186, 'Manhattan', 'Penn Station/Madison Sq West'),
    (187, 'Staten Island', 'Port Richmond'),
    (188, 'Brooklyn', 'Prospect-Lefferts Gardens'),
    (189, 'Brooklyn', 'Prospect Heights'),
    (190, 'Brooklyn', 'Prospect Park'),
    (191, 'Queens', 'Queens Village'),
    (192, 'Queens', 'Queensboro Hill'),
    (193, 'Queens', 'Queensbridge/Ravenswood'),
    (194, 'Manhattan', 'Randalls Island'),
    (195, 'Brooklyn', 'Red Hook'),
    (196, 'Queens', 'Rego Park'),
    (197, 'Queens', 'Richmond Hill'),
    (198, 'Queens', 'Ridgewood'),
    (199, 'Bronx', 'Rikers Island'),
    (200, 'Bronx', 'Riverdale/North Riverdale/Fieldston'),
    (201, 'Queens', 'Rockaway Park'),
    (202, 'Manhattan', 'Roosevelt Island'),
    (203, 'Queens', 'Rosedale'),
    (204, 'Staten Island', 'Rossville/Woodrow'),
    (205, 'Queens', 'Saint Albans'),
    (206, 'Staten Island', 'Saint George/New Brighton'),
    (207, 'Queens', 'Saint Michaels Cemetery/Woodside'),
    (208, 'Bronx', 'Schuylerville/Edgewater Park'),
    (209, 'Manhattan', 'Seaport'),
    (210, 'Brooklyn', 'Sheepshead Bay'),
    (211, 'Manhattan', 'SoHo'),
    (212, 'Bronx', 'Soundview/Bruckner'),
    (213, 'Bronx', 'Soundview/Castle Hill'),
    (214, 'Staten Island', 'South Beach/Dongan Hills'),
    (215, 'Queens', 'South Jamaica'),
    (216, 'Queens', 'South Ozone Park'),
    (217, 'Brooklyn', 'South Williamsburg'),
    (218, 'Queens', 'Springfield Gardens North'),
    (219, 'Queens', 'Springfield Gardens South'),
    (220, 'Bronx', 'Spuyten Duyvil/Kingsbridge'),
    (221, 'Staten Island', 'Stapleton'),
    (222, 'Brooklyn', 'Starrett City'),
    (223, 'Queens', 'Steinway'),
    (224, 'Manhattan', 'Stuy Town/Peter Cooper Village'),
    (225, 'Brooklyn', 'Stuyvesant Heights'),
    (226, 'Queens', 'Sunnyside'),
    (227, 'Brooklyn', 'Sunset Park East'),
    (228, 'Brooklyn', 'Sunset Park West'),
    (229, 'Manhattan', 'Sutton Place/Turtle Bay North'),
    (230, 'Manhattan', 'Times Sq/Theatre District'),
    (231, 'Manhattan', 'TriBeCa/Civic Center'),
    (232, 'Manhattan', 'Two Bridges/Seward Park'),
    (233, 'Manhattan', 'UN/Turtle Bay South'),
    (234, 'Manhattan', 'Union Sq'),
    (235, 'Bronx', 'University Heights/Morris Heights'),
    (236, 'Manhattan', 'Upper East Side North'),
    (237, 'Manhattan', 'Upper East Side South'),
    (238, 'Manhattan', 'Upper West Side North'),
    (239, 'Manhattan', 'Upper West Side South'),
    (240, 'Bronx', 'Van Cortlandt Park'),
    (241, 'Bronx', 'Van Cortlandt Village'),
    (242, 'Bronx', 'Van Nest/Morris Park'),
    (243, 'Manhattan', 'Washington Heights North'),
    (244, 'Manhattan', 'Washington Heights South'),
    (245, 'Staten Island', 'West Brighton'),
    (246, 'Manhattan', 'West Chelsea/Hudson Yards'),
    (247, 'Bronx', 'West Concourse'),
    (248, 'Bronx', 'West Farms/Bronx River'),
    (249, 'Manhattan', 'West Village'),
    (250, 'Bronx', 'Westchester Village/Unionport'),
    (251, 'Staten Island', 'Westerleigh'),
    (252, 'Queens', 'Whitestone'),
    (253, 'Queens', 'Willets Point'),
    (254, 'Bronx', 'Williamsbridge/Olinville'),
    (255, 'Brooklyn', 'Williamsburg (North Side)'),
    (256, 'Brooklyn', 'Williamsburg (South Side)'),
    (257, 'Brooklyn', 'Windsor Terrace'),
    (258, 'Queens', 'Woodhaven'),
    (259, 'Bronx', 'Woodlawn/Wakefield'),
    (260, 'Queens', 'Woodside'),
    (261, 'Manhattan', 'World Trade Center'),
    (262, 'Manhattan', 'Yorkville East'),
    (263, 'Manhattan', 'Yorkville West'),
    (264, 'Unknown', 'N/A'),
    (265, 'N/A', 'Outside of NYC')
ON CONFLICT (zone_id) DO NOTHING;
