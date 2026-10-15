---
id: resumen
title: Módulos y Servicios del Sistema
sidebar_label: Resumen de Módulos
---

# Catálogo de Módulos y Microservicios

El repositorio de RutaViva está organizado en microservicios y módulos modulares desacoplados:

| Módulo | Directorio | Tecnología | Estado | Responsabilidad Principal |
|---|---|---|:---:|---|
| **Infraestructura** | `infra/` | PostgreSQL 16, Alembic, Docker | ✅ Activo | Esquema DDL operacional y migraciones versionadas. |
| **Seed CLI** | `services/seed_cli/` | Python 3.12, GeoPandas, Faker | ✅ Activo | Ingesta de catálogo de zonas y generación determinista de flota. |
| **Simulador de Telemetría** | `services/telemetry_simulator/` | Python 3.12, `aio-pika`, R-Tree | ✅ Activo | Emisión de pulsos GPS c/ 15s a RabbitMQ con defectos (`HU-02`). |
| **API Multiplicador** | `services/multiplier_api/` | FastAPI, SQLAlchemy 2.0, Pydantic | 🔄 En evolución | Consulta de multiplicador en p95 menor a 150 ms con degradación segura. |
| **Pressure Worker** | `services/pressure_worker/` | Python 3.12, RabbitMQ Consumer | ⏳ En desarrollo | Consumo de telemetría y cálculo de presión en ventana deslizante. |
| **Simulador de Solicitudes** | `services/request_simulator/` | Python 3.12 | ⏳ En desarrollo | Generador de ráfagas de demanda para estresar la API (`HU-01`). |
| **Batch Analytics** | `batch/` | Apache Spark, Apache Airflow | ⏳ En desarrollo | Procesamiento Medallón (Bronze -> Gold) y DAGs de clima. |
