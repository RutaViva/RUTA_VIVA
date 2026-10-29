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
| **NAT Instance** | `ruta-viva-nat-instance` | IP Privada en 10.0.0.x | EC2 `t4g.micro` con IP Forwarding e iptables masquerade. |
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
* **Instancia**: `ruta-viva-postgres` (`db.t4g.micro` / `db.t4g.medium`, Single-AZ).
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
* **`ruta-viva-rds-sg`**: Inbound 5432 permitido exclusivamente desde `ruta-viva-ecs-tasks-sg`.
* **Roles IAM**:
  - `ruta-viva-ecs-execution-role`: Permisos mínimos para descargar de ECR y escribir logs en CloudWatch (`AmazonECSTaskExecutionRolePolicy`).
  - `ruta-viva-ecs-task-role`: Permisos delimitados estrictamente para leer/escribir dentro del bucket del Data Lake S3 (`s3:GetObject`, `s3:PutObject`, `s3:ListBucket`).

---

## 2. Runbook Operacional: Despliegue, Destrucción y Recreación

### Escenario A: Destrucción Total para Evitar Costos Residuales ($0.00 USD)
Cuando se termine una sesión de trabajo o evaluación, se garantiza que ningún recurso quede facturando:

1. Abrir terminal de PowerShell en la carpeta de infraestructura:
   ```powershell
   cd "c:\Users\Cohorte 5\Downloads\RUTA_VIVA\infra\terraform"
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

1. Abrir terminal de PowerShell en la carpeta:
   ```powershell
   cd "c:\Users\Cohorte 5\Downloads\RUTA_VIVA\infra\terraform"
   ```
2. Ejecutar:
   ```powershell
   terraform init
   terraform apply -auto-approve
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

---

### Escenario C: Modo Hibernación (Mantener datos pero gastar $0.00 en cómputo)
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
