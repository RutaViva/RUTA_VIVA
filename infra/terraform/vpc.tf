# --- VPC PRINCIPAL ---
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.project_name}-vpc"
  }
}

# --- SUBREDES (6 SUBREDES EN TOTAL SEGÚN EL PDF) ---
# 2 Públicas (ALB y NAT Instance)
resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.${count.index}.0/24"
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_name}-public-subnet-${count.index + 1}"
  }
}

# 2 Privadas para Aplicación (ECS Tasks, Workers, RabbitMQ)
resource "aws_subnet" "private_app" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.${count.index + 10}.0/24"
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = {
    Name = "${var.project_name}-private-app-subnet-${count.index + 1}"
  }
}

# 2 Privadas para Base de Datos (RDS PostgreSQL 16)
resource "aws_subnet" "private_db" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.${count.index + 20}.0/24"
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = {
    Name = "${var.project_name}-private-db-subnet-${count.index + 1}"
  }
}

# --- INTERNET GATEWAY ---
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.project_name}-igw"
  }
}

# --- S3 GATEWAY ENDPOINT (GRATUITO PARA TRÁFICO MASIVO DE SPARK / DATA LAKE) ---
resource "aws_vpc_endpoint" "s3" {
  vpc_id       = aws_vpc.main.id
  service_name = "com.amazonaws.${var.aws_region}.s3"
  route_table_ids = [
    aws_route_table.public.id,
    aws_route_table.private_app.id
  ]

  tags = {
    Name = "${var.project_name}-s3-gateway-endpoint"
  }
}

# --- EC2 COMPARTIDA: NAT INSTANCE + AIRFLOW/SPARK PARA EL ENTORNO PEQUEÑO ---
data "aws_ami" "amazon_linux_arm" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-arm64"]
  }
}

resource "aws_instance" "nat_instance" {
  ami                         = data.aws_ami.amazon_linux_arm.id
  instance_type               = "t4g.medium"
  subnet_id                   = aws_subnet.public[0].id
  vpc_security_group_ids      = [aws_security_group.nat.id]
  iam_instance_profile        = aws_iam_instance_profile.data_services.name
  source_dest_check           = false # Requerido para enrutar tráfico como NAT
  associate_public_ip_address = true

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  root_block_device {
    volume_size           = 40
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  credit_specification {
    cpu_credits = "standard"
  }

  user_data = <<-EOF
              #!/bin/bash
              set -euxo pipefail
              dnf install -y docker git curl amazon-ssm-agent

              ARCH="$(uname -m)"
              case "$ARCH" in
                aarch64) COMPOSE_ARCH="aarch64" ;;
                *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;;
              esac
              install -d -m 0755 /usr/local/lib/docker/cli-plugins
              curl --fail --location --silent --show-error \
                "https://github.com/docker/compose/releases/download/v2.39.4/docker-compose-linux-$COMPOSE_ARCH" \
                --output /usr/local/lib/docker/cli-plugins/docker-compose
              chmod 0755 /usr/local/lib/docker/cli-plugins/docker-compose

              cat >/etc/sysctl.d/99-ruta-viva-nat.conf <<'SYSCTL'
              net.ipv4.ip_forward=1
              SYSCTL
              sysctl --system

              cat >/usr/local/sbin/ruta-viva-nat-rules <<'SCRIPT'
              #!/bin/bash
              set -euo pipefail
              EXT_IF="$(ip -4 route show default | awk 'NR == 1 {print $5}')"
              test -n "$EXT_IF"
              iptables -t nat -C POSTROUTING -o "$EXT_IF" -j MASQUERADE 2>/dev/null || \
                iptables -t nat -A POSTROUTING -o "$EXT_IF" -j MASQUERADE
              iptables -C DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || \
                iptables -I DOCKER-USER 1 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
              iptables -C DOCKER-USER -i "$EXT_IF" -o "$EXT_IF" -s 10.0.0.0/16 -j ACCEPT 2>/dev/null || \
                iptables -I DOCKER-USER 2 -i "$EXT_IF" -o "$EXT_IF" -s 10.0.0.0/16 -j ACCEPT
              SCRIPT
              chmod 0755 /usr/local/sbin/ruta-viva-nat-rules

              cat >/etc/systemd/system/ruta-viva-nat-rules.service <<'UNIT'
              [Unit]
              Description=RutaViva NAT forwarding rules
              Requires=docker.service
              After=docker.service network-online.target
              Wants=network-online.target

              [Service]
              Type=oneshot
              ExecStart=/usr/local/sbin/ruta-viva-nat-rules
              RemainAfterExit=yes

              [Install]
              WantedBy=multi-user.target
              UNIT

              systemctl enable --now docker
              systemctl enable --now amazon-ssm-agent
              systemctl daemon-reload
              systemctl enable --now ruta-viva-nat-rules.service
              EOF

  user_data_replace_on_change = true

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name = "${var.project_name}-nat-data-services"
  }
}

# --- TABLAS DE ENRUTAMIENTO ---
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }

  tags = {
    Name = "${var.project_name}-public-rt"
  }
}

resource "aws_route_table" "private_app" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block           = "0.0.0.0/0"
    network_interface_id = aws_instance.nat_instance.primary_network_interface_id
  }

  tags = {
    Name = "${var.project_name}-private-app-rt"
  }
}

resource "aws_route_table" "private_db" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.project_name}-private-db-rt"
  }
}

# Asociaciones de Subredes
resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private_app" {
  count          = 2
  subnet_id      = aws_subnet.private_app[count.index].id
  route_table_id = aws_route_table.private_app.id
}

resource "aws_route_table_association" "private_db" {
  count          = 2
  subnet_id      = aws_subnet.private_db[count.index].id
  route_table_id = aws_route_table.private_db.id
}
