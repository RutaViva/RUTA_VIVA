---
id: multiplier-api
title: API de Multiplicador y Auditoría
sidebar_label: Multiplier API (multiplier_api/)
---

# API de Multiplicador y Tarifas (`services/multiplier_api/`)

Microservicio REST desarrollado en **FastAPI** encargado de entregar el multiplicador de tarifa vigente por zona, registrar solicitudes de viaje y permitir la auditoría de tarifas cobradas.

---

## 1. Arquitectura en Capas

El servicio sigue estrictamente el patrón de dependencias unidireccionales:
`routers` ➔ `services` ➔ `repositories` ➔ `models`

```mermaid
flowchart TD
    Router[app/routers/ - Controladores HTTP & Códigos Status] --> Service[app/services/ - Reglas Puras & Fallbacks]
    Service --> Repo[app/repositories/ - Consultas SQLAlchemy]
    Repo --> Model[app/models/ - Clases ORM Base]
    Router -.-> Schema[app/schemas/ - Validación Pydantic In/Out]
```

* **`routers/`**: Maneja peticiones HTTP, validación de parámetros (Path/Query) y códigos de estado.
* **`services/`**: Aplica reglas de negocio y la política de degradación segura.
* **`repositories/`**: Consultas directas de lectura/escritura en PostgreSQL con SQLAlchemy.
* **`models/`**: Clases ORM mapeadas a las tablas de la base de datos.
* **`schemas/`**: Modelos Pydantic para serialización y validación estricta de payloads JSON.

---

## 2. Endpoints del Servicio

| Método | Ruta | Actor / Uso | Descripción | Respuesta Exitosa |
|---|---|---|---|:---:|
| `GET` | `/health/live` | ALB / K8s | Sonda de vida del contenedor | `{"status": "alive"}` (200) |
| `GET` | `/health/ready` | ALB / Ops | Sonda de preparación (valida conexión a PostgreSQL) | `{"status": "ready"}` (200 / 503) |
| `GET` | `/zones/{zone_id}` | Apps / Ops | Consulta catálogo y metadata de una zona | `{"zone_id": 1, ...}` (200) |
| `GET` | `/zones/{zone_id}/multiplier` | Pasajeros | Multiplicador de tarifa dinámico vigente | `{"multiplier": 1.25, ...}` (200) |
| `POST` | `/trip-requests` | Pasajeros / Simulator | Crea solicitud, fija multiplicador y audita | `{"trip_id": "...", ...}` (201) |
| `POST` | `/trip-requests/{trip_id}/complaints` | Pasajero / Operaciones | Registra una queja categorizada sin datos personales ni texto libre | `{"complaint_id": "...", "category": "service", ...}` (201) |
| `GET` | `/audit/{trip_id}` | Auditor Interno | Reconstruye el cálculo exacto de la tarifa | `{"base_fare": 15.0, ...}` (200) |

---

## 3. Diagramas de Secuencia (Flujos de Trabajo)

### 3.1 Solicitud de Viaje (`POST /trip-requests`)

```mermaid
sequenceDiagram
  participant App as App de pasajeros
  participant ALB as ALB
  participant API as multiplier-api
  participant PG as PostgreSQL
  participant MQ as RabbitMQ
  App->>ALB: POST solicitud de viaje (zona_id, base_fare)
  ALB->>API: reenvía solicitud
  API->>PG: lee ZONE_STATE de la zona
  PG-->>API: multiplier y computed_at
  Note over API: Si falla lectura o dato es viejo (>300s), usa 1.0 y degraded: true
  API->>PG: guarda TRIP_REQUEST y FARE_AUDIT en una transacción
  API->>MQ: publica evento de solicitud para conteo de demanda
  API-->>ALB: tarifa base, multiplicador y tarifa cobrada
  ALB-->>App: respuesta 201 Created
```

### 3.2 Auditoría de Tarifa (`GET /audit/{trip_id}`)

```mermaid
sequenceDiagram
  participant AUD as Auditor
  participant ALB as ALB
  participant API as multiplier-api
  participant PG as PostgreSQL
  AUD->>ALB: GET auditoría de trip_id (con token / credenciales)
  ALB->>API: reenvía solicitud
  Note over API: Valida rol auditor (401 si falta token, 403 si rol inválido)
  API->>PG: lee FARE_AUDIT por trip_id
  PG-->>API: base, multiplicador, tarifa cobrada, presión, lluvia y rule_version_id
  Note over API: Si trip_id no existe retorna 404
  API-->>ALB: detalle inmutable para reconstrucción de tarifa
  ALB-->>AUD: respuesta 200 OK
```

### 3.3 Queja de una solicitud (`POST /trip-requests/{trip_id}/complaints`)

El cuerpo acepta únicamente una categoría: `service`, `fare`, `safety` u `other`.
El endpoint valida que exista la solicitud; PostgreSQL genera `complaint_id` y
`created_at`. No se reciben notas, nombres ni otros datos personales. Si la
solicitud no existe, la API responde `404`; una categoría no permitida o campos
adicionales se rechazan con `422`.

La tabla `service_complaint` se crea en la base operacional existente mediante
una migración Alembic. Antes de desplegar la API, aplica la migración contra la
base configurada:

```powershell
uv run --locked alembic upgrade head
```

RN-11 cuenta cada registro por mes de `created_at` y distrito de origen
asociado a `trip_id`.

---

## 4. Degradación Segura (RNF-04)

Si la consulta a PostgreSQL falla o el timestamp `computed_at` excede `FRESHNESS_THRESHOLD_SECONDS` (300 segundos):
* La API **nunca responde con error 500**.
* Devuelve un multiplicador neutro **`1.0`** con la bandera **`degraded: true`**.
* Si la zona no existe en el catálogo maestro, retorna `404 Not Found`.
