---
id: auditoria-trazabilidad
title: Auditoría y Trazabilidad Inmutable
sidebar_label: Auditoría y Trazabilidad
---

# Auditoría y Trazabilidad Inmutable

Uno de los principales objetivos de negocio de RutaViva es garantizar que **cualquier tarifa cobrada pueda ser reconstruida con precisión matemática** meses o años después de realizado el viaje.

---

## 1. La Entidad `fare_audit`

Por cada registro en `trip_request`, la API persiste de forma atómica una fila en `fare_audit`:

```sql
CREATE TABLE fare_audit (
    trip_id         UUID PRIMARY KEY REFERENCES trip_request(trip_id),
    base_fare       NUMERIC(10,2) NOT NULL CHECK (base_fare mayor a 0),
    multiplier      NUMERIC(3,2)  NOT NULL CHECK (multiplier BETWEEN 1.0 AND 2.0),
    charged_fare    NUMERIC(10,2) NOT NULL CHECK (charged_fare mayor a 0),
    pressure_index  DOUBLE PRECISION NOT NULL,
    rain_mm_h       DOUBLE PRECISION NOT NULL DEFAULT 0,
    rule_version_id INTEGER NOT NULL REFERENCES tariff_rule_version(rule_version_id),
    degraded        BOOLEAN NOT NULL DEFAULT FALSE
);
```

---

## 2. Reconstrucción de Tarifas (CA-05)

El endpoint `GET /audit/{trip_id}` permite leer:
* **Tarifa Base**: Ejemplo: \15.000.
* **Multiplicador**: Ejemplo: 1.5.
* **Tarifa Cobrada**: \15.000 \times 1.5 = \22.500.
* **Factores Operacionales**: Presión = 4.0, Lluvia = 5.0 mm/h, Versión de Reglas = 1.
* **Estado de Degradación**: Indica si el cálculo provino del worker o fue un fallback seguro (`degraded = true`).

> **Principio de Auditoría**: La auditoría lee **valores históricos persistidos**, nunca recalcula en vivo, ya que un recálculo con reglas tarifarias futuras arrojaría un resultado divergente.
