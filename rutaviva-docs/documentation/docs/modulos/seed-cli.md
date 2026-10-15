---
id: seed-cli
title: Módulo Seed CLI
sidebar_label: Seed CLI (seed_cli/)
---

# Módulo Seed CLI (`services/seed_cli/`)

Herramienta de línea de comandos para el poblamiento determinista, idempotente y masivo de la base de datos operacional.

---

## 1. Responsabilidades

* Carga el catálogo espacial de zonas desde los Shapefiles oficiales de la TLC (`taxi_zones.shp`) y `taxi_zone_lookup.csv`.
* Genera conductores sintéticos con nombres en inglés (`Faker`) y UUIDs reproducibles mediante semillas configuradas (`SEED`, `NP_SEED`).
* Asigna licencias y sanciones evaluando la coherencia legal mediante `apply_driver_status()` (RN-09).
* Genera vehículos con matrículas únicas y asigna su estado inicial (`available`, `busy`, `offline`, `maintenance`) dentro de las zonas de la ciudad.

---

## 2. Inserción Masiva Idempotente

El seeder ejecuta las inserciones en bloques de 5,000 registros utilizando la directiva de PostgreSQL:
```python
statement = pg_insert(model_cls).on_conflict_do_nothing()
```
Esto garantiza que si el script se ejecuta dos veces, no se produzcan errores por colisión de claves ni duplicación de registros.

---

## 3. Uso

```bash
# Ejecutar seeding de 150 conductores y su flota asociada
uv run python -m services.seed_cli.app.main --drivers 150

# Limpiar las tablas antes de poblar (TRUNCATE)
uv run python -m services.seed_cli.app.main --clean --drivers 150
```
