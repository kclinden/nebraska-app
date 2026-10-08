terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

# Credentials come from Application Default Credentials (`make gcp-login`).
provider "google" {
  project = var.project_id
  region  = var.region
  # User ADC needs a quota project for the Firestore data API.
  user_project_override = true
  billing_project       = var.project_id

  default_labels = {
    environment = "testing"
    application = "husker-roster-app"
  }
}
