# Inventario de Recursos AWS y Runbook Operacional (CT-03)

> **Proyecto**: RutaViva Mobility  
> **Criterio de Aceptación**: CT-03 (Documento de inventario y procedimiento paso a paso para desplegar, destruir y recrear recursos evitando costos residuales)  
> **Área**: Cloud Architecture & DevOps

---

## 1. Inventario Técnico de Recursos Provisionados

### 1.1. Red y Conectividad (VPC)
| Recurso | Identificador / Nombre | CIDR / Subred | Propósito / Zona |
| :--- | :--- | :--- | :--- |
| **VPC** | `ruta-viva-vpc` | `10.0.0.0/16` | Aislamiento de red principal con DNS hostnames habilitados. |
| **Subred Pública 1** | `ruta-viva-public-subnet-1` | `10.0.0.0/24` | AZ: `us-east-1a`. Aloja ALB y NAT Instance. |
| **Subred Pública 2** | `ruta-viva-public-subnet-2` | `10.0.1.0/24` | AZ: `us-east-1b`. Requerida para Multi-AZ del ALB público. |
| **Subred Privada App 1**| `ruta-viva-private-app-subnet-1`| `10.0.10.0/24` | AZ: `us-east-1a`. Tareas de ECS Fargate y RabbitMQ. |
| **Subred Privada App 2**| `ruta-viva-private-app-subnet-2`| `10.0.11.0/24` | AZ: `us-east-1b`. Tareas de ECS Fargate y RabbitMQ. |
| **Subred Privada DB 1** | `ruta-viva-private-db-subnet-1` | `10.0.20.0/24` | AZ: `us-east-1a`. Aislamiento estricto de PostgreSQL. |
| **Subred Privada DB 2** | `ruta-viva-private-db-subnet-2` | `10.0.21.0/24` | AZ: `us-east-1b`. Aislamiento estricto de PostgreSQL. |
| **Internet Gateway** | `ruta-viva-igw` | -- | Salida/entrada a Internet para subredes públicas. |
| **EC2 compartida NAT + datos** | `ruta-viva-nat-data-services` | Subred pública 1 | EC2 `t4g.medium` ARM64, 40 GB gp3, Docker/Compose; hace NAT y ejecuta Airflow + Spark para cargas pequeñas. |
| **S3 Gateway Endpoint**| `ruta-viva-s3-gateway-endpoint`| -- | Tráfico directo y gratuito entre VPC y Amazon S3. |

### 1.2. Almacenamiento y Data Lake (Amazon S3)
* **Bucket**: `ruta-viva-datalake-<suffix>` (Cifrado SSE-S3 AES256, Bloqueo de Acceso Público Activo).
* **Estructura Medallón**:
  - `raw/`: Datos crudos GPS y viajes. Regla de ciclo de vida: transición a Glacier a los 90 días.
  - `silver/`: Datos curados y enriquecidos con Open-Meteo.
  - `quarantine/`: Datos con anomalías de telemetría.
  - `gold/`: Datos agregados de demanda y tarifas para auditoría.
  - `athena-results/`: Regla de ciclo de vida con expiración automática a los 7 días.

### 1.3. Base de Datos Relacional (Amazon RDS)
* **Instancia**: `ruta-viva-postgres` (`db.t4g.medium` según `terraform.tfvars.example`, Single-AZ).
* **Motor**: PostgreSQL 16 con `rds.force_ssl = 1` en Parameter Group.
* **Almacenamiento**: 20 GB gp3 con autoescalado controlado hasta 100 GB.
* **Acceso Público**: Inactivo (`publicly_accessible = false`).
* **Credenciales**: Almacenadas de forma rotativa en **AWS Secrets Manager** (`ruta-viva-db-credentials`).

### 1.4. Repositorios de Contenedores (Amazon ECR)
* Repositorios privados:
  1. `ruta-viva/multiplier_api`
  2. `ruta-viva/pressure_worker`
  3. `ruta-viva/telemetry_simulator`
  4. `ruta-viva/rabbitmq`
  5. `ruta-viva/request_simulator`
* **Políticas**: Escaneo de seguridad automático en push (`scan_on_push = true`) y expiración de imágenes dejando solo las últimas 10 (`imageCountMoreThan: 10`).

### 1.5. Matriz de Seguridad y Principio de Menor Privilegio (IAM & SG)
* **`ruta-viva-alb-sg`**: Inbound 80/443 desde `0.0.0.0/0`.
* **`ruta-viva-ecs-tasks-sg`**: Inbound 8000 exclusivamente desde `ruta-viva-alb-sg`. Inbound interno para RabbitMQ (5672/15672) restringido a `self`.
* **`ruta-viva-rds-sg`**: Inbound 5432 permitido desde `ruta-viva-ecs-tasks-sg` y `ruta-viva-nat-sg` (Airflow en la EC2 compartida).
* **Roles IAM**:
  - `ruta-viva-ecs-execution-role`: Permisos mínimos para descargar de ECR y escribir logs en CloudWatch (`AmazonECSTaskExecutionRolePolicy`).
  - `ruta-viva-ecs-task-role`: Permisos delimitados estrictamente para leer/escribir dentro del bucket del Data Lake S3 (`s3:GetObject`, `s3:PutObject`, `s3:ListBucket`).
  - `ruta-viva-nat-data-services-role`: acceso SSM y acceso de lectura/escritura al bucket del Data Lake desde Airflow/Spark.

### 1.6. Airflow y Spark en la EC2 compartida
* Airflow usa `LocalExecutor` y una base PostgreSQL local en volumen Docker para sus metadatos.
* Los DAGs consultan RDS usando un rol PostgreSQL de solo lectura y publican resultados en S3 con el rol de instancia EC2.
* Spark usa un master y un worker de 1 GB. Es una configuración de demostración; limita la concurrencia y no ofrece alta disponibilidad.
* Airflow y las interfaces web de Spark solo se enlazan a `127.0.0.1`. Accede a Airflow mediante Session Manager con port forwarding; no se abren puertos de aplicación en el Security Group.
* Los volúmenes Docker sobreviven a `docker compose down`, pero no al reemplazo o destrucción de la EC2. Los datos/artefactos que deban conservarse deben quedar en RDS o S3.
* `request_simulator`, API, RabbitMQ y workers operativos permanecen en ECS/Fargate. RDS y S3 no se migran a la EC2.

---

## 2. Runbook Operacional: Despliegue, Destrucción y Recreación

### Escenario A: Destrucción Total para Evitar Costos Residuales ($0.00 USD)
Cuando se termine una sesión de trabajo o evaluación, se garantiza que ningún recurso quede facturando:

1. Abrir terminal de PowerShell en el repositorio:
   ```powershell
   Set-Location infra/terraform
   ```
2. Ejecutar la orden de destrucción completa:
   ```powershell
   terraform destroy -auto-approve
   ```
3. **Verificación de Residuos Cero**:
   - Verificar en consola de RDS que no existan instancias ni snapshots facturables (`skip_final_snapshot = true` asegura que no queden respaldos de pago).
   - El bucket S3 se vacía y elimina automáticamente (`force_destroy = true`).
   - El ALB y su Elastic IP se liberan de inmediato.

---

### Escenario B: Recreación Rápida de Toda la Infraestructura
Para volver a levantar el 100% de la arquitectura operativa en 5 minutos:

1. Abrir terminal de PowerShell en el repositorio:
   ```powershell
   Set-Location infra/terraform
   ```
2. Planificar y aplicar. Revisa el plan: el cambio de tamaño/configuración reemplaza la EC2 NAT, elimina sus volúmenes Docker locales y causa una interrupción temporal de salida a Internet para las subredes privadas.
   ```powershell
   terraform init
   terraform plan
   terraform apply
   ```
3. Construir y publicar las imágenes de microservicios:
   ```powershell
   .\push_images.ps1
   ```
4. **Verificación de Disponibilidad**:
   - Obtener la URL del ALB:
     ```powershell
     terraform output alb_dns_name
     ```
   - Probar endpoint de salud:
     ```bash
     curl http://<ALB-DNS-NAME>/health
     ```

### Escenario C: Preparar Airflow y Spark en la EC2 NAT
La EC2 solo queda preparada con Docker/Compose e IAM al aplicar Terraform; el código y los contenedores de datos se levantan aparte:

1. Obtén el ID de la instancia y el hostname RDS:
   ```powershell
   terraform output -raw nat_instance_id
   terraform output -raw rds_address
   terraform output -raw s3_datalake_bucket
   ```
2. Conéctate usando Session Manager (requiere AWS CLI y Session Manager plugin):
   ```powershell
   aws ssm start-session --target <NAT-INSTANCE-ID>
   ```
3. En la instancia, clona la rama del repositorio que contiene los cambios a desplegar y entra a su carpeta. Copia `infra/terraform/airflow-spark.env.example` a `airflow-spark.env`; completa `RDS_HOST`, credenciales de Airflow y las rutas `s3a://` usando los outputs del paso 1. No agregues credenciales AWS estáticas: los contenedores usan el rol IAM de la instancia. Restringe el archivo con `chmod 600 airflow-spark.env`.
4. Crea un archivo temporal `.env.bootstrap` con solo la contraseña maestra de RDS, con permisos `chmod 600`. Ejecuta una sola vez el SQL que crea el usuario PostgreSQL de solo lectura:
   ```bash
   docker compose --env-file airflow-spark.env --env-file .env.bootstrap \
     --profile bootstrap -f docker-compose.aws-data.yml run --rm airflow-db-setup
   ```
   Después elimina `.env.bootstrap`; su contraseña no se necesita para ejecutar Airflow/Spark:
   ```bash
   rm .env.bootstrap
   ```
5. Inicia los servicios de datos:
   ```bash
   mkdir -p batch/data/landing
   docker compose --env-file airflow-spark.env -f docker-compose.aws-data.yml up -d --build
   docker compose --env-file airflow-spark.env -f docker-compose.aws-data.yml ps
   ```
6. Desde otra terminal local, abre un túnel SSM y visita `http://localhost:8081`:
   ```powershell
   aws ssm start-session --target <NAT-INSTANCE-ID> --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["8081"],"localPortNumber":["8081"]}'
   ```
   Usa las credenciales de Airflow definidas en `airflow-spark.env`.

Antes de habilitar los DAGs, inicializa el esquema y carga los datos de RDS según la guía de despliegue. El `docker-compose.aws-data.yml` ejecuta solo Airflow/Spark y sus dependencias; no levanta una segunda API, RabbitMQ ni base de datos de aplicación. El rol de Airflow se crea con permisos de lectura, así que las tablas de aplicación deben existir antes de ejecutar el DAG.

---

### Escenario D: Apagar cómputo de aplicación manteniendo la EC2 NAT
Si se desea conservar la base de datos y la red pero apagar los contenedores:

1. En `terraform.tfvars` colocar:
   ```hcl
   desired_tasks_api       = 0
   desired_tasks_worker    = 0
   desired_tasks_telemetry = 0
   desired_tasks_rabbitmq  = 0
   ```
2. Aplicar:
   ```powershell
   terraform apply -auto-approve
   ```
3. Pausar la base de datos temporalmente:
   ```powershell
   aws rds stop-db-instance --db-instance-identifier ruta-viva-postgres
   ```
4. Si no se necesitan los jobs de datos, detén Airflow/Spark con `docker compose ... down`. La EC2 debe seguir encendida mientras se requiera NAT y continúa generando costo.
