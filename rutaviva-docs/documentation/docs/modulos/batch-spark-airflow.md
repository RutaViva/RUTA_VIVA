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
* Construye las tablas de hechos de la capa **Gold** (`FACT_TRIP`, `FACT_ZONE_INTERVAL`) y el agregado `RN11_MONTHLY_REPORT`.

---

## 2. DAGs de Apache Airflow (`batch/dags/`)

* **`rutaviva_monthly_pipeline`**: Se ejecuta a las 03:00 (America/New_York) el día 2 de cada mes. Extrae desde PostgreSQL las solicitudes con su auditoría y los intervalos de `zone_state_history` del mes anterior, carga los archivos landing a Bronze, y ejecuta Spark Job 1 y Job 2. Job 2 publica las tablas Gold en Parquet y el agregado RN-11. El DAG no termina correctamente si algún paso falla.
* **DAG Horario de Clima**: Consulta la API de Open-Meteo y actualiza la tabla operacional `weather_current` para que el cálculo en vivo siempre tenga el dato de precipitación sin latencia de red externa.

El landing debe estar montado en todos los workers de Airflow y contener subdirectorios `f1/`, `f3/`, `f7/`, `zone_state_history/`, `operational/trip_requests/` y `operational/service_complaints/`. La extracción operacional usa la conexión Airflow `AIRFLOW_POSTGRES_CONN_ID` (por defecto `postgres_default`), el provider `apache-airflow-providers-postgres` y permisos de solo lectura sobre `trip_request`, `fare_audit`, `zone_state_history` y `service_complaint`. Aplica la migración de quejas antes de habilitar el DAG. Configura `AIRFLOW_TIMEZONE` con la misma zona horaria del DAG. La ingesta conserva las rutas relativas en `S3_BRONZE_PATH` y omite objetos que ya existen. Configura `BRONZE_LANDING_DIR` y las rutas `S3_BRONZE_PATH`, `S3_SILVER_PATH`, `S3_QUARANTINE_PATH` y `S3_GOLD_PATH` en el entorno de Airflow y Spark. Los jobs Spark usan la conexión `spark_default`; la ingesta usa `AIRFLOW_AWS_CONN_ID` (por defecto `aws_default`) y puede apuntar a MinIO/LocalStack mediante `S3_ENDPOINT` y `S3_PATH_STYLE_ACCESS`.

La salida analítica es exclusivamente la Capa Gold en Parquet, consultable desde Athena o Power BI; no se generan reportes planos JSON.

### Ejecución local de Airflow con Docker Compose

El stack usa Apache Airflow **3.3.2** con `CeleryExecutor`. Redis actúa como
broker y los workers ejecutan las tareas Airflow; su base de metadatos
(`airflow-db`) es independiente de PostgreSQL operacional (`db`). Airflow solo
lee la base operacional mediante el rol `airflow_reader`. La interfaz web está
disponible en `http://localhost:8081` y Spark conserva su UI en el puerto 8080.

1. Copia `.env.example` a `.env` y configura las rutas S3 y, si usas
   MinIO/LocalStack, `S3_ENDPOINT`, `S3_PATH_STYLE_ACCESS`,
   `AWS_ACCESS_KEY_ID` y `AWS_SECRET_ACCESS_KEY`. MinIO/LocalStack debe estar
   ejecutándose por separado; este Compose no los incluye. En AWS real, deja el
   endpoint vacío y proporciona credenciales mediante IAM.
2. Reemplaza los valores de ejemplo `AIRFLOW_ADMIN_PASSWORD`,
   `AIRFLOW_DB_PASSWORD`, `AIRFLOW_FERNET_KEY`, `AIRFLOW_API_JWT_SECRET`,
   `AIRFLOW_API_SECRET_KEY` y `AIRFLOW_POSTGRES_PASSWORD`. Genera claves
   hexadecimales con `python -c "import secrets; print(secrets.token_hex(32))"`
   y la Fernet key con
   `docker run --rm apache/airflow:3.3.2-python3.12 python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
   Las contraseñas de base de datos se recomiendan hexadecimales para evitar
   caracteres que deban escaparse en la URI de conexión.
3. Aplica las migraciones de la aplicación y carga datos base en PostgreSQL
   operacional antes de iniciar los simuladores:

   ```bash
   uv run --locked alembic upgrade head
   uv run --locked python -m services.seed_cli.app.main --drivers 150
   ```

   Esto incluye la migración de `service_complaint`; no arranques
   `telemetry_simulator` ni el pipeline antes de que termine el seed.
4. Inicializa las bases de datos y el usuario de solo lectura y arranca los
   servicios:

   ```bash
   docker compose up --build airflow-init
   docker compose up --build -d spark-master spark-worker-1 airflow-api-server airflow-scheduler airflow-dag-processor airflow-worker airflow-triggerer
   ```

   El servicio `airflow-db-setup` configura de forma idempotente permisos de
   lectura para las tablas operacionales consultadas por el DAG. Para detener
   Airflow sin bajar el resto de la plataforma, ejecuta
   `docker compose stop airflow-api-server airflow-scheduler airflow-dag-processor airflow-worker airflow-triggerer`.
   No elimines el volumen `airflow_db_data`: contiene el metastore de Airflow.

El worker ejecuta las tareas Airflow y la imagen incluye Java, `spark-submit`
y los providers necesarios. Spark conserva sus propios workers para ejecutar
las aplicaciones distribuidas. El proceso Spark configura `spark.pyspark.python` con
`SPARK_EXECUTOR_PYTHON` para usar `/opt/venv/bin/python` en los ejecutores del
cluster.

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
  operational/
    trip_requests/     # TRIP_REQUEST unido a FARE_AUDIT, exportado por mes
    service_complaints/ # SERVICE_COMPLAINT con la zona de origen asociada
```

Se pueden sustituir las rutas predeterminadas `f1/`, `f3/`, `f7/`,
`operational/trip_requests/`, `operational/service_complaints/` y
`zone_state_history/` con `S3_F1_PATH`, `S3_WEATHER_PATH`, `S3_EVENTS_PATH`,
`S3_TRIP_REQUESTS_PATH`, `S3_SERVICE_COMPLAINTS_PATH` y
`S3_ZONE_STATE_HISTORY_PATH`. Las entradas aceptan CSV con encabezado, JSON o
Parquet; si el formato no se deduce de la extensión, se usa CSV. Para forzarlo,
configura `F1_FORMAT`, `F3_FORMAT`, `F7_FORMAT`, `TRIP_REQUESTS_FORMAT`,
`SERVICE_COMPLAINTS_FORMAT` o `ZONE_STATE_HISTORY_FORMAT` (`csv`, `json` o
`parquet`).

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

Job 1 normaliza encabezados F1 por archivo antes de unirlos, así admite meses
con los nombres TLC antiguos (`pickup_datetime`/`dropoff_datetime`) y los
actuales (`tpep_pickup_datetime`/`tpep_dropoff_datetime`), además de
`PULocationID`/`DOLocationID` o `pickup_zone_id`/`dropoff_zone_id`. Los nombres
de encabezado se comparan sin distinguir mayúsculas ni separadores. Las
columnas obligatorias son fechas de recogida y llegada, `trip_distance`,
`fare_amount` y `total_amount`; coordenadas y `extra` son opcionales. Si hay
IDs de zona, se validan entre 1 y 265 y las coordenadas pueden faltar; si no
hay IDs, las coordenadas son necesarias. Cada archivo se normaliza por separado
antes de unirlo, también para Parquet, para soportar cambios de esquema entre
archivos.
Job 2 también usa nombres canónicos: F3 contiene `weather_hour` y `rain_mm_h`;
F7 contiene `zone_id`, `starts_at` y `ends_at` (el ID puede ser nulo para un
evento de ciudad completa); el historial contiene `zone_id`, `interval_start`,
`requests`, `free_vehicles`, `pressure_index` y `estimated_wait_minutes`.
Job 2 construye `DIM_DATE`, `DIM_TIME_SLOT` (24 franjas horarias),
`DIM_WEATHER`, `DIM_ZONE`, `FACT_TRIP` y `FACT_ZONE_INTERVAL` en directorios
homónimos de Gold, en Parquet. También agrega `TRIP_REQUEST`/`FARE_AUDIT`,
`ZONE_STATE_HISTORY` y `SERVICE_COMPLAINT` a `RN11_MONTHLY_REPORT`, a una fila
por distrito y mes.
Incluye promedio de tarifa cobrada, espera estimada y porcentaje de auditorías
con multiplicador superior a 1, y conteo de quejas por fecha de creación y
distrito de origen.

El DAG pasa a los jobs Spark y a la extracción el año y mes calendario anterior
al disparo. Job 1
normaliza F1, filtra los viajes por fecha de recogida y reemplaza únicamente
las particiones `pickup_year`/`pickup_month` de Silver y Quarantine de ese
período. Job 2 filtra Silver y el historial operacional al mismo período y
reemplaza las particiones `year`/`month` de las tablas Gold que las tienen;
las dimensiones sin partición temporal se reconstruyen completas. Reejecutar
el DAG para un período actualiza ese período sin borrar los demás. Cuando los
archivos están organizados o nombrados con `YYYY-MM`, Job 1 puede limitar la
lectura a esos archivos; de lo contrario lee los archivos disponibles y aplica
el filtro temporal.

La ingesta Bronze conserva las rutas relativas y compara tamaño y fecha de
modificación del archivo local con los metadatos del objeto para omitir cargas
sin cambios o subir archivos modificados. Si se corrige una fuente, actualiza
el archivo en landing y vuelve a ejecutar el DAG. Esta detección no identifica
cambios que preserven ambos metadatos; en ese caso, fuerza la actualización
del objeto en Bronze antes del reproceso. El reemplazo de particiones en S3 no
es una operación transaccional: si una escritura falla, la tarea falla y
Airflow reintenta; el DAG no se considera exitoso hasta terminar todos los
pasos.

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
