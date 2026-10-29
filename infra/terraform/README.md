# Infraestructura AWS con Terraform - RUTA VIVA

Esta carpeta contiene la infraestructura completa como código (IaC) para desplegar **RUTA VIVA** en AWS siguiendo la arquitectura optimizada de **$158.40 USD/mes** (≤ $200 USD/mes) descrita en el documento de análisis de costos.

## Componentes Desplegados

1. **VPC y Red**:
   - 6 Subredes en 2 Zonas de Disponibilidad (Públicas, Privadas App, Privadas DB).
   - 1x Instancia EC2 `t4g.nano` configurada como NAT Instance (ahorro de $68.95/mes vs NAT Gateway administrado).
   - 1x VPC Gateway Endpoint para Amazon S3 (gratuito para tráfico de Spark y Data Lake).
2. **Base de Datos**:
   - Amazon RDS PostgreSQL 16 (`db.t4g.medium` Graviton2, Single-AZ, 20 GB gp3).
   - PITR (Point-in-Time Recovery) configurado a 7 días.
   - Parámetro `rds.force_ssl = 1`.
3. **Data Lake Medallón**:
   - Bucket S3 con carpetas `raw/`, `silver/`, `quarantine/`, `gold/`.
   - Ciclo de vida con archivado a Glacier a los 90 días y limpieza de consultas Athena.
4. **Cómputo en Contenedores**:
   - Clúster Amazon ECS con Fargate.
   - `multiplier_api`: FastAPI en Fargate On-Demand (2 tareas).
   - `pressure_worker`: Worker de RabbitMQ en Fargate Spot (70% descuento).
   - `telemetry_simulator`: Simulador en Fargate Spot (70% descuento).
   - `rabbitmq`: Tarea en Fargate On-Demand con DNS interno (`rabbitmq.rutaviva.local`).
5. **Balanceador de Carga**:
   - Application Load Balancer (ALB) público con Target Group hacia el puerto 8000.
6. **Contenedores y Monitoreo**:
   - 5 Repositorios privados en Amazon ECR con escaneo de vulnerabilidades y retención de 10 imágenes.
   - CloudWatch Log Groups con retención fijada a 14 días.
   - Credenciales almacenadas en AWS Secrets Manager.

---

## Requisitos Previos

1. **Instalar AWS CLI**:
   ```powershell
   winget install Amazon.AWSCLI
   ```
2. **Instalar Terraform**:
   ```powershell
   winget install Hashicorp.Terraform
   ```
3. **Configurar Credenciales de AWS**:
   ```powershell
   aws configure
   ```
   *(Ingresa tu Access Key ID, Secret Access Key y región `us-east-1`)*.

---

## Cómo Desplegar

1. **Copiar variables**:
   ```powershell
   cd infra/terraform
   Copy-Item terraform.tfvars.example terraform.tfvars
   ```
2. **Inicializar Terraform**:
   ```powershell
   terraform init
   ```
3. **Planificar y Crear**:
   ```powershell
   terraform apply
   ```
   *(Escribe `yes` cuando lo solicite)*.

4. **Construir y Subir Contenedores a ECR**:
   ```powershell
   .\push_images.ps1
   ```

---

## Cómo Ahorrar Créditos (Apagar y Encender)

Para que AWS **no te consuma créditos** mientras duermes o no estés probando:

### Opción 1: Apagar todos los contenedores de ECS (Costo Fargate = $0.00)
En `terraform.tfvars`, cambia los números a `0`:
```hcl
desired_tasks_api       = 0
desired_tasks_worker    = 0
desired_tasks_telemetry = 0
desired_tasks_rabbitmq  = 0
```
Y ejecuta:
```powershell
terraform apply -auto-approve
```
Cuando quieras volver a probar, vuelve a poner los números originales (2, 1, 1, 1) y ejecuta `terraform apply`.

### Opción 2: Pausar la Base de Datos RDS
En la consola de AWS o por CLI:
```powershell
aws rds stop-db-instance --db-instance-identifier ruta-viva-postgres
```
Para volver a encenderla:
```powershell
aws rds start-db-instance --db-instance-identifier ruta-viva-postgres
```

---

## Destruir Todo (Cuando termines la evaluación/proyecto)

Para que el consumo de créditos sea **cero absoluto**:
```powershell
terraform destroy
```
*(Escribe `yes` para eliminar todos los recursos de AWS)*.
