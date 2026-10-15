---
id: estandares-glosario
title: Estándares de Datos y Glosario de Dominio
sidebar_label: Estándares & Glosario
---

# Estándares de Datos y Glosario de Dominio

Documento de referencia para el equipo de desarrollo que asegura coherencia terminológica y homogeneidad en el pipeline de datos.

---

## 1. Glosario de Dominio

| Término | Definición |
|---|---|
| **RutaViva** | Plataforma para el procesamiento, estandarización y tarificación dinámica de flota vehicular urbana. |
| **F1** | NYC Yellow Taxi Trip Data (CSV histórico con cambios de esquema entre años). |
| **F2** | Catálogo oficial de Taxi Zones de la TLC (Shapefile y CSV lookup). |
| **F3** | Datos meteorológicos horarios (históricos de API Open-Meteo). |
| **F4** | Telemetría GPS en streaming (pulsos cada 15 segundos). |
| **F5** | Solicitudes continuas de viaje generadas por pasajeros. |
| **F6** | Registro operativo de conductores, vehículos, licencias y sanciones. |
| **F7** | Calendario de eventos masivos y emergencias. |
| **Índice de Presión** | Relación matemática Presión = Demanda / max(Oferta, 1). |
| **Degradación Segura** | Mecanismo de fallback por el cual la API retorna multiplicador 1.0 con `degraded: true` ante fallos o datos obsoletos (>300 s). |

---

## 2. Convenciones de Desarrollo

* **Estrategia de Ramas**: Git Flow simplificado:
  * `main`: Código estable y probado para producción.
  * `feature/<nombre>`: Ramas de funcionalidad aisladas (`feature/DataSeed`, `feature/telemetry-simulator`, `feature/api`).
* **Mensajes de Commit**: Formato **Conventional Commits**:
  * `feat: ...`: Nueva funcionalidad.
  * `fix: ...`: Corrección de un defecto.
  * `chore: ...`: Mantenimiento o configuración.
  * `docs ...`:Cambios en documentación.
  * `refactor: ...`Reestructuración del código sin cambiar su funcionalidad.
  * `test: ...`: Creación o modificación de pruebas.
  * `data: ...` :Cambios relacionados con datos, esquemas o transformaciones.
* **Tipado y Fechas**:
  * Fechas siempre en UTC (`TIMESTAMPTZ` o naive normalizado en Python con `replace(tzinfo=None)`).
  * Monedas y multiplicadores representados mediante tipos decimales exactos (`NUMERIC`).
