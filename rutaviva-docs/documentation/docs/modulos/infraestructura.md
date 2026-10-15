---
id: infraestructura
title: Módulo de Infraestructura y Base de Datos
sidebar_label: Infraestructura (infra/)
---

# Módulo de Infraestructura (`infra/`)

Administra la persistencia relacional operacional y el versionamiento del esquema mediante **Alembic**.

---

## 1. Migraciones de Esquema

El historial de migraciones se encuentra en `infra/migrations/versions/`:

* **`0001` (`esquema_01.py`)**:
  * Crea las 13 tablas operacionales del MER.
  * Define restricciones `CHECK` (multiplicador entre 1.0 y 2.0, lluvia positiva, tarifas mayor a 0).
  * Crea índices compuestos en claves calientes: `ix_vehicle_state_zone (zone_id, status)` para el conteo veloz de vehículos libres.
* **`1c747396d464` (`add_inactive_to_driver_status_check.py`)**:
  * Actualiza la restricción de estados de conductor para admitir `'active'`, `'inactive'` y `'suspended'`.

---

## 2. Docker Compose Local

Define los servicios indispensables en local:
```yaml
services:
  db:
    image: postgres:16
    container_name: rutaviva_postgres
    ports:
      - "5438:5432" # Expuesto en el puerto 5438 del host
  rabbitmq:
    image: rabbitmq:3.12-management
    container_name: rabbitmq-telemetria
    ports:
      - "5672:5672"   # Puerto de mensajería AMQP
      - "15672:15672" # Dashboard Web de administración
```
