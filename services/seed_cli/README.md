# RutaViva Movilidad · `seed_cli`

Herramienta de línea de comandos (CLI) encargada del poblamiento determinista, reproducible e idempotente de los catálogos geográficos y las entidades operacionales maestras de RutaViva (**Fuentes F2 y F6**).

---

## 📌 1. Visión General: ¿Qué hace este servicio?

El `seed_cli` genera la base de datos inicial sin intervención manual ni volcados arbitrarios (*dumps*), cumpliendo los requisitos de la sección 5.2 del proyecto:
1. **Catálogo Espacial Oficial (Fuente F2)**: Carga las 265 zonas oficiales de la NYC Taxi & Limousine Commission (TLC) desde polígonos GeoJSON / Shapefiles, mapeando `borough` y `zone_name`.
2. **Flota y Conductores Sintéticos (Fuente F6)**: Genera 8,000 conductores por defecto con nombres realistas, números de licencia y entre uno y dos vehículos afiliados por conductor, con placas únicas.
3. **Modelado de Estado Legal (Regla RN-09)**:
   - Asigna de manera estocástica pero determinista licencias vigentes y vencidas.
   - Aplica sanciones disciplinarias activas con fechas de inicio y término.
   - Actualiza el estado legal del conductor (`active`, `suspended`, `inactive`) para garantizar la integridad de las reglas tarifarias.
4. **Semilla Inicial de Telemetría**: Ubica a cada vehículo físicamente dentro de un polígono de zona de taxi válido en la tabla `vehicle_state`.

---

## ⚙️ 2. ¿Cómo se hizo? (Características Técnicas)

- **Semilla Fija y Reproducibilidad**: Utiliza `SEED=42` y `NP_SEED=42` con `Faker` y `numpy.random`, garantizando que dos ejecuciones generen exactamente la misma flota.
- **Idempotencia Estricta**: Inserciones mediante `pg_insert(Model).on_conflict_do_nothing()`. Ejecutar el comando múltiples veces no duplica filas ni produce errores de clave duplicada (**Criterio CT-06**).
- **Parámetros de Volumen**: `--modo completo` genera 8,000 conductores por defecto y asigna aleatoriamente entre uno y dos vehículos a cada conductor. `--drivers` permite ajustar la cantidad de conductores y `--vehicles` establecer opcionalmente una cantidad exacta de vehículos.

---

## 🚀 3. ¿Cómo se usa?

### Ejecución Local

```bash
cd services/seed_cli

# Ejecución completa (8,000 conductores y de 1 a 2 vehículos por conductor)
python -m app.main --modo completo
```

### Ejecución con Docker

```bash
docker build -t rutaviva-seed-cli -f Dockerfile .
docker run --rm --network rutaviva-network rutaviva-seed-cli
```
