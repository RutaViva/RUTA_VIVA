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

## 2. Inicializar el stack con Docker Compose

1. Copia `.env.example` a `.env` y completa las variables requeridas para
   PostgreSQL, Airflow y el almacenamiento S3. Compose crea la URL de
   migraciones usando el hostname interno `db`; usa una contraseña de
   PostgreSQL compatible con URL (se recomiendan caracteres hexadecimales).
   Para S3 local, configura también
   `S3_ENDPOINT`, `S3_PATH_STYLE_ACCESS` y las credenciales correspondientes.
2. Valida la configuración y levanta el proyecto:

   ```bash
   docker compose config -q
   docker compose up --build -d
   docker compose ps
   ```

   Compose aplica automáticamente las migraciones (`db_migrate`) y carga datos
   iniciales (`seed_runner`) antes de los servicios que los necesitan. El seed
   usa 8000 conductores/vehículos por defecto; puedes definir
   `SEED_DRIVERS` y `SEED_VEHICLES` en `.env` para ajustar el tamaño en una
   prueba. El seed no borra datos existentes por defecto; no ejecutes
   `docker compose down -v` salvo que quieras eliminar los volúmenes y sus
   datos. El simulador de solicitudes espera a que el healthcheck de la API
   responda correctamente.
3. Comprueba los servicios y sus logs cuando alguno no aparezca como
   `healthy`/`running`:

   ```bash
   docker compose ps -a
   docker compose logs --tail=100 db_migrate seed_runner airflow-api-server
   ```

   PostgreSQL escucha en `localhost:5438`, RabbitMQ en `localhost:5672`
   (consola `http://localhost:15672`), API en `http://localhost:8000/docs`,
   Airflow en `http://localhost:8081` y Spark UI en `http://localhost:8080`.
   Airflow debe tener fuentes F1/F3/F7 disponibles en landing o en S3 y los
   archivos de zonas requeridos por Job 2 antes de ejecutar el DAG mensual.

## 3. Documentación del proyecto

Inicia Docusaurus desde el directorio `documentation`:

```bash
cd documentation
npm run start
```
Abre [http://localhost:3000](http://localhost:3000).
