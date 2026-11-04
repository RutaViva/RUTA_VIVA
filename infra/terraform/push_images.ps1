# Script para construir y subir las imagenes de Docker a Amazon ECR
param (
    [string]$Region = "us-east-1"
)

$ErrorActionPreference = "Stop"

# Refrescar PATH
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

Write-Host "Obteniendo datos de AWS..." -ForegroundColor Cyan
$AccountId = (aws sts get-caller-identity --query Account --output text).Trim()
$EcrBase = "$AccountId.dkr.ecr.$Region.amazonaws.com"

Write-Host "Iniciando sesion en Amazon ECR..." -ForegroundColor Cyan
aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin $EcrBase

$RepoRoot = (Get-Item $PSScriptRoot).Parent.Parent.FullName

$Services = @(
    @{ Name = "multiplier_api"; Dir = "services\multiplier_api" },
    @{ Name = "pressure_worker"; Dir = "services\pressure_worker" },
    @{ Name = "telemetry_simulator"; Dir = "services\telemetry_simulator" },
    @{ Name = "request_simulator"; Dir = "services\request_simulator" }
)

foreach ($svc in $Services) {
    $Name = $svc.Name
    $ImgName = "ruta-viva/$Name"
    $LocalTag = "${ImgName}:latest"
    $RemoteTag = "${EcrBase}/${ImgName}:latest"
    $ContextPath = Join-Path $RepoRoot $svc.Dir

    Write-Host "`nConstruyendo $LocalTag desde $ContextPath..." -ForegroundColor Yellow
    docker build -t $LocalTag -f "$ContextPath\Dockerfile" "$ContextPath"
    if ($LASTEXITCODE -ne 0) {
        throw "Error al construir la imagen $LocalTag"
    }

    Write-Host "Etiquetando como $RemoteTag..." -ForegroundColor Green
    docker tag $LocalTag $RemoteTag
    if ($LASTEXITCODE -ne 0) {
        throw "Error al etiquetar la imagen $RemoteTag"
    }

    Write-Host "Subiendo a Amazon ECR: $RemoteTag..." -ForegroundColor Green
    docker push $RemoteTag
    if ($LASTEXITCODE -ne 0) {
        throw "Error al subir la imagen $RemoteTag"
    }
}

Write-Host "`nTodas las imagenes se han subido exitosamente a Amazon ECR!" -ForegroundColor Cyan
