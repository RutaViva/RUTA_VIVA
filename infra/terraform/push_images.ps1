# Script para construir y subir las imagenes de Docker a Amazon ECR
param (
    [string]$Region = "us-east-1"
)

$ErrorActionPreference = "Stop"

Write-Host "Obteniendo datos de AWS..." -ForegroundColor Cyan
$AccountId = aws sts get-caller-identity --query Account --output text
$EcrBase = "$AccountId.dkr.ecr.$Region.amazonaws.com"

Write-Host "Iniciando sesion en Amazon ECR..." -ForegroundColor Cyan
aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin $EcrBase

$RepoRoot = (Get-Item $PSScriptRoot).Parent.Parent.FullName

$Services = @(
    @{ Name = "multiplier_api"; Dir = "services/multiplier_api" },
    @{ Name = "pressure_worker"; Dir = "services/pressure_worker" },
    @{ Name = "telemetry_simulator"; Dir = "services/telemetry_simulator" },
    @{ Name = "request_simulator"; Dir = "services/request_simulator" }
)

foreach ($svc in $Services) {
    $ImgName = "ruta-viva/$($svc.Name)"
    $RemoteTag = "$EcrBase/$ImgName:latest"
    $ContextPath = Join-Path $RepoRoot $svc.Dir

    Write-Host "`nConstruyendo $ImgName..." -ForegroundColor Yellow
    docker build -t "$ImgName:latest" -f "$ContextPath/Dockerfile" $RepoRoot

    Write-Host "Etiquetando y subiendo $RemoteTag..." -ForegroundColor Green
    docker tag "$ImgName:latest" $RemoteTag
    docker push $RemoteTag
}

Write-Host "`nTodas las imagenes se han subido exitosamente a Amazon ECR!" -ForegroundColor Cyan
