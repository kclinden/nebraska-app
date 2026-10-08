terraform {
  required_version = ">= 1.6"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

# Subscription comes from ARM_SUBSCRIPTION_ID (the Makefile sets it from `az account show`).
provider "azurerm" {
  features {}
  # Providers are registered by `make azure-init`; lab subscriptions often can't register the full set.
  resource_provider_registrations = "none"
}
