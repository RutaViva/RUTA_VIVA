variable "aws_region" {
  type        = string
  description = "Región de AWS para el despliegue"
  default     = "us-east-1"
}

variable "project_name" {
  type        = string
  description = "Nombre base del proyecto"
  default     = "ruta-viva"
}

variable "environment" {
  type        = string
  description = "Entorno (dev, prod-opt)"
  default     = "prod-opt"
}

# --- BASE DE DATOS RDS ---
variable "db_name" {
  type        = string
  description = "Nombre de la base de datos PostgreSQL"
  default     = "rutaviva_db"
}

variable "db_username" {
  type        = string
  description = "Usuario maestro de PostgreSQL"
  default     = "postgres"
}

variable "db_password" {
  type        = string
  description = "Contraseña maestra de PostgreSQL"
  default     = "RutaViva2026SecurePass!"
  sensitive   = true
}

variable "db_instance_class" {
  type        = string
  description = "Tipo de instancia RDS elegible para Capa Gratuita (Free Tier: db.t4g.micro)"
  default     = "db.t4g.micro"
}

# --- CONTROL DE CRÉDITOS: TAREAS ECS ACTIVAS ---
# Pon estos valores en 0 cuando termines de probar o quieras apagar los contenedores y gastar $0.00
variable "desired_tasks_api" {
  type        = number
  description = "Número de tareas para FastAPI multiplier_api (Fargate On-Demand)"
  default     = 2
}

variable "desired_tasks_worker" {
  type        = number
  description = "Número de tareas para pressure_worker (Fargate Spot)"
  default     = 1
}

variable "desired_tasks_telemetry" {
  type        = number
  description = "Número de tareas para telemetry_simulator (Fargate Spot)"
  default     = 1
}

variable "desired_tasks_rabbitmq" {
  type        = number
  description = "Número de tareas para rabbitmq (Fargate On-Demand)"
  default     = 1
}
