---
id: batch-spark-airflow
title: Procesamiento Batch (Spark & Airflow)
sidebar_label: Batch (Spark & Airflow)
---

# Procesamiento Batch (`batch/`)

El módulo batch contiene los trabajos analíticos distribuidos (PySpark) y los grafos de orquestación (Apache Airflow).

---

## 1. Jobs de Apache Spark (`batch/spark_jobs/`)

### `job1_clean_validate`
* Ingiere datos masivos de viajes históricos de NYC Yellow Taxi (F1) desde la capa Raw/Bronze.
* Unifica los esquemas cambiantes entre años (ej. columnas de 2019 vs. 2022).
* Aplica reglas de calidad de datos y desvía registros anómalos hacia la capa de **Quarantine** en S3:
  * Distancia recorrida menor o igual a 0 millas.
  * Tarifa base negativa o nula.
  * Duración de viaje mayor a 300 minutos o llegada anterior a la recogida.
  * Zonas de recogida/llegada fuera del catálogo de 265 zonas.
* Escribe los viajes limpios y conformados en la capa **Silver** en formato Parquet.

### `job2_enrich_model`
* Lee viajes de la capa Silver y los enriquece con clima histórico (F3) y eventos especiales (F7).
* Genera las dimensiones `DIM_DATE` y `DIM_TIME_SLOT`.
* Construye las tablas de hechos de la capa **Gold** (`FACT_TRIP`, `FACT_ZONE_INTERVAL`).

---

## 2. DAGs de Apache Airflow (`batch/dags/`)

* **DAG de Ingesta Histórica**: Ejecución idempotente que orquesta Spark Job 1 y Job 2 particionados por año y mes.
* **DAG Horario de Clima**: Consulta la API de Open-Meteo y actualiza la tabla operacional `weather_current` para que el cálculo en vivo siempre tenga el dato de precipitación sin latencia de red externa.
* **DAG de Reporte Regulatorio**: Agregación mensual automática el día 2 de cada mes con los indicadores exigidos por la autoridad de tránsito.

## 3. Ejecución y configuración de los jobs

Los scripts ejecutables están en `batch/spark_jobs/`; la configuración común
vive en `batch/spark_jobs/common/`. El entorno de `spark-submit` debe definir
`S3_BRONZE_PATH`, `S3_SILVER_PATH`, `S3_GOLD_PATH` y `S3_QUARANTINE_PATH`;
cada job exige las rutas que utiliza. Bronze se organiza por defecto así:

```text
<S3_BRONZE_PATH>/
  f1/                  # Viajes Yellow Taxi
  f3/                  # Clima histórico horario
  f7/                  # Eventos con zona y vigencia, o fecha del evento
  zone_state_history/  # Extracción de ZONE_STATE_HISTORY desde PostgreSQL
```

Se pueden sustituir las rutas predeterminadas `f1/`, `f3/`, `f7/` y
`zone_state_history/` con `S3_F1_PATH`, `S3_WEATHER_PATH`, `S3_EVENTS_PATH` y
`S3_ZONE_STATE_HISTORY_PATH`. Las entradas aceptan CSV con encabezado, JSON o
Parquet; si el formato no se deduce de la extensión, se usa CSV. Para forzarlo,
configura `F1_FORMAT`, `F3_FORMAT`, `F7_FORMAT` o
`ZONE_STATE_HISTORY_FORMAT` (`csv`, `json` o `parquet`).

S3A queda configurado en la sesión Spark. El runtime debe incluir
`hadoop-aws` compatible con la versión Hadoop de Spark; las credenciales deben
estar disponibles mediante la cadena de credenciales AWS del runtime. Usa
`AWS_REGION`/`AWS_DEFAULT_REGION` para la región, `S3_ENDPOINT` y
`S3_PATH_STYLE_ACCESS` para un endpoint S3 compatible, y `SPARK_JARS_PACKAGES`
para especificar paquetes Spark adicionales. Si alguna ruta usa `s3a://`, el
job agrega `org.apache.hadoop:hadoop-aws:3.5.0` (salvo que ya esté en
`SPARK_JARS_PACKAGES`), correspondiente a la imagen Spark 4.2.0 del proyecto;
configura `HADOOP_AWS_VERSION` si tu runtime usa otra versión de Hadoop. Los
nodos deben poder descargar el paquete o tenerlo disponible en su
caché/repositorio Maven.
`SPARK_TIMEZONE` controla la zona horaria de Spark y por defecto es
`America/New_York`, adecuada para las marcas horarias locales del dataset TLC.

Job 1 espera que F1 ya use un esquema unificado: `tpep_pickup_datetime`,
`tpep_dropoff_datetime`, `trip_distance`, `pickup_longitude`,
`pickup_latitude`, `dropoff_longitude`, `dropoff_latitude`, `fare_amount`,
`extra` y `total_amount`. `pickup_zone_id` y `dropoff_zone_id` son opcionales;
si existen, se validan entre 1 y 265. Las coordenadas se validan cuando están
presentes y son obligatorias si no hay ID de zona. No hay lógica de alias o
renombrado automático: los datos de entrada deben respetar esos nombres.
Job 2 también usa nombres canónicos: F3 contiene `weather_hour` y `rain_mm_h`;
F7 contiene `zone_id`, `starts_at` y `ends_at` (el ID puede ser nulo para un
evento de ciudad completa); el historial contiene `zone_id`, `interval_start`,
`requests`, `free_vehicles`, `pressure_index` y `estimated_wait_minutes`.
Job 2 construye `DIM_DATE`, `DIM_TIME_SLOT` (24 franjas horarias),
`DIM_WEATHER`, `DIM_ZONE`, `FACT_TRIP` y `FACT_ZONE_INTERVAL` en directorios
homónimos de Gold, en Parquet.

Para `DIM_ZONE` y la asignación de IDs por coordenadas, Job 2 reutiliza los
loaders compartidos de `services/seed_cli/app/zone_data.py`: carga el
shapefile con GeoPandas, reproyecta las geometrías a EPSG:4326 y consulta
polígonos con Shapely. `DIM_ZONE` combina los atributos geográficos con el
catálogo del seeder para conservar las 265 zonas. El shapefile actual solo
tiene polígonos para 263 IDs (faltan 264 y 265): sus nombres sí aparecen en
`DIM_ZONE`, pero no es posible asignar esas zonas usando coordenadas. Cambia
las rutas con `RUTAVIVA_ZONE_SHAPEFILE_PATH` y `RUTAVIVA_ZONE_CATALOG_PATH`.
Spark 4.2.0 usa Java 21; la imagen del proyecto instala Python 3.12 y las
dependencias del grupo `spark` desde `uv.lock` tanto en el driver como en los
ejecutores. Para el entorno local, instala el mismo grupo con
`uv sync --locked --group spark`. La UDF envía geometrías serializadas y
construye un STRtree por worker.

Los archivos F1 no contienen multiplicador dinámico ni tiempo de espera
operacional; esos campos quedan nulos en `FACT_TRIP` en lugar de inventar
valores. `extra_revenue` se calcula como `total_amount - fare_amount`. Como la
documentación aún no define un umbral cuantitativo para RN-08, el job marca
como desatendida una zona con solicitudes y cero vehículos libres. El clima se
une por hora y los eventos por zona de recogida y vigencia; un evento sin zona
se trata como evento de toda la ciudad. Las zonas de origen y llegada se
determinan con sus coordenadas y los polígonos del shapefile.

Los notebooks ya no son parte del pipeline ejecutable. Los datasets y
resultados locales existentes se conservan fuera del código en
`batch/data/local/job1_clean_validate/`; configura `S3_F1_PATH` a su
subdirectorio `raw/` si deseas procesar esos archivos en local.
Las pruebas de transformaciones están en `batch/tests/` y se ejecutan desde la
raíz del repositorio con:

```powershell
uv run --locked --group spark python -m unittest discover -s batch/tests -v
```

La imagen de Spark usa Java 21.
