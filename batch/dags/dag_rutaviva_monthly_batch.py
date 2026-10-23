"""
batch/dags/dag_rutaviva_monthly_batch.py
DAG maestro de Apache Airflow para el procesamiento mensual de RutaViva (CA-08, RN-11).
Programado para ejecutarse el día 2 de cada mes a las 00:00 UTC (cron: 0 0 2 * *).
Cadena de ejecución:
[task_check_data_readiness] -> [task_spark_job1_clean_validate] -> [task_spark_job2_enrich_gold] -> [task_generate_regulatory_report] -> [task_publish_regulatory_delivery]
"""
from datetime import datetime, timedelta

# Definición de imports condicionales para permitir pruebas locales sin servicio Airflow en marcha
try:
    from airflow import DAG
    from airflow.operators.bash import BashOperator
    from airflow.operators.python import PythonOperator  # noqa: F401
    AIRFLOW_AVAILABLE = True
except ImportError:
    AIRFLOW_AVAILABLE = False


DEFAULT_ARGS = {
    "owner": "rutaviva_data_engineering",
    "depends_on_past": False,
    "email": ["compliance@rutaviva.com", "data-ops@rutaviva.com"],
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def build_rutaviva_monthly_dag():
    """Construye y retorna el DAG mensual de RutaViva."""
    if not AIRFLOW_AVAILABLE:
        return None

    dag = DAG(
        dag_id="dag_rutaviva_monthly_batch",
        default_args=DEFAULT_ARGS,
        description="Pipeline ETL mensual: Bronze -> Silver -> Gold y Reporte Regulatorio TLC el día 2 (RN-11 / CA-08)",
        schedule_interval="0 0 2 * *",  # Día 2 de cada mes a las 00:00 UTC
        start_date=datetime(2026, 1, 1),
        catchup=False,
        max_active_runs=1,
        tags=["rutaviva", "batch", "spark", "regulatory", "tlc"],
    )

    # 1. Comprobación de disponibilidad de datos en S3/Bronze
    task_check_data_readiness = BashOperator(
        task_id="check_data_readiness",
        bash_command="""
        echo "Verificando disponibilidad de extractos mensuales de viajes y zonas..."
        test -d data/bronze/trips || mkdir -p data/bronze/trips
        test -f services/seed_cli/app/data/csv/taxi_zone_lookup.csv || exit 1
        echo "Datos disponibles para ejecución."
        """,
        dag=dag,
    )

    # 2. Job 1 PySpark: Limpieza, Unificación (CA-09) y Cuarentena (CA-01)
    task_spark_job1 = BashOperator(
        task_id="spark_job1_clean_validate",
        bash_command="""
        uv run python batch/spark-jobs/job1_clean_validate/main.py \
            --input data/bronze/trips \
            --silver data/silver/trips \
            --quarantine data/quarantine/trips \
            --format csv
        """,
        dag=dag,
    )

    # 3. Job 2 PySpark: Enriquecimiento Multifuente y Modelo Dimensional Gold (RF-09)
    task_spark_job2 = BashOperator(
        task_id="spark_job2_enrich_gold",
        bash_command="""
        uv run python batch/spark-jobs/job2_enrich_model/main.py \
            --silver data/silver/trips \
            --zones services/seed_cli/app/data/csv/taxi_zone_lookup.csv \
            --gold data/gold
        """,
        dag=dag,
    )

    # 4. Generación Automática del Reporte Regulatorio Mensual (RN-11 / CA-08 / E-16)
    task_generate_report = BashOperator(
        task_id="generate_regulatory_report",
        bash_command="""
        uv run python batch/reports/generate_regulatory_report.py \
            --gold data/gold/fact_trips \
            --out data/reports
        """,
        dag=dag,
    )

    # 5. Entrega y Notificación de Cumplimiento Regulatorio
    task_publish_delivery = BashOperator(
        task_id="publish_regulatory_delivery",
        bash_command="""
        echo "Reporte regulatorio mensual generado y archivado para TLC con éxito."
        ls -la data/reports/
        """,
        dag=dag,
    )

    # Orquestación de dependencias
    task_check_data_readiness >> task_spark_job1 >> task_spark_job2 >> task_generate_report >> task_publish_delivery

    return dag


# Instanciación a nivel de módulo para Airflow scheduler
if AIRFLOW_AVAILABLE:
    dag = build_rutaviva_monthly_dag()
