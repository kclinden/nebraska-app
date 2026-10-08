output "app_url" {
  value = google_cloud_run_v2_service.app.uri
}

output "project_id" {
  value = var.project_id
}

output "region" {
  value = var.region
}

output "image" {
  value = local.image
}

output "service_name" {
  value = google_cloud_run_v2_service.app.name
}

output "firestore_database" {
  value = google_firestore_database.app.name
}
