# ==============================================================================
# Dockerfile para services/telemetry_simulator
# ==============================================================================
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir \
    "aio-pika>=10.1.1" \
    "geopandas>=1.0.0" \
    "numpy>=1.26.0" \
    "pandas>=2.2.0" \
    "psycopg[binary]>=3.2.0" \
    "pydantic-settings>=2.0" \
    "sqlalchemy>=2.0" \
    "shapely>=2.0.0" \
    "pyproj>=3.6.0"

# ==============================================================================
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

COPY ./app /app

CMD ["python", "telemetry_generator.py"]
