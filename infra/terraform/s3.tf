# Generador aleatorio para sufijo único del bucket
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# --- BUCKET DATA LAKE MEDALLÓN ---
resource "aws_s3_bucket" "data_lake" {
  bucket        = "${var.project_name}-datalake-${random_id.bucket_suffix.hex}"
  force_destroy = true

  tags = {
    Name = "${var.project_name}-datalake"
  }
}

# Bloqueo total de acceso público por seguridad
resource "aws_s3_bucket_public_access_block" "block_public" {
  bucket = aws_s3_bucket.data_lake.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Cifrado en reposo por defecto (SSE-S3 sin costo extra de KMS)
resource "aws_s3_bucket_server_side_encryption_configuration" "encryption" {
  bucket = aws_s3_bucket.data_lake.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Estructura de Capas del Data Lake Medallón
resource "aws_s3_object" "bronze_raw" {
  bucket = aws_s3_bucket.data_lake.id
  key    = "raw/"
}

resource "aws_s3_object" "silver" {
  bucket = aws_s3_bucket.data_lake.id
  key    = "silver/"
}

resource "aws_s3_object" "quarantine" {
  bucket = aws_s3_bucket.data_lake.id
  key    = "quarantine/"
}

resource "aws_s3_object" "gold" {
  bucket = aws_s3_bucket.data_lake.id
  key    = "gold/"
}

# --- REGLAS DE CICLO DE VIDA (OPTIMIZACIÓN DE COSTOS DE ALMACENAMIENTO) ---
resource "aws_s3_bucket_lifecycle_configuration" "data_lake_lifecycle" {
  bucket = aws_s3_bucket.data_lake.id

  rule {
    id     = "archive-raw-to-glacier"
    status = "Enabled"

    filter {
      prefix = "raw/"
    }

    transition {
      days          = 90
      storage_class = "GLACIER"
    }
  }

  rule {
    id     = "clean-athena-temp-results"
    status = "Enabled"

    filter {
      prefix = "athena-results/"
    }

    expiration {
      days = 7
    }
  }
}
