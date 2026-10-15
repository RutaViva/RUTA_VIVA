# RutaViva Movilidad · `telemetry_simulator`

Simulador asíncrono de telemetría GPS para la flota de vehículos (~8,000 móviles) que emite pulsos de ubicación y estado cada 15 segundos hacia RabbitMQ, incorporando un motor configurable de inyección de defectos de calidad (HU-02).

---

## 📌 Tabla de Contenidos

1. [Propósito del Módulo](#1-propósito-del-módulo)
2. [Tareas Técnicas Cubiertas (Jira / Scrum)](#2-tareas-técnicas-cubiertas-jira--scrum)
3. [Arquitectura y Flujo de Ejecución](#3-arquitectura-y-flujo-de-ejecución)
4. [Registro de Cambios Realizados (Qué y Dónde se tocó)](#4-registro-de-cambios-realizados-qué-y-dónde-se-tocó)
5. [Explicación Detallada del Nuevo Funcionamiento](#5-explicación-detallada-del-nuevo-funcionamiento)
6. [Configuración y Variables de Entorno](#6-configuración-y-variables-de-entorno)
7. [Cómo Probar y Ejecutar](#7-cómo-probar-y-ejecutar)

---

## 1. Propósito del Módulo

El simulador cumple con el requerimiento **F4** del proyecto RutaViva y la historia de usuario **HU-02**:
* Emite mensajes JSON con el contrato oficial (`vehicle_id`, `zone_id`, `lat`, `lon`, `status`, `last_seen_at`) cada 15 segundos por vehículo.
* Publica como máximo un vehículo operativo (`available` o `busy`) por conductor; vehículos `offline` o `maintenance` no emiten telemetría.
* Marca como `offline` en el simulador a los vehículos que superan 120 segundos sin un reporte publicado correctamente.
* Mantiene a los vehículos en movimiento dentro de polígonos de zonas válidas de la ciudad mediante indexación espacial en memoria (**R-Tree / GeoPandas**).
* Inyecta **defectos de calidad controlados**:
  1. Un porcentaje configurable de vehículos que deja de reportar (*vehículos silenciosos*).
  2. Un porcentaje configurable de vehículos que reporta coordenadas *fuera de los límites de la ciudad*.

---

## 2. Tareas Técnicas Cubiertas (Jira / Scrum)

Esta implementación cubre de forma directa las siguientes tareas técnicas asignadas al módulo:

### 🔹 `RWI-38` — *movement generator within zone polygons*
- **Descripción de la tarea**: Implementar un generador de movimiento que desplace a cada vehículo de la flota manteniendo sus coordenadas físicas sincronizadas y contenidas dentro de los polígonos de zonas válidas de la ciudad.
- **Implementación**:
  - `vehicle.py`: Modela el desplazamiento cinemático según velocidad variable (5 a 60 km/h) y rumbo con pequeñas perturbaciones angulares y rebote reflexivo ante fronteras de la ciudad.
  - `zone_locator.py`: Utiliza la geometría oficial de la TLC (`taxi_zones.shp`) indexada espacialmente con R-Tree (`GeoPandas`). En cada tick evalúa el punto (lat, lon) para asignar el `zone_id` exacto.
- **Prueba asociada**: `test_los_vehiculos_siempre_se_mueven_dentro_de_la_ciudad` en `tests/test_simulator.py`.

### 🔹 `RWI-39` — *free/occupied/out-of-service state machine*
- **Descripción de la tarea**: Implementar una máquina de estados para simular la transición de los vehículos entre estados operativos: libre (`available`), ocupado (`busy`), fuera de servicio (`offline`) y mantenimiento (`maintenance`).
- **Implementación**:
  - `config.py`: Define el diccionario `PROBABILIDADES_TRANSICION` con la matriz estocástica de probabilidades de cambio de estado por tick de 15 segundos.
  - `vehicle.py`: Método `_transicionar_estado()` que evalúa probabilidades acumuladas para ejecutar transiciones markovianas realistas.
- **Prueba asociada**: `test_mensaje_tiene_los_campos_del_contrato` en `tests/test_simulator.py` (valida estados válidos en el payload).

### 🔹 `RWI-40` — *injection of "silent" vehicles and invalid coordinates*
- **Descripción de la tarea**: Implementar la inyección controlada de defectos de calidad: un porcentaje configurable de vehículos que deja de reportar telemetría y otro porcentaje que reporta coordenadas inválidas fuera del área metropolitana.
- **Implementación**:
  - `config.py`: Parámetros `SILENT_VEHICLES_PCT`, `OUT_OF_CITY_PCT`, `DEFECT_DELAY_SECONDS` y delimitación geográfica exterior `[39.00, 39.50]` lat / `[-73.00, -72.00]` lon.
  - `defects.py`: Función pura `plan_defects()` que garantiza particiones reproducibles y **estrictamente disjuntas** (`silent_ids` ∩ `out_of_city_ids` = ∅), y `out_of_city_position()`.
  - `telemetry_generator.py`: Aplica el filtro condicional en cada ciclo una vez transcurrido el retardo inicial.
- **Pruebas asociadas**: `test_porcentajes_de_defectos_son_exactos_y_disjuntos` y `test_coordenadas_defectuosas_quedan_fuera_de_la_ciudad` en `tests/test_simulator.py`.


---

## 3. Arquitectura y Flujo de Ejecución

```mermaid
flowchart TD
    subgraph Inicializacion ["1. Inicialización del Módulo"]
        DB[("PostgreSQL<br/>(vehicle_state)")] -->|"Cargar último estado"| Repo["vehicle_repository.py"]
        Repo --> Init["telemetry_generator.py"]
        Shape["taxi_zones.shp"] --> ZL["ZoneLocator<br/>(R-Tree espacial GeoPandas)"]
        Init --> ZL
        Init --> Defects["defects.py<br/>plan_defects()"]
    end

    subgraph BucleSimulacion ["2. Bucle de Simulación (cada 15s)"]
        Init --> Tick["Vehiculo.tick()"]
        Tick --> Move["Cinemática + Rebote urbano"]
        Tick --> State["Transición de Estados (Markov)"]
        Tick --> Locate["Localizar Zona Actual"]
        
        Init --> Filter{"¿Defectos Activos?<br/>(t >= DEFECT_DELAY_SECONDS)"}
        Filter -->|"En silent_ids (5%)"| Omit["Omitir del envío<br/>(Vehículo silencioso)"]
        Filter -->|"En out_of_city_ids (3%)"| Anomalous["to_payload(override_coords)<br/>(Coordenadas fuera de ciudad)"]
        Filter -->|"Flota normal (92%)"| Normal["to_payload()<br/>(Coordenadas válidas)"]
        
        Anomalous --> Batch["Agrupación en lotes<br/>(500 mensajes)"]
        Normal --> Batch
        Batch --> RMQ[("RabbitMQ<br/>Exchange: telemetria.viajes<br/>Cola: telemetria.vehiculos")]
    end
```

---

## 4. Registro de Cambios Realizados (Qué y Dónde se tocó)

A continuación se detalla cada archivo tocado o creado y el motivo del cambio:

| Archivo | Acción | Qué se tocó y Qué reemplazó |
|---|:---:|---|
| [`app/config.py`](app/config.py) | **Modificado** | - **Antes**: Solo leía `database_url` y tenía fijados `RABBITMQ_URL` con localhost sin soporte para `.env` local.<br>- **Ahora**: Incorpora lectura unificada de `.env` (local y de raíz del proyecto), agrega `SILENT_VEHICLES_PCT` (5.0%), `OUT_OF_CITY_PCT` (3.0%), `DEFECT_DELAY_SECONDS` (60s) y las coordenadas límite de anomalías fuera de la ciudad (`OUTSIDE_MIN_LAT`, `OUTSIDE_MAX_LAT`, `OUTSIDE_MIN_LON`, `OUTSIDE_MAX_LON`). |
| [`app/defects.py`](app/defects.py) | **Creado** | - **Nuevo módulo**: Implementa el modelo inmutable `DefectPlan` (con `silent_ids` y `out_of_city_ids` como `frozenset`).<br>- Provee la función pura `plan_defects()` que garantiza que los dos grupos de vehículos defectuosos sean estrictamente **disjuntos** y reproducibles.<br>- Provee `out_of_city_position()` para generar coordenadas geográficas verosímiles pero fuera del cuadrante urbano. |
| [`app/vehicle.py`](app/vehicle.py) | **Modificado** | - **Antes**: `zone_locator` era obligatorio y no se podían sobreescribir coordenadas al generar el payload JSON.<br>- **Ahora**: `zone_locator` es opcional (permite instanciar vehículos livianos en tests unitarios sin cargar shapefiles) y el método `to_payload()` acepta el parámetro `override_coords: Optional[Tuple[float, float]]` para permitir la inyección de anomalías sin descalibrar el estado físico interno del vehículo. |
| [`app/telemetry_generator.py`](app/telemetry_generator.py) | **Modificado** | - Limita el envío a vehículos operativos, omite los silenciosos y marca `offline` los que llevan más de 120 segundos sin un reporte publicado correctamente. Mantiene la inyección de coordenadas fuera de la ciudad para los vehículos seleccionados. |
| [`tests/test_simulator.py`](tests/test_simulator.py) | **Creado** | - **Nueva suite de pruebas unitarias**: Valida el contrato del mensaje JSON, la restricción urbana de la cinemática vehicular, la disyunción matemática de los conjuntos de defectos y la verificación de que las coordenadas de defecto caen estrictamente fuera de la ciudad. |
| [`../../pyproject.toml`](../../pyproject.toml) | **Modificado** | - Agrega la sección `[tool.pytest.ini_options]` con `pythonpath` configurado para ejecutar pruebas limpiamente desde cualquier nivel sin errores de importación. |

---

## 5. Explicación Detallada del Nuevo Funcionamiento

### A. Cinemática Normal y Mantenimiento dentro de Zonas
1. Al arrancar, el simulador consulta la tabla `vehicle_state` en PostgreSQL a través de `vehicle_repository.py`.
2. Para cada vehículo se inicializa un objeto `Vehiculo` con su rumbo angular, velocidad (5–60 km/h) y estado inicial (`available`, `busy`, `offline`, `maintenance`).
3. En cada tick (cada 15 segundos):
   * Se actualizan las coordenadas polares proyectadas a grados decimales.
   * Si el vehículo toca los bordes de la ciudad, "rebota" reflejando su ángulo de dirección.
   * `zone_locator.locate()` consulta el índice espacial R-Tree para actualizar su `zone_id` real.

### B. Inyección de Defectos de Calidad
1. **Planificación Idempotente**: Antes de iniciar el bucle, `plan_defects()` baraja los IDs de vehículos y separa:
   * `Total vehículos * (SILENT_VEHICLES_PCT / 100) ➔ Vehículos Silenciosos (5%)`
   * `Total vehículos * (OUT_OF_CITY_PCT / 100) ➔ Vehículos Fuera de Ciudad (3%)`
2. **Período de Calibración Inicial (`DEFECT_DELAY_SECONDS`)**:
   Durante los primeros segundos (por defecto 60 segundos), todos los vehículos reportan normalmente. Esto permite que los consumidores (como el worker de presión) reciban la flota completa y establezcan su línea base.
3. **Disparo de Anomalías**:
   Una vez transcurrido el retardo, el generador activa los defectos:
   * **Silenciosos**: Si `v.id in defect_plan.silent_ids`, se omite en el payload. Pasados 120 segundos sin un reporte publicado correctamente, el simulador cambia su estado local a `offline` y deja de procesarlo como operativo. RN-10 requiere además que el consumidor de telemetría persista/compruebe `last_seen_at`; el `pressure_worker` todavía está pendiente de implementación.
   * **Fuera de la ciudad**: Si `v.id in defect_plan.out_of_city_ids`, `v.to_payload(override_coords=out_coords)` envía coordenadas en el rango `[39.00, 39.50]` lat / `[-73.00, -72.00]` lon. El consumidor deberá descartar estos registros por estar fuera de zona válida.

---

## 6. Configuración y Variables de Entorno

El simulador lee su configuración del archivo `services/telemetry_simulator/.env` (o en su defecto de `.env` en la raíz del proyecto):

```env
# Conexión a Base de Datos (para carga inicial)
DATABASE_URL=postgresql+psycopg://admin:admin1234@localhost:5438/rutaviva_db

# Broker de Mensajería RabbitMQ
RABBITMQ_URL=amqp://admin:admin1234@localhost:5672/

# Parámetros de Defectos de Calidad (HU-02)
SILENT_VEHICLES_PCT=5.0        # Porcentaje de vehículos silenciosos
OUT_OF_CITY_PCT=3.0            # Porcentaje de vehículos fuera de la ciudad
DEFECT_DELAY_SECONDS=60        # Segundos antes de activar los defectos
```

---

## 7. Cómo Probar y Ejecutar

### Ejecución de Pruebas Unitarias
Para correr la suite de pruebas automatizadas del simulador:
```bash
# Desde la raíz del proyecto
pytest services/telemetry_simulator/tests/ -v
```

Resultado esperado:
```text
test_mensaje_tiene_los_campos_del_contrato PASSED
test_los_vehiculos_siempre_se_mueven_dentro_de_la_ciudad PASSED
test_porcentajes_de_defectos_son_exactos_y_disjuntos PASSED
test_coordenadas_defectuosas_quedan_fuera_de_la_ciudad PASSED
4 passed
```

### Ejecutar el Simulador en Vivo
Asegúrate de que PostgreSQL y RabbitMQ estén levantados (`docker compose up -d`) y que la base tenga datos del seeder:
```bash
# Ejecutar el bucle de telemetría
python -m services.telemetry_simulator.app.telemetry_generator
```
Verás en consola la carga de vehículos, el plan de defectos configurado y la publicación periódica en lotes de 500 mensajes cada 15 segundos hacia la cola `telemetria.vehiculos`.
