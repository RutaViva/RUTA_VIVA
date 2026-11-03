# Infraestructura AWS con Terraform - RUTA VIVA

Esta carpeta contiene la infraestructura como código (IaC) para desplegar **RUTA VIVA** en AWS. La arquitectura conserva ECS/Fargate para la aplicación y comparte la EC2 de NAT con Airflow y un worker Spark pequeño. El estimado de costos actualizado está en `docs/cost_analysis_e07.md`; no es una cotización y deja poco margen bajo el límite de $190 USD/mes.

## Componentes Desplegados

1. **VPC y Red**:
   - 6 Subredes en 2 Zonas de Disponibilidad (Públicas, Privadas App, Privadas DB).
   - 1x Instancia EC2 `t4g.medium` con Amazon Linux 2023, Docker, Docker Compose y reglas NAT persistentes.
   - Airflow y Spark se ejecutan como un stack Docker Compose separado en la misma EC2. El perfil usa Airflow `LocalExecutor` y un solo worker Spark; está pensado para cargas pequeñas, no para alta disponibilidad.
   - Acceso administrativo mediante AWS Systems Manager Session Manager; el puerto de Airflow solo se publica en loopback.
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
   terraform plan
   terraform apply
   ```
   *(Escribe `yes` cuando lo solicite)*.

   El cambio de tamaño/configuración reemplaza la EC2 NAT; durante el reemplazo habrá una interrupción temporal de salida a Internet para las subredes privadas. Terraform entrega `nat_instance_id`, `rds_address` y `s3_datalake_bucket`.

4. **Preparar Airflow y Spark en la EC2 compartida**:
   Sigue `docs/aws_inventory_and_runbook_ct03.md`, sección “Airflow y Spark en la EC2 NAT”. El despliegue usa `docker-compose.aws-data.yml`, almacena metadatos de Airflow en un volumen local y conecta los DAGs a RDS/S3. Ese volumen se pierde si Terraform reemplaza o destruye la EC2; conserva los resultados en RDS/S3.

5. **Construir y Subir Contenedores a ECR**:
   ```powershell
   .\push_images.ps1
   ```

---

## Cómo Ahorrar Créditos (Apagar y Encender)

La EC2 compartida también presta servicio de NAT, por lo que no se debe detener mientras los recursos privados necesiten salida a Internet. Para reducir costos de EC2, destruye la infraestructura o acepta interrumpir la salida NAT; detener solo los contenedores Airflow/Spark no detiene la facturación de la instancia.

### Apagar los contenedores ECS (costo Fargate = $0.00)
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

### Apagar Airflow y Spark
Desde la carpeta del proyecto en la EC2:
```bash
docker compose --env-file airflow-spark.env -f docker-compose.aws-data.yml down
```
Esto detiene y elimina los contenedores, pero conserva los volúmenes de Docker. La EC2 sigue encendida como NAT y se sigue facturando.

### Pausar la Base de Datos RDS
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
