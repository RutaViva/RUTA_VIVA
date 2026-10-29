# Guía Maestra de Despliegue, Ejecución y Validación de Infraestructura AWS

> **Proyecto**: RutaViva Mobility  
> **Propósito**: Manual operacional integral para desplegar la arquitectura optimizada en AWS, compilar y publicar microservicios, validar el funcionamiento de cada componente y gestionar el ciclo de vida para garantizar costo $0.00 cuando no esté en uso.

---

## 📑 Tabla de Contenidos
1. [Arquitectura del Sistema en AWS](#1-arquitectura-del-sistema-en-aws)
2. [Requisitos Previos y Entorno](#2-requisitos-previos-y-entorno)
3. [Paso a Paso de Ejecución (Despliegue)](#3-paso-a-paso-de-ejecución-despliegue)
   - [3.1. Configuración de Variables](#31-configuración-de-variables)
   - [3.2. Aprovisionamiento con Terraform](#32-aprovisionamiento-con-terraform)
   - [3.3. Compilación y Publicación de Contenedores a ECR](#33-compilación-y-publicación-de-contenedores-a-ecr)
   - [3.4. Inicialización y Seed de Base de Datos](#34-inicialización-y-seed-de-base-de-datos)
4. [Protocolo de Validación y Pruebas (Health & Smoke Tests)](#4-protocolo-de-validación-y-pruebas-health--smoke-tests)
   - [4.1. Validación de Red, NAT y S3 Gateway Endpoint](#41-validación-de-red-nat-y-s3-gateway-endpoint)
   - [4.2. Validación de Base de Datos PostgreSQL 16 (SSL y MER)](#42-validación-de-base-de-datos-postgresql-16-ssl-y-mer)
   - [4.3. Validación del Data Lake S3 (Capas Medallón)](#43-validación-del-data-lake-s3-capas-medallón)
   - [4.4. Validación de la API Pública y ALB](#44-validación-de-la-api-pública-y-alb)
   - [4.5. Validación de RabbitMQ y Fargate Spot Workers](#45-validación-de-rabbitmq-y-fargate-spot-workers)
   - [4.6. Validación de Retención de Logs en CloudWatch](#46-validación-de-retención-de-logs-en-cloudwatch)
5. [Guía Anti-Consumo de Créditos: Hibernación y Destrucción](#5-guía-anti-consumo-de-créditos-hibernación-y-destrucción)

---

## 1. Arquitectura del Sistema en AWS

La infraestructura implementada en AWS responde a un modelo altamente desacoplado, seguro y optimizado en costo:

```mermaid
flowchart TD
    subgraph Internet & Clientes
        User[Peticiones Pasajeros / Clientes]
        OpenMeteo[API Externa Clima]
    end

    subgraph AWS VPC 10.0.0.0/16
        subgraph Subredes Públicas Multi-AZ
            ALB[Application Load Balancer\nHTTP:80 / HTTPS:443]
            NAT[NAT Instance t4g.micro\nSalida Liviana Internet]
        end

        subgraph Subredes Privadas App
            ECS_API[multiplier_api\nFastAPI 2x On-Demand]
            ECS_RABBIT[rabbitmq\nBroker 1x On-Demand]
            ECS_WORKER[pressure_worker\nConsumidor Fargate Spot]
            ECS_SIM[telemetry_simulator\nSimulador Fargate Spot]
        end

        subgraph Subredes Privadas Base de Datos
            RDS[(RDS PostgreSQL 16\ndb.t4g.micro gp3\nSingle-AZ + SSL)]
        end

        S3_EP[VPC S3 Gateway Endpoint\nTráfico Interno Gratuito $0.00]
    end

    subgraph Almacenamiento & Servicios AWS
        S3_LAKE[(Amazon S3 Data Lake\nraw/ | silver/ | quarantine/ | gold/)]
        ECR[Amazon ECR\n5 Repositorios Privados]
        CW[CloudWatch Logs\nRetención 14 días]
        SM[Secrets Manager\nCredenciales DB]
    end

    User -->|HTTP Requests| ALB
    ALB -->|Balancea puerto 8000| ECS_API
    ECS_SIM -->|Eventos GPS c/15s| ECS_RABBIT
    ECS_RABBIT -->|Consume colas| ECS_WORKER
    ECS_WORKER -->|Actualiza zone_state| RDS
    ECS_API -->|Consulta tarifas & audita| RDS
    ECS_WORKER -->|Salida Clima| NAT --> OpenMeteo
    ECS_WORKER -.->|Vía VPC Endpoint| S3_EP --> S3_LAKE
    RDS -.->|Credenciales| SM
    ECS_API -.->|Logs| CW
    ECS_WORKER -.->|Logs| CW
```

---

## 2. Requisitos Previos y Entorno

Verifica que en tu terminal de **PowerShell** tengas instalados los siguientes comandos:
```powershell
aws --version          # AWS CLI v2
terraform -version     # Terraform v1.5+
docker --version       # Docker Engine
```

Verifica la conexión activa con tu cuenta de AWS:
```powershell
aws sts get-caller-identity
```

---

## 3. Paso a Paso de Ejecución (Despliegue)

### 3.1. Configuración de Variables
Navega a la carpeta de infraestructura:
```powershell
cd "c:\Users\Cohorte 5\Downloads\RUTA_VIVA\infra\terraform"
```
Revisa el archivo `terraform.tfvars`:
```hcl
aws_region              = "us-east-1"
project_name            = "ruta-viva"
environment             = "prod-opt"
db_name                 = "rutaviva_db"
db_username             = "postgres"
db_password             = "RutaViva2026SecurePass!"
db_instance_class       = "db.t4g.micro"

# Tareas activas de ECS:
desired_tasks_api       = 2
desired_tasks_worker    = 1
desired_tasks_telemetry = 1
desired_tasks_rabbitmq  = 1
```

### 3.2. Aprovisionamiento con Terraform
Inicializa los plugins y aplica el despliegue:
```powershell
terraform init
terraform apply
```
Cuando te pregunte `Do you want to perform these actions?`, escribe **`yes`** y presiona Enter.  

Al terminar, Terraform imprimirá los outputs principales:
* `alb_dns_name`: URL pública de acceso web.
* `rds_endpoint`: Dirección privada de conexión a la base de datos.
* `s3_datalake_bucket`: Nombre asignado al bucket S3.
* `ecr_repositories`: URLs de tus 5 repositorios privados.

---

### 3.3. Compilación y Publicación de Contenedores a ECR
En la misma carpeta `infra/terraform`, ejecuta el script automatizado:
```powershell
.\push_images.ps1
```

---

### 3.4. Inicialización y Seed de Base de Datos
Para aplicar el esquema relacional de las 13 tablas y la semilla de 8,000 vehículos y conductores:
1. Conéctate a la base de datos usando el script SQL del repositorio:
   ```powershell
   psql -h <RDS_ENDPOINT> -U postgres -d rutaviva_db -f "..\init.sql"
   ```
2. Ejecuta las migraciones de Alembic para asegurar las restricciones de integridad y auditoría:
   ```powershell
   alembic upgrade head
   ```

---

## 4. Protocolo de Validación y Pruebas (Health & Smoke Tests)

### 4.1. Validación de Red, NAT y S3 Gateway Endpoint
* **Objetivo**: Confirmar que los recursos en subredes privadas tienen salida a Internet sin pagar por NAT Gateway y que el tráfico a S3 es interno.
* **Prueba**:
  1. Ve a la consola de **VPC** $\rightarrow$ **Endpoints**. Verifica que `ruta-viva-s3-gateway-endpoint` esté en estado **Available** y asociado a las Route Tables privadas.
  2. Ve a **EC2** $\rightarrow$ Verifica que la instancia `ruta-viva-nat-instance` esté **Running** y con la opción `Source/dest. check` en **Disabled**.

### 4.2. Validación de Base de Datos PostgreSQL 16 (SSL y MER)
* **Objetivo**: Verificar que PostgreSQL esté aislado, obligue a usar cifrado SSL y contenga las tablas del sistema.
* **Prueba de SSL Forzado**:
  Intenta conectar sin SSL. La conexión debe ser rechazada porque `rds.force_ssl = 1`:
  ```bash
  psql "host=<RDS_ENDPOINT> user=postgres dbname=rutaviva_db sslmode=disable"
  ```
  Conecta con SSL activo:
  ```bash
  psql "host=<RDS_ENDPOINT> user=postgres dbname=rutaviva_db sslmode=require"
  ```

### 4.3. Validación del Data Lake S3 (Capas Medallón)
* **Objetivo**: Verificar la estructura de directorios y las políticas de ciclo de vida.
* **Prueba desde AWS CLI**:
  ```powershell
  # Listar carpetas del bucket
  aws s3 ls s3://<NOMBRE_DEL_BUCKET>/
  # Resultado esperado:
  # PRE gold/
  # PRE quarantine/
  # PRE raw/
  # PRE silver/
  ```

### 4.4. Validación de la API Pública y ALB
* **Objetivo**: Validar el punto de entrada HTTPS/HTTP y la respuesta del microservicio FastAPI.
* **Prueba de Health Check**:
  ```powershell
  curl http://<ALB_DNS_NAME>/health
  # Respuesta esperada: HTTP 200 OK {"status": "healthy"}
  ```

### 4.5. Validación de RabbitMQ y Fargate Spot Workers
* **Objetivo**: Comprobar que RabbitMQ encola los mensajes y que los workers en Fargate Spot los procesan sin pérdida de telemetría.
* **Prueba**:
  1. En la consola de **ECS** $\rightarrow$ clúster `ruta-viva-cluster` $\rightarrow$ pestaña **Services**.
  2. Verifica que `ruta-viva-rabbitmq` esté en estado `ACTIVE` con 1 tarea en proveedor **FARGATE**.
  3. Verifica que `ruta-viva-pressure-worker` y `ruta-viva-telemetry-simulator` estén en estado `ACTIVE` utilizando el proveedor **FARGATE_SPOT**.

### 4.6. Validación de Retención de Logs en CloudWatch
* **Objetivo**: Asegurar que ningún Log Group acumule costos indefinidos.
* **Prueba**:
  Ejecuta en PowerShell:
  ```powershell
  aws logs describe-log-groups --log-group-name-prefix "/ecs/ruta-viva" --query "logGroups[*].[logGroupName,retentionInDays]" --output table
  ```

---

## 5. Guía Anti-Consumo de Créditos: Hibernación y Destrucción

### Escenario A: Hibernar (Apagar Cómputo, Mantener Datos y Red)
1. En `infra/terraform/terraform.tfvars`, coloca las tareas en `0`.
2. Aplica el cambio: `terraform apply -auto-approve`.
3. Detén la base de datos PostgreSQL:
   ```powershell
   aws rds stop-db-instance --db-instance-identifier ruta-viva-postgres
   ```

---

### Escenario B: Destrucción Total ($0.00 Absoluto)
```powershell
cd "c:\Users\Cohorte 5\Downloads\RUTA_VIVA\infra\terraform"
terraform destroy
```
Escribe **`yes`**. Todos los recursos en AWS se eliminarán en menos de 3 minutos.

---

### Escenario C: Recrear Todo desde Cero (En 5 Minutos)
```powershell
cd "c:\Users\Cohorte 5\Downloads\RUTA_VIVA\infra\terraform"
terraform apply -auto-approve
.\push_images.ps1
```
