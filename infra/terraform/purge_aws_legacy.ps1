# ==============================================================================
# Script de purga total de recursos huérfanos/duplicados de RutaViva en AWS
# ==============================================================================
param (
    [string]$Region = "us-east-1"
)

$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

Write-Host "Iniciando purga de recursos huérfanos en región $Region..." -ForegroundColor Cyan

# 1. ECS Services y Cluster
Write-Host "-> Purgando ECS..." -ForegroundColor Yellow
$services = aws ecs list-services --cluster ruta-viva-cluster --region $Region --query "serviceArns" --output json 2>$null | ConvertFrom-Json
if ($services) {
    foreach ($svc in $services) {
        $svcName = $svc.Split('/')[-1]
        Write-Host "   Deteniendo servicio ECS: $svcName"
        aws ecs update-service --cluster ruta-viva-cluster --service $svcName --desired-count 0 --region $Region > $null 2>&1
        aws ecs delete-service --cluster ruta-viva-cluster --service $svcName --force --region $Region > $null 2>&1
    }
}
aws ecs delete-cluster --cluster ruta-viva-cluster --region $Region > $null 2>&1

# 2. Application Load Balancer y Target Groups
Write-Host "-> Purgando ALB..." -ForegroundColor Yellow
$albArn = aws elbv2 describe-load-balancers --names ruta-viva-alb --region $Region --query "LoadBalancers[0].LoadBalancerArn" --output text 2>$null
if ($albArn -and $albArn -ne "None") {
    Write-Host "   Eliminando ALB: ruta-viva-alb"
    aws elbv2 delete-load-balancer --load-balancer-arn $albArn --region $Region > $null 2>&1
    Start-Sleep -Seconds 5
}
$tgArn = aws elbv2 describe-target-groups --names ruta-viva-api-tg --region $Region --query "TargetGroups[0].TargetGroupArn" --output text 2>$null
if ($tgArn -and $tgArn -ne "None") {
    Write-Host "   Eliminando Target Group: ruta-viva-api-tg"
    aws elbv2 delete-target-group --target-group-arn $tgArn --region $Region > $null 2>&1
}

# 3. Instancias EC2
Write-Host "-> Terminando instancias EC2..." -ForegroundColor Yellow
$instances = aws ec2 describe-instances --filters "Name=tag:Project,Values=ruta-viva" "Name=instance-state-name,Values=running,stopped,pending" --region $Region --query "Reservations[*].Instances[*].InstanceId" --output json 2>$null | ConvertFrom-Json
if ($instances) {
    foreach ($inst in $instances) {
        Write-Host "   Terminando EC2: $inst"
        aws ec2 terminate-instances --instance-ids $inst --region $Region > $null 2>&1
    }
}

# 4. RDS PostgreSQL
Write-Host "-> Purgando RDS PostgreSQL..." -ForegroundColor Yellow
aws rds delete-db-instance --db-instance-identifier ruta-viva-postgres --skip-final-snapshot --delete-automated-backups --region $Region > $null 2>&1

# 5. ECR Repositorios
Write-Host "-> Purgando repositorios ECR..." -ForegroundColor Yellow
$repos = @("multiplier_api", "pressure_worker", "telemetry_simulator", "rabbitmq", "request_simulator")
foreach ($r in $repos) {
    aws ecr delete-repository --repository-name "ruta-viva/$r" --force --region $Region > $null 2>&1
}

# 6. CloudWatch Log Groups
Write-Host "-> Purgando Log Groups de CloudWatch..." -ForegroundColor Yellow
foreach ($r in $repos) {
    aws logs delete-log-group --log-group-name "/ecs/ruta-viva/$r" --region $Region > $null 2>&1
}

# 7. Secrets Manager
Write-Host "-> Purgando Secret en Secrets Manager..." -ForegroundColor Yellow
aws secretsmanager delete-secret --secret-id "ruta-viva-db-credentials" --force-delete-without-recovery --region $Region > $null 2>&1

# 8. Roles IAM y Políticas
Write-Host "-> Purgando Roles IAM..." -ForegroundColor Yellow
aws iam remove-role-from-instance-profile --instance-profile-name "ruta-viva-nat-data-services-profile" --role-name "ruta-viva-nat-data-services-role" > $null 2>&1
aws iam delete-instance-profile --instance-profile-name "ruta-viva-nat-data-services-profile" > $null 2>&1

aws iam delete-role-policy --role-name "ruta-viva-nat-data-services-role" --policy-name "ruta-viva-data-services-s3" > $null 2>&1
aws iam detach-role-policy --role-name "ruta-viva-nat-data-services-role" --policy-arn "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore" > $null 2>&1
aws iam delete-role --role-name "ruta-viva-nat-data-services-role" > $null 2>&1

aws iam detach-role-policy --role-name "ruta-viva-ecs-execution-role" --policy-arn "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy" > $null 2>&1
aws iam delete-role --role-name "ruta-viva-ecs-execution-role" > $null 2>&1

$s3PolicyArn = "arn:aws:iam::$((aws sts get-caller-identity --query Account --output text)):policy/ruta-viva-ecs-s3-policy"
aws iam detach-role-policy --role-name "ruta-viva-ecs-task-role" --policy-arn $s3PolicyArn > $null 2>&1
aws iam delete-role --role-name "ruta-viva-ecs-task-role" > $null 2>&1
aws iam delete-policy --policy-arn $s3PolicyArn > $null 2>&1

# 9. S3 Buckets
Write-Host "-> Purgando buckets S3 de Ruta Viva..." -ForegroundColor Yellow
$buckets = aws s3api list-buckets --query "Buckets[?starts_with(Name, 'ruta-viva-datalake')].Name" --output json 2>$null | ConvertFrom-Json
if ($buckets) {
    foreach ($b in $buckets) {
        Write-Host "   Vaciando y eliminando bucket: $b"
        aws s3 rb "s3://$b" --force > $null 2>&1
    }
}

# 10. Service Discovery Namespace
Write-Host "-> Purgando Service Discovery..." -ForegroundColor Yellow
$sdServices = aws servicediscovery list-services --query "Services[?Name=='rabbitmq'].Id" --output json 2>$null | ConvertFrom-Json
if ($sdServices) {
    foreach ($s in $sdServices) {
        aws servicediscovery delete-service --id $s > $null 2>&1
    }
}
$sdNamespaces = aws servicediscovery list-namespaces --query "Namespaces[?Name=='rutaviva.local'].Id" --output json 2>$null | ConvertFrom-Json
if ($sdNamespaces) {
    foreach ($ns in $sdNamespaces) {
        aws servicediscovery delete-namespace --id $ns > $null 2>&1
    }
}

Write-Host "`n✅ Purga inicial completada. (RDS tarda unos minutos en terminar de destruirse)." -ForegroundColor Green
