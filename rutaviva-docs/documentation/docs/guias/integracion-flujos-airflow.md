---
id: integracion-flujos-airflow
title: Integración de los flujos mensuales de Airflow
sidebar_label: Integración de flujos Airflow
---

# Integración de los flujos mensuales de Airflow

Este documento registra las decisiones y cambios realizados para consolidar
los dos flujos mensuales que llegaron desde las ramas integradas. El objetivo
fue conservar la extracción y el procesamiento medallón del DAG anterior e
incorporar la validación y la entrega del reporte regulatorio del otro flujo,
sin mantener dos pipelines mensuales que pudieran ejecutarse sobre el mismo
período de forma independiente.

## Decisión de integración

Se conserva `rutaviva_monthly_pipeline` como el único DAG mensual y se mantiene
su `dag_id`, horario y semántica de período anterior. El nuevo flujo no
reemplaza las transformaciones Spark existentes: se reutilizan
`batch/spark_jobs/job1_clean_validate.py` y
`batch/spark_jobs/job2_enrich_model.py`, que leen y escriben en las rutas S3
medallón del proyecto.

El orden final es:

```text
check_data_readiness
  -> extract_operational_sources
  -> bronze_ingestion
  -> job1_clean_validate
  -> job2_enrich_model
  -> generate_regulatory_report
  -> publish_regulatory_report
```

Cada etapa depende de que la anterior termine correctamente. El reporte se
genera a partir de `RN11_MONTHLY_REPORT`, que Job 2 escribe en Gold; no se
consulta un esquema `fact_trips` distinto al que produce este pipeline.

## Cambios realizados, archivo por archivo

### Orquestación y datos

| Archivo | Cambio | Motivo / resultado |
|---|---|---|
| `batch/dags/rutaviva_monthly_pipeline.py` | Se conservó el DAG y su ID, y se extendió la secuencia para incluir readiness, extracción, Bronze, Jobs 1 y 2, reporte RN-11 y publicación. Se usan las utilidades existentes para seleccionar el mes calendario anterior. | Unificar la extracción operacional y el procesamiento histórico con la salida regulatoria bajo un mismo run y período. |
| `batch/dags/dag_rutaviva_monthly_batch.py` | Se retiró el DAG mensual duplicado. | Evitar dos pipelines mensuales con responsabilidades solapadas o ejecución doble. El DAG horario del clima no forma parte de este cambio y se conserva. |
| `batch/scripts/pipeline_readiness.py` | Nuevo módulo que valida landing, las rutas S3 requeridas, las fuentes históricas F1/F3/F7 disponibles en landing o en S3 y el catálogo/shapefile de zonas usado por Job 2. | Fallar antes de extraer datos operacionales o iniciar Spark si faltan entradas indispensables. |
| `batch/scripts/operational_bronze_extract.py` | Se reutiliza sin cambiar su contrato: extrae solicitudes con auditorías, historial de zona y quejas para el mes anterior. | Preservar la extracción de PostgreSQL que ya realizaba el flujo existente e incluir esos datos en RN-11. |
| `batch/scripts/bronze_ingestion.py` | Se expuso el constructor del cliente S3 como `make_s3_client` en lugar de la función privada anterior. La carga incremental de Bronze se mantiene. | Compartir la misma configuración AWS/S3 entre la ingesta y la publicación de reportes. |
| `batch/utils/spark_utils.py` | `submit_spark_job` recibe la ruta del script que debe ejecutar y pasa la configuración S3/AWS y las rutas de insumos geográficos al proceso Spark. | Permitir que el DAG invoque los scripts S3-aware de `batch/spark_jobs/` y el generador del reporte de forma explícita. |
| `batch/spark_jobs/job1_clean_validate.py` y `batch/spark_jobs/job2_enrich_model.py` | Se mantienen como jobs canónicos; no se reemplazaron por los scripts del flujo alternativo. Job 2 sigue generando `RN11_MONTHLY_REPORT`. | Preservar Silver, Quarantine, Gold y la compatibilidad con los formatos de entrada usados por el proyecto. |

### Reporte regulatorio

| Archivo | Cambio | Motivo / resultado |
|---|---|---|
| `batch/reports/generate_regulatory_report.py` | Se añadió el modo `--rn11`, que lee el agregado `RN11_MONTHLY_REPORT`, filtra año/mes y genera JSON y CSV por distrito. El modo histórico `--gold` se conserva. | Incorporar el reporte del nuevo flujo sin retirar la CLI anterior ni leer un modelo Gold incompatible. |
| `batch/scripts/report_publication.py` | Nuevo módulo que comprueba que los dos archivos existan y no estén vacíos, y luego los publica en `S3_GOLD_PATH/reports/year=YYYY/month=MM/`. | Hacer que la finalización del DAG incluya la entrega de los archivos, no solo su generación local. |
| `docker-compose.yml` | Se añadió el volumen compartido `airflow_reports` montado en `/opt/airflow/reports` en todos los componentes Airflow. | Compartir el directorio de salida entre la tarea que ejecuta Spark en modo cliente y la tarea Airflow que publica los archivos. |

El contrato de `RN11_MONTHLY_REPORT` usado por el reporte requiere las
columnas `borough`, `trip_count`, `average_fare`, `average_wait_minutes`,
`multiplier_gt_one_pct`, `complaint_count`, `year` y `month`. Job 2 produce
este agregado por distrito y período; si no hay filas para el período, la
generación del reporte falla en lugar de publicar un archivo vacío.

### Inicio y dependencias de Compose

| Archivo | Cambio | Motivo / resultado |
|---|---|---|
| `docker-compose.yml` | Se incorporó el servicio de una sola ejecución `db_migrate`, construido con la imagen de `seed_cli`, y se configura su conexión hacia el host interno `db`. | Aplicar las migraciones Alembic dentro del entorno Compose antes del seed y de los servicios que consultan el esquema. |
| `infra/migrations/env.py` | Alembic usa `DATABASE_URL` cuando está definido y mantiene el valor de `alembic.ini` como alternativa. | Permitir que el mismo conjunto de migraciones conecte tanto desde el host como desde el contenedor. |
| `docker-compose.yml` | `seed_runner` espera a `db_migrate`; `SEED_CLEAN` toma `false` por defecto. Los servicios operacionales y Airflow esperan las tareas de migración, seed y permisos según corresponda. | Hacer que el arranque respete el orden de inicialización y evitar borrar datos cada vez que se inicia Compose. |
| `docker-compose.yml` | Se pasan variables AWS/S3 a Spark master y worker. | Asegurar que tanto el driver como los ejecutores tengan la configuración de acceso al almacenamiento. |
| `docker-compose.yml` | Los servicios Airflow comparten el volumen de reportes y dependen de la inicialización de bases, seed y usuario de solo lectura. | Evitar que el DAG empiece antes de tener el entorno operacional listo. |
| `docker-compose.yml` | Se agregó un healthcheck HTTP para `multiplier_api`; `request_simulator` espera a que la API esté saludable. El seed genera 8000 conductores por defecto y de 1 a 2 vehículos por conductor; `SEED_DRIVERS` permite ajustar la cantidad de conductores. | Evitar errores de conexión durante el arranque y permitir pruebas locales con un tamaño de datos controlado. |

`docker compose build` construye imágenes; el servicio `db_migrate` y el
`seed_runner` se ejecutan al levantar los servicios con `docker compose up`.
La guía de [puesta en marcha](./puesta-en-marcha.md) documenta los comandos de
inicio y las comprobaciones.

## Pruebas añadidas o actualizadas

| Archivo | Cobertura |
|---|---|
| `batch/tests/test_bronze_ingestion.py` | Actualiza el mock para el nombre público `make_s3_client`; conserva las comprobaciones de carga y omisión de objetos sin cambios. |
| `batch/tests/test_pipeline_readiness.py` | Comprueba disponibilidad de fuentes locales y S3, e informa error cuando faltan fuentes históricas. |
| `batch/tests/test_report_publication.py` | Comprueba las claves de destino para JSON/CSV y que no se publique si faltan archivos. |
| `batch/tests/test_operational_bronze_extract.py` | Se ejecutó para verificar que la extracción existente conserva período, rutas y exportación. |

## Configuración y ejecución

Antes de habilitar o disparar el DAG:

1. Configura `.env`, las cuatro rutas S3 medallón, credenciales/endpoints
   necesarios y conexiones de PostgreSQL, Spark y AWS descritas en
   [Procesamiento Batch (Spark & Airflow)](../modulos/batch-spark-airflow.md).
2. Asegura que F1, F3 y F7 estén en el landing compartido o en las rutas S3
   configuradas. En el landing, las rutas predeterminadas son `f1/`, `f3/` y
   `f7/`.
3. Comprueba que el catálogo TLC y todos los componentes del shapefile estén
   disponibles en el contenedor Airflow/Spark.
4. Ejecuta `docker compose config -q`, después levanta el stack y verifica que
   `db_migrate`, `seed_runner` y `airflow-db-setup` terminen correctamente.
5. Despausa `rutaviva_monthly_pipeline` en Airflow y ejecuta un run controlado.
   El horario regular es a las 03:00 de `America/New_York` el día 2, para
   procesar el mes anterior.

La validación de fuentes remotas necesita permisos S3 para listar objetos; la
ingesta, además, requiere permiso de escritura. Si las fuentes F1/F3/F7 no
están disponibles, readiness detendrá el DAG deliberadamente.

## Validación realizada y limitaciones

Se ejecutaron las pruebas focalizadas de extracción, ingesta Bronze,
readiness y publicación; compilaron los módulos Python modificados; y
`docker compose config -q` y `git diff --check` finalizaron correctamente.
No se ejecutó el pipeline completo contra un entorno Airflow, PostgreSQL y S3
reales.

En el momento de la validación, `uv run pytest` no podía arrancar porque
`pyproject.toml` contenía una tabla `[dependency-groups]` duplicada. Ese
archivo estaba en conflicto de merge y no se modificó como parte de esta
integración. Asimismo, no se incorporaron ni se inventaron archivos de datos
F1/F3/F7 ausentes en el landing local: deben proporcionarse antes de ejecutar
el DAG.
