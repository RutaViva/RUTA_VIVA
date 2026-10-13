# Guía: cómo crear un endpoint nuevo en `multiplier_api`

> Ubicación sugerida en el repo: `docs/guia-nuevos-endpoints.md`
> Aplica a: `services/multiplier_api/` (FastAPI + SQLAlchemy 2.0 + PostgreSQL)

## 1. Reglas de oro

1. **Una capa, una responsabilidad.** El router habla HTTP, el service decide, el repository consulta, el model describe la tabla.
2. **Las dependencias solo bajan:** `router → service → repository → model`. Nunca un router llama a un repository ni importa un model.
3. **El esquema real de la BD manda.** Los models reflejan las tablas que creó el seed/Alembic, no al revés. Si una columna no existe, no se inventa.
4. **Mapea solo las columnas que el endpoint usa.** Si luego hace falta otra, se agrega.
5. **Nada de secretos en el código.** Todo va en `.env` (y `.env` nunca se sube al repo).

## 2. Mapa de capas

```
services/multiplier_api/
├── app/
│   ├── main.py            # Ensambla la app: solo include_router, sin lógica
│   ├── core/              # config.py (settings), database.py (engine, Base, get_db)
│   ├── routers/           # HTTP: rutas, validación de path/query, códigos de estado
│   ├── services/          # Reglas de negocio y fallbacks (funciones puras si se puede)
│   ├── repositories/      # Consultas a la BD (una función = una consulta)
│   ├── models/            # Clases SQLAlchemy (una por tabla)
│   └── schemas/           # Pydantic: contrato de entrada/salida de la API
├── scripts/               # Utilidades locales (no es parte de la API)
├── tests/
├── .env                   # Local, NO versionado
└── Dockerfile
```

| Capa | Hace | NO hace |
|---|---|---|
| `routers/` | Define ruta y método, valida parámetros, traduce `None` a 404, devuelve el schema | Lógica de negocio, consultas SQL |
| `services/` | Aplica reglas (RN-xx), decide degradación, orquesta repositorios | Conocer HTTP (`HTTPException`, status codes) |
| `repositories/` | Ejecuta consultas con `Session` y devuelve models o `None` | Reglas de negocio, decidir errores |
| `models/` | Mapea tabla ↔ clase | Lógica |
| `schemas/` | Define qué entra y qué sale en JSON | Acceso a datos |

## 3. Paso a paso (con un ejemplo real: `GET /zones/{zone_id}`)

Orden recomendado: **de abajo hacia arriba**, para que cada pieza se pueda probar al terminar.

### Paso 0: Confirma el esquema real

```bash
cd services/multiplier_api
python -m scripts.inspect_db        # imprime tablas y columnas de la BD configurada
```

### Paso 1: Model (`app/models/<tabla>.py`)

```python
# app/models/zone.py
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Zone(Base):
    """Catálogo de zonas (F2)."""

    __tablename__ = "zone"            # nombre EXACTO de la tabla

    zone_id: Mapped[int] = mapped_column(primary_key=True)
    borough: Mapped[str]
    zone_name: Mapped[str]
```

- Si la tabla ya tiene un model, **reutilízalo**; no crees un segundo.
- Tipos: `TIMESTAMP` sin zona → `DateTime`; `NUMERIC(3,2)` → `Numeric(3, 2)`; `UUID` → `uuid.UUID`.

### Paso 2: Schema (`app/schemas/<recurso>.py`)

```python
# app/schemas/zone.py
from pydantic import BaseModel, ConfigDict


class NameZone(BaseModel):
    # Permite devolver directamente el objeto SQLAlchemy.
    model_config = ConfigDict(from_attributes=True)

    zone_id: int
    zone_name: str
    borough: str
```

- Un schema por contrato. No devuelvas el model crudo: el schema decide qué se expone.

### Paso 3: Repository (`app/repositories/<tabla>_repo.py`)

```python
# app/repositories/zone_repo.py
from sqlalchemy.orm import Session

from app.models.zone import Zone


def get_by_id(db: Session, zone_id: int) -> Zone | None:
    # Lectura por clave primaria: la forma más rápida de consultar.
    return db.get(Zone, zone_id)
```

- Devuelve `None` si no hay dato; **no** lanza HTTP errors.
- Para escribir: `db.add(obj)` y deja el `commit` al service (para agrupar varias escrituras en una transacción).

### Paso 4: Service (`app/services/<recurso>_service.py`)

```python
# app/services/zone_service.py
from sqlalchemy.orm import Session

from app.models.zone import Zone
from app.repositories import zone_repo


def get_zone(db: Session, zone_id: int) -> Zone | None:
    """Devuelve la zona o None si no existe en el catálogo."""
    return zone_repo.get_by_id(db, zone_id)
```

- Aquí viven las reglas (RN-xx) y los fallbacks. Si la regla es pura (entra un dato, sale otro), escríbela como función sin `db` para probarla sin base de datos.

### Paso 5: Router (`app/routers/<recurso>.py`)

```python
# app/routers/zones.py
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

- Usa `def` (síncrono), no `async def`: el acceso a BD es síncrono y FastAPI lo corre en un hilo aparte.
- Siempre define `response_model` y `tags`.

### Paso 6: Registra el router (`app/main.py`)

```python
from app.routers import health, multiplier, zones

app.include_router(zones.router)
```

Si no registras el router, el endpoint **no existe** (y no hay error, solo 404).

### Paso 7: Pruébalo

```bash
python -m uvicorn app.main:app --reload     # desde services/multiplier_api/
curl localhost:8000/zones/1                 # 200
curl localhost:8000/zones/9999              # 422
```

También puedes probar en `http://localhost:8000/docs`.

## 4. Convenciones

### Nombres
| Qué | Formato | Ejemplo |
|---|---|---|
| Archivos | `snake_case` | `zone_state_repo.py` |
| Clases (models, schemas) | `PascalCase` | `ZoneState`, `MultiplierResponse` |
| Rutas | sustantivos en plural, minúsculas, con guion | `/trip-requests`, `/zones/{zone_id}` |
| Funciones | verbo + objeto | `get_by_id`, `get_current_multiplier` |

> Un archivo por recurso en cada capa. No pongas dos cosas distintas en `multiplier.py`: si es otro recurso, es otro router.

### Códigos de error

| Código | Cuándo | Quién lo genera |
|---|---|---|
| 401 | Falta autenticación (auditoría) | `core/` (seguridad) |
| 403 | Autenticado sin rol auditor | `core/` (seguridad) |
| 404 | El recurso no existe (`trip_id`, zona fuera del catálogo) | Router, cuando el service devuelve `None` |
| 422 | Entrada inválida (rango, tipo, tarifa negativa) | FastAPI/Pydantic automáticamente |
| 503 | La API no está lista | `/health/ready` |

### Degradación segura (RNF-04)
- Si falla la lectura en PostgreSQL o el dato está obsoleto (`computed_at` > umbral), el multiplicador es **1.0 con `degraded: true`**.
- Esa lógica vive **solo** en `multiplier_service`. Ningún router ni endpoint nuevo la reimplementa: lo llama.
- Una zona que existe pero aún no tiene fila en `zone_state` → degradado, **no** 404.

### Fechas
- Las columnas son `TIMESTAMP` **sin zona horaria** y se asumen en **UTC**.
- Para comparar con "ahora": `datetime.now(timezone.utc).replace(tzinfo=None)`. Mezclar fechas con y sin zona lanza `TypeError`.
- En SQL, usa `now() AT TIME ZONE 'utc'`, no `now()` a secas.

### Seguridad
- Valida entradas con Pydantic y `Path/Query(ge=..., le=...)`. No confíes en nada que venga del cliente.
- Usa siempre el ORM o parámetros (`text(...)` con `:param`); **nunca** armes SQL concatenando strings.
- No registres (log) datos personales (nombres de conductores, placas).

### Base de datos
- **No** uses `Base.metadata.create_all()`. Las tablas las crea el seed/Alembic.
- Cambiar una tabla (agregar columna, etc.) = **migración de Alembic**, nunca editar a mano la base ni solo el model. Avisa al equipo antes.

## 5. Probar

| Qué | Cómo |
|---|---|
| A mano | `curl` o `http://localhost:8000/docs` |
| Regla de negocio pura | `pytest` en `tests/`, sin base de datos |
| Endpoint completo | `pytest` con `TestClient` y `app.dependency_overrides[get_db]` |

Ejemplo de prueba de una regla pura (no necesita BD):

```python
# tests/test_pricing.py
from app.services.pricing import multiplier_from_pressure


def test_presion_alta_da_1_8():
    assert multiplier_from_pressure(3.5) == 1.8      # RN-03
```

Cada regla de negocio (RN-xx) debe quedar trazada a código y a **al menos una prueba**.

## 6. Errores comunes

| Síntoma | Causa | Solución |
|---|---|---|
| `ModuleNotFoundError: No module named 'app'` | Ejecutas desde otra carpeta | `cd services/multiplier_api` y `python -m uvicorn app.main:app --reload` |
| `Attribute "app" not found in module` | `main.py` vacío o sin guardar | Guarda (`Ctrl+S`) y revisa que exista `app = FastAPI(...)` |
| `ValidationError ... database_url` | Falta el `.env` | Crea `.env` junto a la carpeta `app/` (ver `.env.example`) |
| `ImportError: ... partially initialized module (circular import)` | Un archivo se importa a sí mismo (autoimport del editor) | Borra ese import; `Base` se define en `core/database.py` |
| `can't subtract offset-naive and offset-aware datetimes` | Mezclas fechas con y sin zona | Ver sección "Fechas" |
| `NameError: name 'x' is not defined` al llamar un endpoint | Falta un import en el router/service | Importa el módulo (uvicorn solo lo detecta al ejecutar) |
| Mi endpoint no aparece en `/docs` | No registraste el router en `main.py` | Agrega `app.include_router(...)` |
| `connection refused` / `/health/ready` da 503 | Postgres apagado o `DATABASE_URL` incorrecta | Revisa el contenedor y el `.env` |

## 7. Checklist antes del Pull Request

- [ ] Creé model, schema, repository, service y router (en ese orden).
- [ ] El router está registrado en `main.py`.
- [ ] Las dependencias solo bajan (el router no importa repositories ni models).
- [ ] El model coincide con las columnas reales (`inspect_db`).
- [ ] Probé los casos: 200, 404 (si aplica) y 422.
- [ ] Si hay regla de negocio, tiene al menos una prueba en `tests/`.
- [ ] Cada función y bloque tiene un comentario que explica el **porqué**.
- [ ] No subí `.env` ni scripts temporales (`inspect_db.py`).
- [ ] Trabajé en una rama (`feature/<nombre>`), no directamente en `main`.

## 8. Endpoints del servicio

| Método y ruta | Estado | Capas involucradas |
|---|---|---|
| `GET /health/live`, `GET /health/ready` | Hecho | `routers/health.py` |
| `GET /zones/{zone_id}/multiplier` | Hecho | `multiplier` + `zone_state` |
| `GET /zones/{zone_id}` | Hecho | `zones` + `zone` |
| `POST /trip-requests` | Pendiente | `trip_request`, `fare_audit` (RN-07, RN-12) |
| `GET /audit/{trip_id}` | Pendiente | `fare_audit` (rol auditor, 401/403/404) |

> Antes de `POST /trip-requests`: `fare_audit` aún no tiene la columna `degraded` (pendiente en la documentación de arquitectura). Requiere migración de Alembic.