resource "google_service_account" "app" {
  account_id   = "husker-app-run"
  display_name = "Husker app Cloud Run runtime"
}

resource "google_project_iam_member" "firestore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.app.email}"
}

# Intentionally overly permissive: full Cloud Storage admin on the project (mirrors the AWS S3OverlyPermissivePolicy).
resource "google_project_iam_member" "storage_overly_permissive" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.app.email}"
}
