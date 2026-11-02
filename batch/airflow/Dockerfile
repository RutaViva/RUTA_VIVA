FROM eclipse-temurin:21-jre-jammy AS java

FROM apache/airflow:3.3.2-python3.12

USER root
COPY --from=java /opt/java/openjdk /opt/java/openjdk

ENV JAVA_HOME=/opt/java/openjdk \
    PATH="/opt/java/openjdk/bin:/home/airflow/.local/bin:${PATH}"

USER airflow

RUN pip install --no-cache-dir \
    "apache-airflow==3.3.2" \
    "apache-airflow-providers-amazon==9.36.0" \
    "apache-airflow-providers-apache-spark==6.3.2" \
    "apache-airflow-providers-fab==3.9.0" \
    "apache-airflow-providers-postgres==7.0.2" \
    "geopandas>=1.0.0" \
    "pandas>=2.2.0" \
    "pyspark==4.2.0" \
    "shapely>=2.0.7" \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-3.12.txt"

RUN command -v spark-submit

USER airflow
