# --- 5 REPOSITORIOS PRIVADOS EN ECR ---
locals {
  ecr_services = [
    "multiplier_api",
    "pressure_worker",
    "telemetry_simulator",
    "rabbitmq",
    "request_simulator"
  ]
}

resource "aws_ecr_repository" "services" {
  for_each             = toset(local.ecr_services)
  name                 = "${var.project_name}/${each.key}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name = "${var.project_name}-${each.key}"
  }
}

# --- POLÍTICA DE RETENCIÓN DE LAS ÚLTIMAS 10 IMÁGENES (EVITA COSTOS EXTRA) ---
resource "aws_ecr_lifecycle_policy" "retention_policy" {
  for_each   = aws_ecr_repository.services
  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Retener solo las ultimas 10 imagenes"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
