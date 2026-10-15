---
id: request-simulator
title: Simulador de Solicitudes de Pasajeros
sidebar_label: Request Simulator (request_simulator/)
---

# Simulador de Solicitudes (`services/request_simulator/`)

Generador de carga sintética que emula el comportamiento de los pasajeros solicitando viajes en distintas zonas de la ciudad (Requerimiento F5 / Historia HU-01).

---

## 1. Responsabilidades

* Generar peticiones continuas hacia el endpoint `POST /trip-requests` de la `multiplier_api`.
* Simular ráfagas de demanda configurables (por ejemplo, salida masiva de un evento o concierto en una zona específica, hasta 5,000 req/min).
* Producir eventos de cancelación para validar la operación de cancelación lógica (*soft-cancel*) en `trip_request`.
