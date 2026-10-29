# --- SECURITY GROUP PARA NAT INSTANCE ---
resource "aws_security_group" "nat" {
  name        = "${var.project_name}-nat-sg"
  description = "Trafico para la NAT Instance"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "Trafico saliente desde subredes privadas"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [aws_vpc.main.cidr_block]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-nat-sg"
  }
}

# --- SECURITY GROUP PARA EL ALB (BALANCEADOR PÚBLICO) ---
resource "aws_security_group" "alb" {
  name        = "${var.project_name}-alb-sg"
  description = "Trafico publico hacia el Application Load Balancer"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP desde cualquier origen"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS desde cualquier origen"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-alb-sg"
  }
}

# --- SECURITY GROUP PARA ECS FARGATE (MICROSERVICIOS) ---
resource "aws_security_group" "ecs_tasks" {
  name        = "${var.project_name}-ecs-tasks-sg"
  description = "Trafico para contenedores Fargate"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Trafico desde el ALB hacia FastAPI (puerto 8000)"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  ingress {
    description = "Comunicacion interna entre microservicios y RabbitMQ"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-ecs-tasks-sg"
  }
}

# --- SECURITY GROUP PARA POSTGRESQL (RDS) ---
resource "aws_security_group" "rds" {
  name        = "${var.project_name}-rds-sg"
  description = "Acceso a PostgreSQL unicamente desde contenedores ECS"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL desde tareas de ECS"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-rds-sg"
  }
}
