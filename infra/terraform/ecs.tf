# --- CLÚSTER ECS ---
resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "disabled" # Deshabilitado para no generar métricas extras que consuman créditos
  }

  tags = {
    Name = "${var.project_name}-cluster"
  }
}

# --- PROVEEDORES DE CAPACIDAD: FARGATE Y FARGATE_SPOT ---
resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 1
  }
}

# --- SERVICE DISCOVERY (DNS PRIVADO PARA COMUNICACIÓN ENTRE CONTENEDORES) ---
resource "aws_service_discovery_private_dns_namespace" "internal" {
  name        = "rutaviva.local"
  description = "DNS privado para microservicios de Ruta Viva"
  vpc         = aws_vpc.main.id
}

resource "aws_service_discovery_service" "rabbitmq_discovery" {
  name = "rabbitmq"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.internal.id

    dns_records {
      ttl  = 10
      type = "A"
    }

    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

# --- CLOUDWATCH LOGS CON RETENCIÓN A 14 DÍAS (OPTIMIZACIÓN DEL PDF) ---
resource "aws_cloudwatch_log_group" "logs" {
  for_each          = toset(local.ecr_services)
  name              = "/ecs/${var.project_name}/${each.key}"
  retention_in_days = 14 # Reduce costo de $38.90 a $6.90/mes

  tags = {
    Name = "${var.project_name}-${each.key}-logs"
  }
}

# --- ROLES IAM PARA ECS ---
data "aws_iam_policy_document" "ecs_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_execution_role" {
  name               = "${var.project_name}-ecs-execution-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task_role" {
  name               = "${var.project_name}-ecs-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
}

# Permisos para que los workers accedan al Data Lake S3
resource "aws_iam_policy" "ecs_s3_policy" {
  name = "${var.project_name}-ecs-s3-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.data_lake.arn,
          "${aws_s3_bucket.data_lake.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_s3" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.ecs_s3_policy.arn
}

# ==============================================================================
# 1. SERVICIO RABBITMQ (Fargate On-Demand: 0.5 vCPU, 1 GB RAM)
# ==============================================================================
resource "aws_ecs_task_definition" "rabbitmq" {
  family                   = "${var.project_name}-rabbitmq"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name      = "rabbitmq"
      image     = "rabbitmq:3.12-management"
      essential = true
      portMappings = [
        { containerPort = 5672, hostPort = 5672 },
        { containerPort = 15672, hostPort = 15672 }
      ]
      environment = [
        { name = "RABBITMQ_DEFAULT_USER", value = "admin" },
        { name = "RABBITMQ_DEFAULT_PASS", value = "admin1234" },
        { name = "RABBITMQ_DEFAULT_VHOST", value = "/" }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/${var.project_name}/rabbitmq"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "rabbitmq" {
  name            = "${var.project_name}-rabbitmq"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.rabbitmq.arn
  desired_count   = var.desired_tasks_rabbitmq

  capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 1
  }

  network_configuration {
    subnets          = aws_subnet.private_app[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.rabbitmq_discovery.arn
  }
}

# ==============================================================================
# 2. MULTIPLIER API (FastAPI On-Demand: 2 tareas 0.25 vCPU, 0.5 GB RAM)
# ==============================================================================
resource "aws_ecs_task_definition" "multiplier_api" {
  family                   = "${var.project_name}-multiplier-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name      = "multiplier_api"
      image     = "${aws_ecr_repository.services["multiplier_api"].repository_url}:latest"
      essential = true
      portMappings = [
        { containerPort = 8000, hostPort = 8000 }
      ]
      environment = [
        { name = "DATABASE_URL", value = "postgresql+psycopg://${var.db_username}:${var.db_password}@${aws_db_instance.postgres.address}:${aws_db_instance.postgres.port}/${var.db_name}" },
        { name = "FRESHNESS_THRESHOLD_SECONDS", value = "300" },
        { name = "AUDITOR_API_KEY", value = "auditor-secret-token" }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/${var.project_name}/multiplier_api"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "multiplier_api" {
  name            = "${var.project_name}-multiplier-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.multiplier_api.arn
  desired_count   = var.desired_tasks_api

  capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 1
  }

  network_configuration {
    subnets          = aws_subnet.private_app[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api_tg.arn
    container_name   = "multiplier_api"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.http]
}

# ==============================================================================
# 3. PRESSURE WORKER (Fargate Spot: 0.5 vCPU, 1 GB RAM - 70% de descuento)
# ==============================================================================
resource "aws_ecs_task_definition" "pressure_worker" {
  family                   = "${var.project_name}-pressure-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name      = "pressure_worker"
      image     = "${aws_ecr_repository.services["pressure_worker"].repository_url}:latest"
      essential = true
      environment = [
        { name = "DATABASE_URL", value = "postgresql+psycopg://${var.db_username}:${var.db_password}@${aws_db_instance.postgres.address}:${aws_db_instance.postgres.port}/${var.db_name}" },
        { name = "RABBITMQ_URL", value = "amqp://admin:admin1234@rabbitmq.rutaviva.local:5672/" },
        { name = "BATCH_SIZE", value = "1000" }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/${var.project_name}/pressure_worker"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "pressure_worker" {
  name            = "${var.project_name}-pressure-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.pressure_worker.arn
  desired_count   = var.desired_tasks_worker

  capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = 1
  }

  network_configuration {
    subnets          = aws_subnet.private_app[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  depends_on = [aws_ecs_service.rabbitmq]
}

# ==============================================================================
# 4. TELEMETRY SIMULATOR (Fargate Spot: 0.5 vCPU, 1 GB RAM)
# ==============================================================================
resource "aws_ecs_task_definition" "telemetry_simulator" {
  family                   = "${var.project_name}-telemetry-simulator"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name      = "telemetry_simulator"
      image     = "${aws_ecr_repository.services["telemetry_simulator"].repository_url}:latest"
      essential = true
      environment = [
        { name = "DATABASE_URL", value = "postgresql+psycopg://${var.db_username}:${var.db_password}@${aws_db_instance.postgres.address}:${aws_db_instance.postgres.port}/${var.db_name}" },
        { name = "RABBITMQ_URL", value = "amqp://admin:admin1234@rabbitmq.rutaviva.local:5672/" },
        { name = "SILENT_VEHICLES_PCT", value = "5.0" },
        { name = "OUT_OF_CITY_PCT", value = "3.0" },
        { name = "DEFECT_DELAY_SECONDS", value = "60" }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/${var.project_name}/telemetry_simulator"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "telemetry_simulator" {
  name            = "${var.project_name}-telemetry-simulator"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.telemetry_simulator.arn
  desired_count   = var.desired_tasks_telemetry

  capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = 1
  }

  network_configuration {
    subnets          = aws_subnet.private_app[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  depends_on = [aws_ecs_service.rabbitmq]
}
