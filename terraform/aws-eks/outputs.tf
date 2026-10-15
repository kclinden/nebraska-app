resource "random_password" "auth" {
  for_each = toset(["SESSION_SECRET", "ADMIN_PASSWORD", "VIEWER_PASSWORD"])
  length   = 40
  special  = false
}

output "cluster_name" {
  value = aws_eks_cluster.main.name
}

output "namespace" {
  value = var.namespace
}

output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "image_tag" {
  value = var.image_tag
}

output "build_local_image" {
  value = var.image_repository == ""
}

output "app_url" {
  value = var.public_alb_enabled ? "${local.alb_tls ? "https" : "http"}://${var.alb_hostname != "" ? var.alb_hostname : aws_lb.app[0].dns_name}" : null
}

output "alb_dns_name" {
  value = var.public_alb_enabled ? aws_lb.app[0].dns_name : null
}

output "bootstrap_passwords" {
  sensitive = true
  value = {
    admin  = random_password.auth["ADMIN_PASSWORD"].result
    viewer = random_password.auth["VIEWER_PASSWORD"].result
  }
}

output "helm_values" {
  sensitive = true
  value = yamlencode({
    image          = { repository = var.image_repository != "" ? var.image_repository : aws_ecr_repository.app.repository_url, tag = var.image_tag, pullPolicy = "Always" }
    serviceAccount = { create = true, name = "nebraska-app" }
    seed           = { enabled = false }
    service        = local.app_service
    dynamodb = {
      enabled              = false
      useStaticCredentials = false
      externalEndpoint     = ""
      region               = var.aws_region
      tables               = { for key, table in aws_dynamodb_table.app : key => table.name }
    }
    auth = {
      sessionSecret  = random_password.auth["SESSION_SECRET"].result
      adminPassword  = random_password.auth["ADMIN_PASSWORD"].result
      viewerPassword = random_password.auth["VIEWER_PASSWORD"].result
      secureCookies  = var.public_alb_enabled && local.alb_tls
    }
  })
}