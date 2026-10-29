# --- SUBREDES PARA LA BASE DE DATOS ---
resource "aws_db_subnet_group" "db" {
  name       = "${var.project_name}-db-subnet-group"
  subnet_ids = aws_subnet.private_db[*].id

  tags = {
    Name = "${var.project_name}-db-subnets"
  }
}

# --- PARAMETER GROUP: POSTGRESQL 16 CON SSL OBLIGATORIO ---
resource "aws_db_parameter_group" "pg16" {
  name   = "${var.project_name}-pg16-params"
  family = "postgres16"

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }

  tags = {
    Name = "${var.project_name}-pg16-params"
  }
}

# --- INSTANCIA RDS POSTGRESQL 16 (OPTIMIZADA: Single-AZ db.t4g.medium 20GB gp3) ---
resource "aws_db_instance" "postgres" {
  identifier             = "${var.project_name}-postgres"
  engine                 = "postgres"
  engine_version         = "16"
  instance_class         = var.db_instance_class
  allocated_storage      = 20
  max_allocated_storage  = 100
  storage_type           = "gp3"
  multi_az               = false # Single-AZ para cumplir presupuesto objetivo ($51.94 vs $523/mes)
  publicly_accessible    = false

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.db.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.pg16.name

  backup_retention_period = 1 # 1 dia (maximo permitido en cuentas Free Tier para no generar cobro)
  skip_final_snapshot     = true
  deletion_protection     = false

  tags = {
    Name = "${var.project_name}-postgres"
  }
}

# --- ALMACENAMIENTO SEGURO DE CREDENCIALES EN SECRETS MANAGER ---
resource "aws_secretsmanager_secret" "db_secret" {
  name                    = "${var.project_name}-db-credentials"
  recovery_window_in_days = 0 # Permite eliminar sin costo acumulado si se destruye el stack
}

resource "aws_secretsmanager_secret_version" "db_secret_val" {
  secret_id = aws_secretsmanager_secret.db_secret.id
  secret_string = jsonencode({
    engine   = "postgres"
    host     = aws_db_instance.postgres.address
    port     = aws_db_instance.postgres.port
    dbname   = var.db_name
    username = var.db_username
    password = var.db_password
    url      = "postgresql+psycopg://${var.db_username}:${var.db_password}@${aws_db_instance.postgres.address}:${aws_db_instance.postgres.port}/${var.db_name}"
  })
}
