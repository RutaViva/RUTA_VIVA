# ==============================================================================
# ETAPA 1: Constructor (Builder)
# Instala dependencias de Python en un entorno virtual aislado.
# ==============================================================================
FROM python:3.12-slim AS builder

# Variables de entorno para optimizar y limpiar la construcción
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Instala dependencias del sistema necesarias para compilar paquetes Python
# que tienen extensiones nativas (como psycopg, GDAL, etc.)[reference:6]
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Crea un entorno virtual e instala las dependencias de Python
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ==============================================================================
# ETAPA 2: Imagen Final (Runtime)
# Instala dependencias de sistema en tiempo de ejecución y copia el venv.
# ==============================================================================
FROM python:3.12-slim AS runtime

# Variables de entorno para la aplicación
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Instala dependencias del sistema en tiempo de ejecución (sin -dev)
# Incluye las librerías necesarias para que GeoPandas/Fiona funcionen[reference:7][reference:8]
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    proj-bin \
    proj-data \
    && rm -rf /var/lib/apt/lists/*

# Copia el entorno virtual desde la etapa de construcción
COPY --from=builder /opt/venv /opt/venv

# Crea un usuario no-root para mayor seguridad[reference:9]
RUN groupadd --system app && useradd --system --gid app app

WORKDIR /app

# Copia el código de la aplicación y los datos necesarios
COPY --chown=app:app . .

# Cambia al usuario no-root
USER app

# El comando por defecto se define en docker-compose.yml
CMD ["python", "-m", "services.main"]