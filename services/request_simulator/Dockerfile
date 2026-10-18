# ==============================================================================
# Dockerfile para services/request_simulator
# ==============================================================================
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir \
    "httpx>=0.27.0" \
    "pydantic-settings>=2.0"

# ==============================================================================
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app"

COPY --from=builder /opt/venv /opt/venv

RUN groupadd --system app && useradd --system --gid app app
WORKDIR /app

COPY ./app /app

USER app

CMD ["python", "main.py"]
