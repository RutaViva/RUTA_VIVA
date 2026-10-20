# RutaViva Movilidad · `request_simulator`

Microservicio generador de tráfico sintético encargado de emular el comportamiento de miles de pasajeros solicitando servicios de transporte mediante la aplicación móvil (**Fuente F5**).

---

## 📌 1. Visión General: ¿Qué hace este servicio?

El `request_simulator` modela la demanda de viajes en tiempo real contra la `multiplier_api`:
1. **Emisión de Solicitudes Continuas**: Genera peticiones HTTP concurrentes (`POST /trip-requests`) con tasas parametrizables (por defecto 8 a 15 solicitudes/segundo).
2. **Distribución Espacial Realista**: Distribuye los viajes entre las 265 zonas de NYC TLC, concentrando mayor probabilidad de demanda en núcleos de alto tráfico (Midtown Manhattan, Financial District, Aeropuertos JFK y LaGuardia).
3. **Simulación del Ciclo de Vida del Viaje**: Tras crear la solicitud, un porcentaje de viajes pasa automáticamente al estado `assigned` tras una breve espera (3 a 15 segundos), emulando la aceptación por parte de un conductor.
4. **Modo Ráfaga (*Burst Mode*)**: Capacidad de disparar picos repentinos de demanda (hasta 5,000 solicitudes en 1 minuto) para simular la salida masiva de eventos especiales (conciertos en Madison Square Garden, partidos en Yankee Stadium) y validar la resiliencia del sistema (**Criterio CA-10**).

---

## 🛠️ 2. ¿Qué se hizo? (Detalle de Implementación)

- **Cliente HTTP Asíncrono de Alto Rendimiento (`simulator.py`)**:
  - Implementado sobre `httpx.AsyncClient` con pool de conexiones persistentes (`keepalive`) y semáforo de concurrencia (`asyncio.Semaphore`).
- **Generador Estocástico de Tarifas**:
  - Modela tarifas base usando una distribución normal gaussiana ($media = \$14.50, \sigma = \$5.00$) acotada entre \$5.00 y \$95.00.
- **Configuración Dinámica (`config.py`)**:
  - Permite configurar la tasa de solicitudes por segundo, URL objetivo de la API, zonas mínimas/máximas y parámetros de ráfagas desde variables de entorno o archivo `.env`.
- **Ejecución y Empaquetado (`main.py` y `Dockerfile`)**:
  - Bucle de control asíncrono con captura de señales del sistema para reporte final de métricas (solicitudes enviadas, exitosas y fallidas).

---

## ⚙️ 3. ¿Cómo se usa? (Configuración y Comandos)

### Variables de Entorno Configurables

| Variable | Tipo | Valor por Defecto | Propósito |
|---|:---:|:---:|---|
| `API_URL` | String | `http://localhost:8000` | URL base de la `multiplier_api` |
| `REQUESTS_PER_SECOND` | Float | `10.0` | Solicitudes continuas por segundo |
| `CONCURRENCY_LIMIT` | Int | `50` | Máximo de peticiones HTTP simultáneas |
| `BURST_ENABLED` | Bool | `false` | Activa ráfagas periódicas de alta demanda |
| `BURST_REQUESTS_COUNT` | Int | `1000` | Solicitudes emitidas durante la ráfaga |
| `BURST_INTERVAL_SECONDS` | Int | `180` | Intervalo entre ráfagas |
| `BURST_TARGET_ZONE` | Int | `161` | Zona objetivo de la ráfaga (ej. Midtown Center) |

### Ejecución Local

```bash
# 1. Acceder al directorio
cd services/request_simulator

# 2. Iniciar simulación estándar
python app/main.py
```

### Ejecución de Prueba de Estrés (Ráfaga de 5,000 solicitudes / 1 min — CA-10)

```bash
REQUESTS_PER_SECOND=85.0 CONCURRENCY_LIMIT=100 python app/main.py
```

### Ejecución con Docker

```bash
docker build -t rutaviva-request-simulator -f Dockerfile .
docker run --rm --network rutaviva-network rutaviva-request-simulator
```

---

## 🎯 4. ¿Por qué se hizo así? (Justificación Arquitectónica)

1. **Alimentación Realista del Motor de Presión**: La regla **RN-02** requiere contar solicitudes en los últimos 10 minutos para calcular la presión. Sin este simulador, la base de datos permanecería estática y el multiplicador siempre sería 1.0.
2. **Validación de Criterios de Aceptación (CA-10)**: El pliego del proyecto exige que el sistema soporte ráfagas de 5,000 solicitudes en un minuto sin pérdida de mensajes ni caídas de servicio.
3. **Control de Concurrencia**: El uso de un semáforo asíncrono previene saturar el stack de red local del sistema operativo durante las pruebas de carga.
