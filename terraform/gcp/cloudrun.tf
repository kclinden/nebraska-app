resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
}

resource "google_artifact_registry_repository" "app" {
  repository_id = "husker-app"
  location      = var.region
  format        = "DOCKER"
  description   = "nebraska-app images copied from GHCR"
}

locals {
  image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.app.repository_id}/nebraska-app:${var.image_tag}"
}

resource "google_cloud_run_v2_service" "app" {
  name                = "husker-app"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false
  # Public site without an allUsers IAM binding (often blocked by domain-restricted sharing).
  invoker_iam_disabled = true

  template {
    service_account = google_service_account.app.email

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    containers {
      image = local.image

      ports {
        container_port = 5000
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name  = "STORAGE_BACKEND"
        value = "firestore"
      }

      env {
        name  = "FIRESTORE_DATABASE"
        value = google_firestore_database.app.name
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "SESSION_COOKIE_SECURE"
        value = "true"
      }
      dynamic "env" {
        for_each = google_secret_manager_secret.auth
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value.secret_id
              version = google_secret_manager_secret_version.auth[env.key].version
            }
          }
        }
      }
    }
  }

  # `make gcp-redeploy` uses gcloud, which stamps client metadata on the service.
  lifecycle {
    ignore_changes = [client, client_version]
  }

  depends_on = [google_project_iam_member.firestore_user, google_secret_manager_secret_iam_member.auth]
}
