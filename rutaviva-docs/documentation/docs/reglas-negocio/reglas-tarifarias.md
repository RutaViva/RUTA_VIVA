---
id: reglas-tarifarias
title: Reglas de Negocio de Tarificación Dinámica
sidebar_label: Reglas de Tarifa Dinámica
---

# Reglas de Negocio (RN)

Trazabilidad técnica de las reglas de cálculo tarifario y restricciones regulatorias del sistema:

---

## Catálogo de Reglas

| Código | Regla | Descripción y Lógica Técnica |
|---|---|---|
| **RN-01** | Multiplicador Base | El multiplicador neutral en condiciones de equilibrio es **1.0**. |
| **RN-02** | Fórmula de Presión | Presión = Solicitudes (últimos 10 min) / Vehículos Libres (últimos 2 min). Si no hay vehículos libres, se aplica presión máxima o 1.0 según la demanda. |
| **RN-03** | Escalonamiento por Presión | El multiplicador sube de forma escalonada según tramos de presión (1.0 \times \dots 1.8\times). |
| **RN-04** | Penalización por Lluvia | Si la precipitación supera 22.0 mm/h en `weather_current`, el multiplicador sube un escalón adicional. |
| **RN-05** | Topes Regulatorios | El multiplicador **nunca puede exceder 2.0** en ningún caso (garantizado por restricción `CHECK` en PostgreSQL). También contempla topes en franjas nocturnas. |
| **RN-06** | Congelamiento por Emergencia | Ante eventos declarados de emergencia (`special_event.is_emergency = true`), la tarifa se congela forzosamente en **1.0**. |
| **RN-07** | Congelamiento al Solicitar | La tarifa cobrada al usuario se congela en el segundo exacto de la solicitud (`requested_at`), independientemente de si la asignación del móvil ocurre minutos después. |
| **RN-09** | Filtro Legal de Oferta | Conductores con licencia vencida o sanción disciplinaria activa se excluyen de la oferta disponible. |
| **RN-10** | Filtro de Señal GPS | Vehículos sin emisión de telemetría en los últimos 2 minutos se consideran fuera de servicio y no cuentan como oferta. |
| **RN-12** | Auditoría Inmutable | Toda tarifa debe registrarse en `fare_audit` con tarifa base, multiplicador, factores y versión de regla aplicada. |

---

## Orden Estricto de Aplicación del Multiplicador

El orden de cálculo en el motor de tarifas es crítico:
1. **Presión Base**: Cálculo de demanda / oferta disponible.
2. **Escalón Base**: Determinación del multiplicador base (RN-03).
3. **Lluvia**: Incremento si rainrain mayor a 2 mm/h (RN-04).
4. **Topes**: Aplicación de límites máximos y nocturnos (RN-05).
5. **Emergencia**: Forzado a 1.0 si existe contingencia (RN-06).

> **Caso de Referencia (CA-02)**: Presión 4.0, lluvia 5 mm/h, hora 23:30 -> Multiplicador resultante = **1.5**.
