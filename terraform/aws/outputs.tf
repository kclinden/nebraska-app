output "app_url" {
  value = "http://${aws_lb.app.dns_name}"
}

output "aws_region" {
  value = var.aws_region
}

output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.app.name
}

output "ecs_service_name" {
  value = aws_ecs_service.app.name
}
