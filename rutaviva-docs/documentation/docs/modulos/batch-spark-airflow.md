---
id: batch-spark-airflow
title: Procesamiento Batch (Spark & Airflow)
sidebar_label: Batch (Spark & Airflow)
---

# Procesamiento Batch (`batch/`)

El módulo batch contiene los trabajos analíticos distribuidos (PySpark) y los grafos de orquestación (Apache Airflow).

---

## 1. Jobs de Apache Spark (`batch/spark-jobs/`)

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
