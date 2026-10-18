# RutaViva Movilidad · `weather-api`

Módulo de integración meteorológica encargado de ingerir las condiciones de precipitación pluvial en tiempo real desde la API pública de **Open-Meteo** (**Fuente F3**).

---

## 📌 1. Visión General: ¿Qué hace este servicio?

El servicio consulta los pronósticos y datos observados de lluvia para la ciudad de Nueva York y los almacena en la tabla relacional `weather_current`:
1. **Consulta Meteorológica Horaria**: Obtiene la tasa de lluvia en milímetros por hora (`rain_mm_h`) para las coordenadas centrales de NYC ($40.7128^\circ\text{ N}, -74.0060^\circ\text{ W}$).
2. **Normalización UTC**: Alinea los timestamps a horas en punto UTC (`YYYY-MM-DDTHH:00:00Z`).
3. **Persistencia Idempotente**: Realiza inserciones con `ON CONFLICT (valid_hour) DO UPDATE`, asegurando que reintentos o ejecuciones duplicadas nunca generen errores ni duplicados.

---

## 🎯 2. ¿Por qué se hizo así? (Justificación Arquitectónica)

- **Cero Dependencia Síncrona Externa**: Si cada petición de cotización tarifaria tuviera que llamar a Open-Meteo por HTTP, la latencia aumentaría en 300-800 ms y cualquier caída de la API de clima paralizaría el cobro de viajes. Al persistir el valor horario en PostgreSQL, la lectura es instantánea ($< 2\text{ ms}$).
- **Regla RN-04**: El cálculo del multiplicador en `pressure_worker` consulta directamente el registro vigente en `weather_current`. Si `rain_mm_h > 2.0`, se aplica automáticamente el incremento de un escalón tarifario.

---

## ⚙️ 3. ¿Cómo se usa?

### Modo Worker Continuo (Por defecto en Docker)
En segundo plano, consulta Open-Meteo cada hora y actualiza `weather_current` automáticamente:
```bash
docker compose up -d weather_worker
docker compose logs -f weather_worker
```

### Ejecución Única Local (One-shot)
Para consultar inmediatamente y salir:
```bash
uv run python services/weather-api/app/weather-variables.py --once
```
