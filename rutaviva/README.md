# RutaViva Mobility · Servicios & Plataforma de Datos

Plataforma de ingeniería de datos, backend y procesamiento de streaming/batch para cálculo dinámico de tarifas (*surge/dynamic pricing*) y monitoreo de flota de transporte (~8,000 vehículos) en tiempo real.

---

## 📌 Tabla de Contenidos

1. [Visión General del Sistema](#-visión-general-del-sistema)
2. [Arquitectura y Flujo de Datos](#-arquitectura-y-flujo-de-datos)
3. [Estructura del Proyecto](#-estructura-del-proyecto)
4. [Módulos y Servicios](#-módulos-y-servicios)
   - [Infraestructura & Base de Datos (`infra/`)](#1-infraestructura--base-de-datos-infra)
   - [Seed CLI (`services/seed_cli/`)](#2-seed-cli-servicesseed_cli)
   - [Simulador de Telemetría (`services/telemetry_simulator/`)](#3-simulador-de-telemetría-servicestelemetry_simulator)
   - [API Multiplicador (`services/multiplier_api/`)](#4-api-multiplicador-servicesmultiplier_api)
   - [Worker de Presión (`services/pressure_worker/`)](#5-worker-de-presión-servicespressure_worker---en-desarrollo)
   - [Simulador de Solicitudes (`services/request_simulator/`)](#6-simulador-de-solicitudes-servicesrequest_simulator---en-desarrollo)
   - [Procesamiento Batch (`batch/`)](#7-procesamiento-batch-batch---en-desarrollo)
5. [Puesta en Marcha Rápida](#-puesta-en-marcha-rápida)
6. [Variables de Entorno](#-variables-de-entorno)
7. [Documentación Detallada y Hoja de Ruta](#-documentación-detallada-y-hoja-de-ruta)

---

## 🚀 Visión General del Sistema

**RutaViva Mobility** resuelve el problema de tarifas fijas desacopladas de la realidad operativa, calculando dinámicamente un multiplicador tarifario (de 1.0 a 2.0) en base a:
- Oferta en tiempo real (vehículos libres en cada zona).
- Demanda reciente (solicitudes de viaje recibidas).
- Eventos meteorológicos (lluvia en mm/h).
- Eventos y contingencias especiales de la ciudad.
- Cumplimiento de normativas y trazabilidad inmutable de auditoría para cada viaje.

---

## 🏗 Arquitectura y Flujo de Datos

```mermaid
flowchart TD
    subgraph Data Sources & Seed
        A[Datos TLC / Shapefiles NYC] --> B[services/seed_cli]
        B -->|Poblamiento Inicial| PG[(PostgreSQL 16\nrutaviva_postgres)]
    end

    subgraph Ingestion & Telemetry
        PG -.->|Lee Vehículos Activos| TS[services/telemetry_simulator]
        TS -->|Eventos GPS cada 15s| RMQ[(RabbitMQ 3.12\ntelemetria.viajes)]
        RMQ -->|Consume eventos GPS| PW[services/pressure_worker\n(En desarrollo)]
    end

    subgraph State & Calculation
        RS[services/request_simulator\n(En desarrollo)] -->|Genera demanda| API[services/multiplier_api\nFastAPI :8000]
        PW -->|Actualiza zone_state y vehicle_state| PG
        API <-->|Lee zone_state & Audita tarifas| PG
    end

    subgraph Batch Analytics & Airflow
        PG -.-> Spark[batch/spark-jobs\nETL & Modelos]
        AF[batch/dags Airflow] --> Spark
    end
```

---

## 📂 Estructura del Proyecto

```text
rutaviva/
├── alembic.ini                   # Configuración del motor de migraciones Alembic
├── docker-compose.yml            # Orquestación de infraestructura local (PostgreSQL + RabbitMQ)
├── pyproject.toml / uv.lock      # Gestión moderna de dependencias con uv / Python 3.12+
├── infra/
│   └── migrations/               # Migraciones de esquema DDL (Alembic)
├── services/
│   ├── seed_cli/                 # CLI generador y poblador de catálogo, zonas y conductores
│   ├── telemetry_simulator/      # Motor de simulación GPS y publicador asíncrono en RabbitMQ
│   ├── multiplier_api/           # API REST (FastAPI) para consulta de multiplicador y auditoría
│   ├── pressure_worker/          # [Pendiente] Consumidor de RabbitMQ y calculador de presión/zona
│   └── request_simulator/        # [Pendiente] Generador simulado de solicitudes de pasajeros
├── batch/
│   ├── dags/                     # [Pendiente] DAGs de Apache Airflow (clima horario, agregaciones)
│   └── spark-jobs/               # [Pendiente] Jobs distribuidos Apache Spark (limpieza, enriquecimiento)
└── docs/                         # Documentación de arquitectura, diagramas y ADRs
```

---

## 🧩 Módulos y Servicios

### 1. Infraestructura & Base de Datos (`infra/`)
- **Tecnología**: PostgreSQL 16, Alembic, Docker Compose.
- **Función**: Administra el modelo relacional operacional (13 entidades) que gobierna el catálogo de zonas (265 zonas de NYC), conductores, vehículos, licencias, sanciones, estados en vivo (`vehicle_state`, `zone_state`), historial, reglas tarifarias y auditoría inmutable de tarifas (`fare_audit`).
- **Migraciones clave**:
  - `0001` (`esquema_01.py`): Creación completa de tablas e índices del MER operacional.
  - `1c747396d464`: Incorporación del estado `inactive` en el constraint de estados del conductor (`driver_status_check`).

### 2. Seed CLI (`services/seed_cli/`)
- **Tecnología**: Python 3.12, GeoPandas, Shapely, Faker, NumPy, SQLAlchemy 2.0.
- **Función**: Carga reproducible e idempotente de datos esenciales.
- **Operaciones**:
  - Carga el catálogo espacial de NYC Taxi Zones desde Shapefiles/CSV oficial de la TLC.
  - Genera conductores sintéticos con licencias y sanciones realistas evaluando coherencia legal.
  - Asigna flota vehicular y coordenadas geográficas iniciales válidas dentro de polígonos de zonas.
  - Inserción por lotes con cláusula `ON CONFLICT DO NOTHING`.

### 3. Simulador de Telemetría (`services/telemetry_simulator/`)
- **Tecnología**: Python 3.12, `asyncio`, `aio-pika`, GeoPandas / R-Tree Spatial Indexing.
- **Función**: Simula el movimiento autónomo de la flota (~8,000 vehículos) en intervalos de 15 segundos.
- **Operaciones**:
  - Lee vehículos registrados desde `vehicle_state`.
  - Calcula desplazamientos cinemáticos (rumbo, velocidad entre 5 y 60 km/h, perturbaciones de tráfico).
  - Determina en tiempo real en qué zona de taxi se encuentra cada vehículo usando índices espaciales R-Tree (`ZoneLocator`).
  - Publica ráfagas de telemetría en lotes de alto rendimiento hacia RabbitMQ (`telemetria.viajes`).

### 4. API Multiplicador (`services/multiplier_api/`)
- **Tecnología**: FastAPI, Pydantic v2, SQLAlchemy 2.0, PostgreSQL.
- **Función**: Punto de contacto síncrono para aplicaciones de pasajeros y conductores.
- **Endpoints disponibles**:
  - `GET /health/live` & `GET /health/ready`: Sondas de salud y conectividad con PostgreSQL.
  - `GET /zones/{zone_id}`: Consulta de metadata de la zona.
  - `GET /zones/{zone_id}/multiplier`: Entrega de la tarifa dinámica actual de la zona.
- **Garantías de Diseño**:
  - **Degradación Segura (RNF-04)**: Si `zone_state` tiene datos obsoletos (> 300 segundos) o no calculados, la API entrega multiplicador seguro `1.0` con la bandera `degraded: true` en vez de fallar.

### 5. Worker de Presión (`services/pressure_worker/` - En desarrollo)
- **Función planificada**: Consumir eventos de telemetría de RabbitMQ, contabilizar vehículos disponibles por zona, contrastar contra la demanda de viajes, calcular el índice de presión e impacto climático, y persistir `zone_state` y `zone_state_history`.

### 6. Simulador de Solicitudes (`services/request_simulator/` - En desarrollo)
- **Función planificada**: Simular la creación de viajes (`trip_request`) en distintas zonas para estresar el cálculo de demanda vs. oferta.

### 7. Procesamiento Batch (`batch/` - En desarrollo)
- **Función planificada**:
  - **DAGs Airflow**: Ingesta horaria de clima meteorológico (F3) y ejecución programada de reportes regulatorios.
  - **Jobs Apache Spark**: Limpieza, validación y enriquecimiento de millones de registros históricos de viajes (F1 Yellow Taxi Trip Data).

---

## ⚡ Puesta en Marcha Rápida

### Prerrequisitos
- Docker & Docker Compose
- Python 3.12+ (o gestor `uv`)

### 1. Levantar Infraestructura Base
```bash
# En la raíz del proyecto
docker compose up -d
```
Verifica que Postgres esté en el puerto local `5438` y RabbitMQ en `5672` (Panel web en `http://localhost:15672`, admin / admin1234).

### 2. Ejecutar Migraciones DDL
```bash
uv run alembic upgrade head
```

### 3. Poblar la Base de Datos con el Seeder
```bash
uv run python -m services.seed_cli.app.main --drivers 150
```

### 4. Iniciar la Simulación de Telemetría
```bash
uv run python -m services.telemetry_simulator.app.telemetry_generator
```

### 5. Iniciar la API del Multiplicador
```bash
uv run uvicorn services.multiplier_api.app.main:app --host 0.0.0.0 --port 8000 --reload
```
Abre la documentación interactiva en: [http://localhost:8000/docs](http://localhost:8000/docs).

---

## ⚙ Variables de Entorno

Configuradas en `.env` en la raíz del proyecto:
```env
POSTGRES_USER=dan
POSTGRES_PASSWORD=admin
POSTGRES_DB=rutaviva
POSTGRES_PORT=5438
DATABASE_URL=postgresql+psycopg://dan:admin@localhost:5438/rutaviva

RABBITMQ_URL=amqp://admin:admin1234@localhost:5672/
FRESHNESS_THRESHOLD_SECONDS=300
```

---

## 📖 Documentación Detallada y Hoja de Ruta

Para una visión profunda de las reglas de negocio, diseño de capas, esquema de bases de datos, contratos de datos y guía de futuras mejoras y extensiones, consulta:
👉 **[Documentación Técnica Integral del Sistema (docs/DOCUMENTACION_SISTEMA.md)](docs/DOCUMENTACION_SISTEMA.md)**
