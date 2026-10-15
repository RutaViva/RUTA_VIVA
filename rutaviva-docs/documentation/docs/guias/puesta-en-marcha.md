---
id: puesta-en-marcha
title: Guía de Puesta en Marcha Rápida
sidebar_label: Puesta en Marcha
---

# Guía de Puesta en Marcha

Instrucciones para levantar el entorno de desarrollo local de RutaViva.

---

## 1. Prerrequisitos
* Docker y Docker Compose
* Python 3.12+ (recomendado gestor `uv`)
* Node.js 20+ (para la documentación Docusaurus)

---

## 2. Paso a Paso

### 1. Iniciar Infraestructura (PostgreSQL + RabbitMQ)
```bash
docker compose up -d
```
* PostgreSQL escuchando en el puerto `5438`.
* RabbitMQ en `5672` (Consola Web: `http://localhost:15672`, admin / admin1234).

### 2. Ejecutar Migraciones de Base de Datos
```bash
uv run alembic upgrade head
```

### 3. Poblar Datos Base (Seed CLI)
```bash
uv run python -m services.seed_cli.app.main --drivers 150
```

### 4. Iniciar el Simulador de Telemetría
```bash
uv run python -m services.telemetry_simulator.app.telemetry_generator
```

### 5. Iniciar la API de Multiplicador
```bash
uv run uvicorn services.multiplier_api.app.main:app --host 0.0.0.0 --port 8000 --reload
```
Documentación Swagger interactiva: [http://localhost:8000/docs](http://localhost:8000/docs).

### 6. Iniciar el Servidor de Documentación (Docusaurus)
```bash
cd documentation
npm run start
```
Abre en tu navegador: [http://localhost:3000](http://localhost:3000).
