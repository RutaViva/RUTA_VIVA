# RutaViva Movilidad · `multiplier_api`

API (FastAPI + SQLAlchemy 2.0 + PostgreSQL) que entrega el multiplicador de tarifa vigente por zona, registra solicitudes de viaje y permite auditar tarifas.

> Ubicación sugerida: `services/multiplier_api/README.md`
> Todos los comandos se ejecutan desde `services/multiplier_api/` salvo que se indique otra cosa.

## Contenido

1. [Arranque rápido (un solo comando)](#1-arranque-rápido-un-solo-comando)
2. [Cómo se construyó la API (paso a paso)](#2-cómo-se-construyó-la-api-paso-a-paso)
3. [Guía para crear un endpoint nuevo](#3-guía-para-crear-un-endpoint-nuevo)
4. [Convenciones](#4-convenciones)
5. [Errores comunes](#5-errores-comunes)
6. [Checklist del Pull Request](#6-checklist-del-pull-request)
7. [Endpoints del servicio](#7-endpoints-del-servicio)

---

## 1. Arranque rápido (un solo comando)

```bash
bash services/multiplier_api/run_dev.sh
```

El script `run_dev.sh` hace, en orden:

| # | Qué hace | Equivale a |
|---|---|---|
| 1 | Crea y activa el entorno virtual `rutaviva/.venv` | `python3 -m venv .venv && source .venv/bin/activate` |
| 2 | Instala dependencias | `uv pip install -r requirements.txt` (o `pip`) |
| 3 | Verifica el `.env` (lo copia de `.env.example` si falta) | `cp .env.example .env` |
| 4 | Levanta Postgres y espera hasta que acepte conexiones | `docker compose -f infra/docker-compose.yml up -d` |
| 5 | Imprime tablas y columnas de la BD | `python -m scripts.inspect_db` |
| 6 | Arranca la API con recarga automática | `python -m uvicorn app.main:app --reload` |

Variables opcionales:

```bash
SKIP_DB=1 bash services/multiplier_api/run_dev.sh        # la BD ya está corriendo
SKIP_INSPECT=1 bash services/multiplier_api/run_dev.sh   # no imprimir el esquema
PORT=8001 bash services/multiplier_api/run_dev.sh        # otro puerto
```

Cuando termine, abre `http://localhost:8000/docs`.

---

## 2. Cómo se construyó la API (paso a paso)

Orden en que se creó cada pieza. La columna **Depende de** indica qué paso debe existir antes.

### Paso 0: Requisitos previos
- Python 3.12, Docker y (opcional) `uv`.
- Postgres con el esquema y la semilla (seed) ya cargados.

### Paso 1: Entorno y dependencias

```bash
cd services/multiplier_api
python3 -m venv ../../.venv
source ../../.venv/bin/activate
uv pip install -r requirements.txt      # o: pip install -r requirements.txt
```

`requirements.txt`:

```text
fastapi
uvicorn[standard]
sqlalchemy>=2.0
psycopg[binary]
pydantic-settings
```

> El archivo se llama `requirements.txt` (con **s**).

### Pasos 2 a 10: archivos del proyecto

| # | Archivo | Depende de | Qué hace | Cómo verificar |
|---|---|---|---|---|
| 2 | `app/core/config.py` + `.env` | nada | Lee `DATABASE_URL` y `FRESHNESS_THRESHOLD_SECONDS` del entorno | `python -c "from app.core.config import settings; print(settings)"` |
| 3 | `app/core/database.py` | Paso 2 (`settings`) | Crea `engine`, `SessionLocal`, `Base` y la dependencia `get_db` | `python -c "from app.core.database import engine"` |
| 4 | `app/routers/health.py` | Paso 3 (`get_db`) | `GET /health/live` y `GET /health/ready` (este valida la BD) | `curl localhost:8000/health/ready` |
| 5 | `app/models/zone_state.py` | Paso 3 (`Base`) | Mapea la tabla `zone_state` | Importa sin error |
| 6 | `app/schemas/multiplier.py` | nada | Contrato de respuesta `MultiplierResponse` | Importa sin error |
| 7 | `app/repositories/zone_state_repo.py` | Paso 5 (`ZoneState`) | Lectura de `zone_state` por clave primaria | Importa sin error |
| 8 | `app/services/multiplier_service.py` y `app/routers/multiplier.py` | Pasos 2, 6 y 7 | Regla de degradación segura y el endpoint del multiplicador | `curl localhost:8000/zones/2/multiplier` |
| 9 | `app/main.py` | Pasos 4 y 8 (routers) | Crea `app` y registra los routers. Crear también los `__init__.py` vacíos en `app/` y en cada subcarpeta | `python -m uvicorn app.main:app --reload` |
| 10 | `scripts/inspect_db.py` | Paso 3 (`engine`) | Imprime tablas y columnas de la BD configurada | `python -m scripts.inspect_db` |

> **Ojo con el paso 10:** la carpeta `scripts/` va dentro de `multiplier_api/`, **al lado** de `app/` (no dentro de ella). Y el archivo se llama `inspect_db.py`, no `inspect.py` (ese nombre choca con un módulo estándar de Python). Es una herramienta local: no se sube al repo.

### Pasos 11 a 13: ajuste al esquema real y endpoint de zonas

| # | Qué | Detalle |
|---|---|---|
| 11 | Ajustar `zone_state` al esquema real | `computed_at` es `TIMESTAMP` **sin zona** y `multiplier` es `NUMERIC(3,2)`. En el servicio se compara contra `datetime.now(timezone.utc).replace(tzinfo=None)` |
| 12 | Zona sin fila en `zone_state` ≠ 404 | Si la zona existe en `zone` pero aún no hay cálculo, responde `1.0` con `degraded: true`. El 404 es solo para zonas que no existen. Requiere `models/zone.py` y `repositories/zone_repo.py` |
| 13 | `GET /zones/{zone_id}` | `models/zone.py`, `schemas/zone.py`, `repositories/zone_repo.py`, `services/zone_service.py`, `routers/zones.py` y registrarlo en `main.py` (ver sección 3) |

### Comandos de uso diario

```bash
# Levantar la base de datos
docker compose -f infra/docker-compose.yml up -d

# Ver el esquema real de la BD
python -m scripts.inspect_db

# Correr la API
python -m uvicorn app.main:app --reload

# Probar
curl localhost:8000/health/live
curl localhost:8000/health/ready
curl localhost:8000/zones/1
curl localhost:8000/zones/1/multiplier
```

---

## 3. Guía para crear un endpoint nuevo

### 3.1 Reglas de oro

1. **Una capa, una responsabilidad.** El router habla HTTP, el service decide, el repository consulta, el model describe la tabla.
2. **Las dependencias solo bajan:** `router → service → repository → model`. Un router nunca llama a un repository ni importa un model.
3. **El esquema real de la BD manda.** Los models reflejan las tablas del seed/Alembic, no al revés.
4. **Mapea solo las columnas que el endpoint usa.**
5. **Nada de secretos en el código.** Todo va en `.env`, y `.env` nunca se sube.

### 3.2 Mapa de capas

```
services/multiplier_api/
├── app/
│   ├── main.py            # Ensambla la app: solo include_router, sin lógica
│   ├── core/              # config.py (settings), database.py (engine, Base, get_db)
│   ├── routers/           # HTTP: rutas, validación de path/query, códigos de estado
│   ├── services/          # Reglas de negocio y fallbacks
│   ├── repositories/      # Consultas a la BD (una función = una consulta)
│   ├── models/            # Clases SQLAlchemy (una por tabla)
│   └── schemas/           # Pydantic: contrato de entrada/salida
├── scripts/               # Utilidades locales (no son parte de la API)
├── tests/
├── .env                   # Local, NO versionado
├── run_dev.sh             # Arranque con un comando
└── Dockerfile
```

| Capa | Hace | NO hace |
|---|---|---|
| `routers/` | Define ruta y método, valida parámetros, traduce `None` a 404 | Lógica de negocio, consultas SQL |
| `services/` | Aplica reglas (RN-xx), decide degradación, orquesta repositorios | Conocer HTTP (`HTTPException`) |
| `repositories/` | Ejecuta consultas y devuelve models o `None` | Reglas de negocio, decidir errores |
| `models/` | Mapea tabla ↔ clase | Lógica |
| `schemas/` | Define qué entra y qué sale en JSON | Acceso a datos |

### 3.3 Paso a paso (ejemplo real: `GET /zones/{zone_id}`)

Se construye **de abajo hacia arriba**, para poder probar cada pieza al terminarla.

**Paso 0: confirma el esquema real**

```bash
python -m scripts.inspect_db
```

**Paso 1: Model** (`app/models/zone.py`)

```python
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Zone(Base):
    """Catálogo de zonas (F2)."""

    __tablename__ = "zone"            # nombre EXACTO de la tabla

    zone_id: Mapped[int] = mapped_column(primary_key=True)
    borough: Mapped[str]
    zone_name: Mapped[str]
```

Si la tabla ya tiene model, reutilízalo. Tipos: `TIMESTAMP` sin zona → `DateTime`; `NUMERIC(3,2)` → `Numeric(3, 2)`; `UUID` → `uuid.UUID`.

**Paso 2: Schema** (`app/schemas/zone.py`)

```python
from pydantic import BaseModel, ConfigDict


class NameZone(BaseModel):
    # Permite devolver directamente el objeto SQLAlchemy.
    model_config = ConfigDict(from_attributes=True)

    zone_id: int
    zone_name: str
    borough: str
```

**Paso 3: Repository** (`app/repositories/zone_repo.py`)

```python
from sqlalchemy.orm import Session

from app.models.zone import Zone


def get_by_id(db: Session, zone_id: int) -> Zone | None:
    # Lectura por clave primaria: la forma más rápida de consultar.
    return db.get(Zone, zone_id)
```

Devuelve `None` si no hay dato; no lanza errores HTTP. Para escribir: `db.add(obj)` y deja el `commit` al service, para agrupar varias escrituras en una transacción.

**Paso 4: Service** (`app/services/zone_service.py`)

```python
from sqlalchemy.orm import Session

from app.models.zone import Zone
from app.repositories import zone_repo


def get_zone(db: Session, zone_id: int) -> Zone | None:
    """Devuelve la zona o None si no existe en el catálogo."""
    return zone_repo.get_by_id(db, zone_id)
```

Aquí viven las reglas y los fallbacks. Si la regla es pura (entra un dato, sale otro), escríbela sin `db` para probarla sin base de datos.

**Paso 5: Router** (`app/routers/zones.py`)

```python
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.zone import NameZone
from app.services import zone_service

router = APIRouter(prefix="/zones", tags=["zones"])


@router.get("/{zone_id}", response_model=NameZone)
def read_zone(
    zone_id: int = Path(ge=1, le=265),      # fuera de rango → 422 automático
    db: Session = Depends(get_db),          # una sesión por petición
):
    zone = zone_service.get_zone(db, zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="zone not found")
    return zone
```

Usa `def` (síncrono), no `async def`: el acceso a BD es síncrono y FastAPI lo corre en un hilo aparte. Define siempre `response_model` y `tags`.

**Paso 6: registra el router** (`app/main.py`)

```python
from app.routers import health, multiplier, zones

app.include_router(zones.router)
```

Si no lo registras, el endpoint no existe (y no da error, solo 404).

**Paso 7: pruébalo**

```bash
curl localhost:8000/zones/1       # 200
curl localhost:8000/zones/9999    # 422
```

También en `http://localhost:8000/docs`.

---

## 4. Convenciones

### Nombres

| Qué | Formato | Ejemplo |
|---|---|---|
| Archivos | `snake_case` | `zone_state_repo.py` |
| Clases (models, schemas) | `PascalCase` | `ZoneState`, `MultiplierResponse` |
| Rutas | sustantivos en plural, minúsculas, con guion | `/trip-requests`, `/zones/{zone_id}` |
| Funciones | verbo + objeto | `get_by_id`, `get_current_multiplier` |

Un archivo por recurso en cada capa. Si es otro recurso, es otro router (no mezcles cosas en `multiplier.py`).

### Códigos de error

| Código | Cuándo | Quién lo genera |
|---|---|---|
| 401 | Falta autenticación (auditoría) | `core/` (seguridad) |
| 403 | Autenticado sin rol auditor | `core/` (seguridad) |
| 404 | El recurso no existe (`trip_id`, zona fuera del catálogo) | Router, cuando el service devuelve `None` |
| 422 | Entrada inválida (rango, tipo, tarifa negativa) | FastAPI/Pydantic, automático |
| 503 | La API no está lista | `/health/ready` |

### Degradación segura (RNF-04)
- Si falla la lectura en PostgreSQL o el dato está obsoleto (`computed_at` mayor al umbral), el multiplicador es **1.0 con `degraded: true`**.
- Esa lógica vive **solo** en `multiplier_service`. Los endpoints nuevos la llaman, no la reimplementan.
- Una zona que existe pero aún no tiene fila en `zone_state` → degradado, no 404.
- `FRESHNESS_THRESHOLD_SECONDS` (por defecto 300) define cuántos segundos puede tener el dato para considerarse fresco.

### Fechas
- Las columnas son `TIMESTAMP` **sin zona horaria** y se asumen en **UTC**.
- Para comparar con "ahora": `datetime.now(timezone.utc).replace(tzinfo=None)`. Mezclar fechas con y sin zona lanza `TypeError`.
- En SQL usa `now() AT TIME ZONE 'utc'`, no `now()` a secas.

### Seguridad
- Valida entradas con Pydantic y `Path/Query(ge=..., le=...)`.
- Usa el ORM o parámetros (`text(...)` con `:param`); **nunca** armes SQL concatenando strings.
- No registres (log) datos personales (nombres de conductores, placas).

### Base de datos
- No uses `Base.metadata.create_all()`: las tablas las crean el seed y Alembic.
- Cambiar una tabla (agregar una columna, etc.) = **migración de Alembic**, nunca editar a mano la base. Avisa al equipo antes.

### Probar

| Qué | Cómo |
|---|---|
| A mano | `curl` o `http://localhost:8000/docs` |
| Regla de negocio pura | `pytest` en `tests/`, sin base de datos |
| Endpoint completo | `pytest` con `TestClient` y `app.dependency_overrides[get_db]` |

```python
# tests/test_pricing.py  (ejemplo: la función la implementa quien haga RN-03)
from app.services.pricing import multiplier_from_pressure


def test_presion_alta_da_1_8():
    assert multiplier_from_pressure(3.5) == 1.8      # RN-03
```

Cada regla de negocio (RN-xx) debe quedar trazada a código y a **al menos una prueba**.

---

## 5. Errores comunes

| Síntoma | Causa | Solución |
|---|---|---|
| `ModuleNotFoundError: No module named 'app'` | Ejecutas desde otra carpeta | `cd services/multiplier_api` y `python -m uvicorn app.main:app --reload` |
| `Attribute "app" not found in module` | `main.py` vacío o sin guardar | Guarda (`Ctrl+S`) y revisa que exista `app = FastAPI(...)` |
| `ValidationError ... database_url` | Falta el `.env` | Crea `.env` junto a la carpeta `app/` |
| `ImportError: ... circular import` | Un archivo se importa a sí mismo (autoimport del editor) | Borra ese import; `Base` se define en `core/database.py` |
| `can't subtract offset-naive and offset-aware datetimes` | Mezclas fechas con y sin zona | Ver "Fechas" |
| `NameError: name 'x' is not defined` al llamar un endpoint | Falta un import en el router o service | Importa el módulo (uvicorn solo lo detecta al ejecutar) |
| Mi endpoint no aparece en `/docs` | No registraste el router | `app.include_router(...)` en `main.py` |
| `No module named scripts.inspect_db` | El archivo se llama distinto o falta `scripts/__init__.py` | Debe ser `scripts/inspect_db.py` |
| `connection refused` / `/health/ready` da 503 | Postgres apagado o `DATABASE_URL` incorrecta | Revisa el contenedor y el `.env` |
| `/zones/{id}/multiplier` da `degraded: true` con datos del seed | `computed_at` más viejo que el umbral | Es esperado: el `pressure-worker` es quien lo mantiene al día |

---

## 6. Checklist del Pull Request

- [ ] Creé model, schema, repository, service y router (en ese orden).
- [ ] El router está registrado en `main.py`.
- [ ] Las dependencias solo bajan (el router no importa repositories ni models).
- [ ] El model coincide con las columnas reales (`inspect_db`).
- [ ] Probé los casos: 200, 404 (si aplica) y 422.
- [ ] Si hay regla de negocio, tiene al menos una prueba en `tests/`.
- [ ] Cada función y bloque tiene un comentario que explica el **porqué**.
- [ ] No subí `.env` ni scripts temporales.
- [ ] Trabajé en una rama (`feature/<nombre>`), no directamente en `main`.

---

## 7. Endpoints del servicio

| Método y ruta | Estado | Capas involucradas | Propósito |
|---|:---:|---|---|
| `GET /health` / `GET /health/live` | ✅ Hecho | `routers/health.py` | Liveness probe para orquestadores y balanceadores |
| `GET /health/ready` | ✅ Hecho | `routers/health.py` + DB | Readiness probe (valida conexión a PostgreSQL) |
| `GET /zones/{zone_id}/multiplier` | ✅ Hecho | `multiplier_service` + `zone_state_repo` | Consulta el multiplicador vigente (con degradación segura RNF-04) |
| `GET /zones/{zone_id}` | ✅ Hecho | `zone_service` + `zone_repo` | Detalle geográfico de la zona TLC |
| `POST /trip-requests` | ✅ Hecho | `trip_request_service` + `trip_request_repo` | Crea solicitud de viaje y congela atómicamente la tarifa (RN-07, RN-12) |
| `POST /trip-requests/{trip_id}/assign` | ✅ Hecho | `trip_request_service` | Marca la solicitud como asignada a un conductor |
| `POST /trip-requests/{trip_id}/cancel` | ✅ Hecho | `trip_request_service` | Cancela la solicitud de viaje |
| `GET /audit/{trip_id}` | ✅ Hecho | `audit_service` + `fare_audit_repo` | Reconstruye la tarifa matemáticamente con rol auditor (RF-04, RNF-06, CA-05) |

---

## 8. Casos de Uso y Ejemplos de Petición

### 8.1 Crear Solicitud de Viaje (`POST /trip-requests`)
- **Qué se hizo**: Endpoint transaccional que recibe la zona de origen y la tarifa base estimada.
- **Cómo se hizo**: Consulta el multiplicador vigente en ese segundo exacto (`requested_at`), calcula `charged_fare = base_fare * multiplier`, e inserta en `trip_request` y `fare_audit` dentro de una misma transacción ACID.
- **Por qué se hizo**: Cumple **RN-07** (la tarifa cobrada se congela en la solicitud, no en la asignación) y **RN-12** (registro inmutable obligatorio).

#### Opción A: Con tarifa base explícita
```bash
curl -X POST http://localhost:8000/trip-requests \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": 1,
    "base_fare": 15.00
  }'
```

#### Opción B: Con cálculo automático de tarifa base (RN-01)
Si no envías `base_fare`, la API calcula automáticamente la tarifa base fija:
$$\text{Base} = \$1.50 + (\$0.35 \times \text{km}) + (\$0.15 \times \text{min})$$

```bash
curl -X POST http://localhost:8000/trip-requests \
  -H "Content-Type: application/json" \
  -d '{
    "origin_zone_id": 1,
    "destination_zone_id": 2,
    "estimated_distance_km": 7.5,
    "estimated_duration_min": 18.0
  }'
```

**Respuesta exitosa (`201 Created`):**
```json
{
  "trip_id": "44342d14-d30d-4552-b1d1-933e87f947c0",
  "zone_id": 1,
  "requested_at": "2026-10-18T22:56:51.819774Z",
  "status": "created",
  "base_fare": 6.82,
  "multiplier": 1.80,
  "charged_fare": 12.28,
  "degraded": false
}
```

---

### 8.2 Reconstruir Auditoría de Tarifa (`GET /audit/{trip_id}`)
- **Qué se hizo**: Endpoint protegido para reconstrucción histórica de la tarifa cobrada.
- **Cómo se hizo**: Recupera la fila correspondiente en `fare_audit` validando las credenciales de auditor mediante cabeceras flexibles (`X-User-Role: auditor` / `X-Auditor-Role: auditor` o `X-Audit-Token` / `X-Auditor-Key`).
- **Por qué se hizo**: Cumple **RF-04** (API de auditoría), **RNF-05** (reconstrucción de cualquier viaje en 24 meses), **RNF-06** (seguridad por rol auditor) y **CA-05**.

```bash
curl -X GET http://localhost:8000/audit/44342d14-d30d-4552-b1d1-933e87f947c0 \
  -H "X-User-Role: auditor" \
  -H "X-Audit-Token: audit-secret-token"
```

**Respuesta exitosa (`200 OK`):**
```json
{
  "trip_id": "44342d14-d30d-4552-b1d1-933e87f947c0",
  "base_fare": 6.82,
  "multiplier": 1.80,
  "charged_fare": 12.28,
  "pressure_index": 4.0,
  "rain_mm_h": 0.0,
  "rule_version_id": 1,
  "degraded": false
}
```

**Respuesta sin autorización (`403 Forbidden`):**
```bash
curl -X GET http://localhost:8000/audit/44342d14-d30d-4552-b1d1-933e87f947c0
```
```json
{
  "detail": "Acceso denegado: se requieren credenciales válidas de rol auditor (RNF-06)."
}
```