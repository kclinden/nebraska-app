resource "google_project_service" "secrets" {
  project            = var.project_id
  service            = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

resource "random_password" "auth" {
  for_each = toset(["SESSION_SECRET", "ADMIN_PASSWORD", "VIEWER_PASSWORD"])
  length   = 40
  special  = false
}

resource "google_secret_manager_secret" "auth" {
  for_each  = random_password.auth
  secret_id = "husker-${lower(replace(each.key, "_", "-"))}"

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  depends_on = [google_project_service.secrets]
}

resource "google_secret_manager_secret_version" "auth" {
  for_each    = random_password.auth
  secret      = google_secret_manager_secret.auth[each.key].id
  secret_data = each.value.result
}

resource "google_secret_manager_secret_iam_member" "auth" {
  for_each  = random_password.auth
  secret_id = google_secret_manager_secret.auth[each.key].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.app.email}"
}

output "bootstrap_passwords" {
  sensitive = true
  value = {
    admin  = random_password.auth["ADMIN_PASSWORD"].result
    viewer = random_password.auth["VIEWER_PASSWORD"].result
  }
}