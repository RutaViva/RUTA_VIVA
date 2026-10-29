output "alb_dns_name" {
  description = "URL publica del Load Balancer para acceder a la API de FastAPI"
  value       = "http://${aws_lb.api_alb.dns_name}"
}

output "rds_endpoint" {
  description = "Endpoint de conexion a PostgreSQL"
  value       = aws_db_instance.postgres.endpoint
}

output "s3_datalake_bucket" {
  description = "Nombre del Bucket S3 para el Data Lake Medallon"
  value       = aws_s3_bucket.data_lake.id
}

output "ecr_repositories" {
  description = "URLs de los repositorios en ECR"
  value       = { for k, v in aws_ecr_repository.services : k => v.repository_url }
}

output "secret_arn" {
  description = "ARN del secreto en AWS Secrets Manager con las credenciales de BD"
  value       = aws_secretsmanager_secret.db_secret.arn
}
