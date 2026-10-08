variable "project_id" {
  description = "GCP project to deploy into (the Makefile passes the active gcloud project)"
  type        = string
}

variable "region" {
  description = "Region for Cloud Run, Artifact Registry, and Firestore"
  type        = string
  default     = "us-central1"
}

variable "image_tag" {
  description = "Image tag the Cloud Run service runs"
  type        = string
  default     = "latest"
}
