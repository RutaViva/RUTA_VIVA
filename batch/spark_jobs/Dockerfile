FROM eclipse-temurin:21-jre-jammy AS java

FROM python:3.12-slim-bookworm

ARG SPARK_VERSION=4.2.0
ARG SPARK_HADOOP_PROFILE=hadoop3

ENV JAVA_HOME=/opt/java/openjdk \
    SPARK_HOME=/opt/spark \
    PATH="/opt/spark/bin:/opt/spark/sbin:/opt/venv/bin:${PATH}" \
    PYSPARK_PYTHON=/opt/venv/bin/python \
    PYSPARK_DRIVER_PYTHON=/opt/venv/bin/python

COPY --from=java /opt/java/openjdk /opt/java/openjdk

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl --fail --location --progress-bar --show-error \
        "https://archive.apache.org/dist/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-${SPARK_HADOOP_PROFILE}.tgz" \
        --output /tmp/spark.tgz \
    && tar -xzf /tmp/spark.tgz --directory /opt \
    && mv "/opt/spark-${SPARK_VERSION}-bin-${SPARK_HADOOP_PROFILE}" /opt/spark \
    && rm /tmp/spark.tgz \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir \
        "geopandas>=1.0.0" \
        "pandas>=2.2.0,<3.0" \
        "shapely>=2.0.7" \
    && useradd --system --create-home --uid 185 spark \
    && mkdir -p /opt/spark/work /opt/spark/logs \
    && chown -R spark:spark /opt/spark /opt/venv /home/spark

USER spark
WORKDIR /opt/spark/work
