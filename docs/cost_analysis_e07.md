# Análisis de Costos de Infraestructura Cloud en AWS (E-07)

> **Proyecto**: RutaViva Mobility  
> **Rol**: Cloud Architect  
> **Criterio de Aceptación**: E-07 (Tabla Comparativa Dev vs. Prod con supuestos explícitos y desglose de AWS Pricing Calculator)  
> **Presupuesto Máximo**: $\le \$190 \text{ USD/mes}$
> **Nota**: estimación orientativa para `us-east-1`; validar en AWS Pricing Calculator. La nueva EC2 compartida deja poco margen para transferencia, picos de CPU, logs o cambios de precios.

---

## 1. Tabla Comparativa de Costos por Servicio (Dev vs. Prod Inicial vs. Prod Optimizado)

| Servicio AWS | ¿Qué incluye? | Escenario Dev ($/mes) | Escenario Prod Inicial ($/mes) | Escenario Prod Optimizado ($/mes) |
| :--- | :--- | :--- | :--- | :--- |
| **Amazon RDS (PostgreSQL 16)** | Motor relacional MER 13 tablas, auditoría `fare_audit`, PITR y `rds.force_ssl=1`. | **$27.12**<br>*(db.t4g.small, 20 GB)* | **$523.06** ⚠️<br>*(db.r6g.xlarge Multi-AZ, 100 GB)* | **$51.94**<br>*(db.t4g.medium Single-AZ, 20 GB gp3)* |
| **Amazon VPC (Red y salida)** | Salida a Internet para Open-Meteo y EC2 compartida para NAT/Airflow/Spark. | **$34.20**<br>*(1 NAT GW + 30 GB)* | **$72.45** ⚠️<br>*(2 NAT GWs Multi-AZ)* | **$31.38**<br>*(t4g.medium 24/7, 40 GB gp3, IPv4 pública y S3 Gateway Endpoint)* |
| **AWS ECS / Fargate (Cómputo)** | FastAPI (`multiplier_api`), `pressure_worker`, `telemetry_sim`, `rabbitmq`. | **$36.20**<br>*(2 tareas 0.5 vCPU)* | **$178.50**<br>*(6-8 tareas On-Demand 24/7)* | **$47.06**<br>*(API On-Demand + Workers en Spot con 70% desc.)* |
| **Application Load Balancer (ALB)** | Balanceador público TLS/HTTP hacia FastAPI. | **$22.50**<br>*(1 LCU promedio)* | **$38.40**<br>*(3 LCUs en Multi-AZ)* | **$22.50**<br>*(1 LCU promedio)* |
| **Amazon S3 (Data Lake Medallón)** | Capas `raw/`, `silver/`, `quarantine/`, `gold/` + ciclo de vida Glacier. | **$1.26**<br>*(45 GB almacenamiento)* | **$5.35**<br>*(250 GB + 2.5M peticiones)* | **$4.00**<br>*(60 GB con ciclo de vida activo)* |
| **Amazon ECR (Imágenes Docker)** | 5 repositorios privados con escaneo continuo de CVEs. | **$1.00**<br>*(10 GB / 10 versiones)* | **$4.00**<br>*(40 GB / 30 versiones)* | **$2.50**<br>*(25 GB / 10 versiones con lifecycle rule)* |
| **CloudWatch Logs & Secrets** | Ingestión de logs, métricas p95 y Secrets Manager. | **$6.70**<br>*(5 GB logs + 3 secretos)* | **$38.90**<br>*(50 GB logs + 6 secretos)* | **$6.90**<br>*(8 GB logs a 14 días + secretos)* |
| **TOTAL MENSUAL** | -- | **$129.08 USD** | **$861.66 USD** | **$166.28 USD** |

> La suma de las partidas del escenario optimizado es aproximadamente **$166.28 USD/mes**, dejando **$23.72 USD** antes del máximo de $190. El total anterior de $158.40 no coincidía con la suma de las partidas publicadas. No es una cotización: transferencia, recursos adicionales y cambios de precio pueden consumir el margen.

---

## 2. Supuestos Explícitos de la Optimización

### 2.1. Base de Datos RDS (Ahorro: -$471.12/mes)
* **Supuesto**: El volumen actual de ~8,000 vehículos envía telemetría cada 15 segundos amortiguado por el buffer de RabbitMQ. Una instancia Graviton2 (`db.t4g.medium` o `db.t4g.micro` en Free Tier) procesa holgadamente este caudal de escrituras sin requerir `db.r6g.xlarge`.
* **Disponibilidad vs. Resiliencia**: Se prescinde de la réplica síncrona en caliente (Multi-AZ) a favor de Single-AZ con copias de seguridad continuas y restauración a cualquier segundo (**Point-In-Time Recovery**).

### 2.2. Salida a Internet, EC2 compartida y S3 Endpoint
* **Supuesto de costo**: EC2 `t4g.medium` Linux On-Demand encendida 730 horas/mes, 40 GB gp3 y una IPv4 pública en `us-east-1`. El costo de referencia de esta fila es ~US$31.38/mes, sujeto a precios, uso y créditos de CPU.
* **Concurrencia limitada**: Airflow usa `LocalExecutor` y Spark un solo worker de 1 GB. El modo T4g `standard` evita cobros por créditos de CPU, pero puede limitar trabajos que mantengan CPU alta.
* **S3 Gateway Endpoint**: el tráfico entre la VPC y S3 no pasa por la NAT y el endpoint gateway no tiene tarifa por hora.
* **Disponibilidad**: EC2 también sirve como NAT. No se puede detener solo para ahorrar mientras las subredes privadas requieran salida a Internet.

### 2.3. Cómputo ECS Fargate Mixto (Ahorro: -$131.44/mes)
* **Supuesto**: La API expuesta a usuarios (`multiplier_api`) requiere SLA estricto (p95 < 150ms) y corre en **Fargate On-Demand**.
* **Tolerancia a Interrupciones**: Los workers (`pressure_worker` y `telemetry_simulator`) son tolerantes a interrupciones porque RabbitMQ implementa colas durables y mensajes persistentes; corren en **Fargate Spot** aprovechando un 70% de descuento.

### 2.4. Retención de CloudWatch (Ahorro: -$32.00/mes)
* **Supuesto**: Los logs de consola de contenedores tienen valor operativo durante 14 días. La trazabilidad regulatoria e histórica permanente se almacena de forma inmutable en PostgreSQL (`fare_audit`) y en la capa `gold/` de S3.
