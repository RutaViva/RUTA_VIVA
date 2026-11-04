# ==============================================================================
# RUTA VIVA - Master Deploy Script (One-Click AWS Deployment)
# ==============================================================================
[CmdletBinding()]
param (
    [string]$Region = "us-east-1",
    [switch]$SkipBuild,
    [switch]$Destroy
)

# Refrescar PATH para asegurar disponibilidad inmediata de AWS CLI y Terraform
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

$ProjectRoot = $PSScriptRoot
$TerraformDir = Join-Path $ProjectRoot "infra\terraform"

if ($Destroy) {
    Write-Host ""
    Write-Host "========================================================" -ForegroundColor Red
    Write-Host " [DESTRUCCION] Eliminando infraestructura en AWS...     " -ForegroundColor Red
    Write-Host "========================================================" -ForegroundColor Red
    Write-Host ""
    
    Set-Location $TerraformDir
    terraform destroy -auto-approve
    Set-Location $ProjectRoot
    Write-Host ""
    Write-Host "[OK] Todos los recursos en AWS han sido destruidos ($0.00)." -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " RUTA VIVA - Despliegue Automatico en AWS               " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Validar Docker
Write-Host "[1/6] Verificando Docker Desktop..." -ForegroundColor Yellow
docker info 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [ERROR] Docker Desktop no esta en ejecucion. Por favor inicialo." -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] Docker esta activo y listo." -ForegroundColor Green

# 2. Validar Credenciales de AWS
Write-Host ""
Write-Host "[2/6] Verificando conexion con AWS..." -ForegroundColor Yellow
$IdentityJson = aws sts get-caller-identity --output json 2>$null
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($IdentityJson)) {
    Write-Host "  [ERROR] No se detectaron credenciales de AWS activas." -ForegroundColor Red
    Write-Host "  Ejecuta 'aws configure' e ingresa tu Access Key ID y Secret Access Key." -ForegroundColor Yellow
    exit 1
}

$Identity = $IdentityJson | ConvertFrom-Json
Write-Host "  [OK] Conectado a AWS exitosamente!" -ForegroundColor Green
Write-Host "       Cuenta: $($Identity.Account)" -ForegroundColor DarkGray
Write-Host "       ARN:    $($Identity.Arn)" -ForegroundColor DarkGray

# 3. Preparar e Inicializar Terraform
Write-Host ""
Write-Host "[3/6] Inicializando infraestructura con Terraform..." -ForegroundColor Yellow
Set-Location $TerraformDir

$TfVarsPath = Join-Path $TerraformDir "terraform.tfvars"
if (-not (Test-Path $TfVarsPath)) {
    Copy-Item (Join-Path $TerraformDir "terraform.tfvars.example") $TfVarsPath
}

terraform init

# 4. Fase 1 de Terraform: Levantar red, RDS, S3, ALB y ECR (con tareas en 0)
Write-Host ""
Write-Host "[4/6] Aprovisionando VPC, RDS, S3 Data Lake, ALB y repositorios ECR..." -ForegroundColor Yellow
terraform apply -auto-approve -var="desired_tasks_api=0" -var="desired_tasks_worker=0" -var="desired_tasks_telemetry=0" -var="desired_tasks_rabbitmq=0"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [ERROR] Fallo al desplegar la infraestructura base con Terraform." -ForegroundColor Red
    Set-Location $ProjectRoot
    exit 1
}

# 5. Compilar y publicar imagenes Docker a Amazon ECR
if (-not $SkipBuild) {
    Write-Host ""
    Write-Host "[5/6] Compilando microservicios y publicando imagenes en Amazon ECR..." -ForegroundColor Yellow
    & ".\push_images.ps1" -Region $Region
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] Fallo al compilar o publicar las imagenes a ECR." -ForegroundColor Red
        Set-Location $ProjectRoot
        exit 1
    }
}

# 6. Fase 2: Escalar y encender microservicios en ECS Fargate
Write-Host ""
Write-Host "[6/6] Activando microservicios en Amazon ECS Fargate..." -ForegroundColor Yellow
terraform apply -auto-approve -var="desired_tasks_api=2" -var="desired_tasks_worker=1" -var="desired_tasks_telemetry=1" -var="desired_tasks_rabbitmq=1"
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [ERROR] Fallo al activar las tareas de ECS en Terraform." -ForegroundColor Red
    Set-Location $ProjectRoot
    exit 1
}

# Obtener salidas de Terraform
$AlbDns = terraform output -raw alb_dns_name 2>$null
$S3Bucket = terraform output -raw s3_datalake_bucket 2>$null
$RdsHost = terraform output -raw rds_address 2>$null
$NatId = terraform output -raw nat_instance_id 2>$null

Set-Location $ProjectRoot

Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Host " PROYECTO RUTA VIVA DESPLEGADO CON EXITO EN AWS!        " -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
Write-Host "  Endpoint ALB (API):      http://$AlbDns" -ForegroundColor Cyan
Write-Host "  Swagger Docs (OpenAPI):  http://$AlbDns/docs" -ForegroundColor Cyan
Write-Host "  Health Check:            http://$AlbDns/health/ready" -ForegroundColor Cyan
Write-Host "  Data Lake S3:            s3://$S3Bucket" -ForegroundColor Cyan
Write-Host "  Host RDS PostgreSQL:     $RdsHost" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Green
Write-Host "  COMANDO PARA DESTRUIR TODO DESPUES DE LA PRESENTACION:" -ForegroundColor Yellow
Write-Host "     .\destroy.ps1" -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Green
Write-Host ""
