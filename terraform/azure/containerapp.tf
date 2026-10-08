resource "azurerm_container_registry" "app" {
  name                = "crhusker${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = false
}

resource "azurerm_log_analytics_workspace" "app" {
  name                = "log-husker-app"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_container_app_environment" "app" {
  name                       = "cae-husker-app"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.app.id

  # Azure adds a default Consumption workload profile after creation.
  lifecycle {
    ignore_changes = [workload_profile]
  }
}

resource "azurerm_container_app" "app" {
  name                         = "husker-app"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.app.id
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.app.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  ingress {
    external_enabled = true
    target_port      = 5000

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 1
    max_replicas = 1

    container {
      name   = "husker-app"
      image  = "${azurerm_container_registry.app.login_server}/nebraska-app:${var.image_tag}"
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "STORAGE_BACKEND"
        value = "azure_table"
      }

      env {
        name  = "AZURE_STORAGE_TABLE_ENDPOINT"
        value = azurerm_storage_account.data.primary_table_endpoint
      }

      # DefaultAzureCredential needs the client ID to pick the user-assigned identity.
      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.app.client_id
      }

      liveness_probe {
        transport = "HTTP"
        port      = 5000
        path      = "/nebraska_football.png"
      }
    }
  }

  # `make azure-redeploy` sets a new revision suffix to re-pull :latest; Azure assigns the Consumption profile.
  lifecycle {
    ignore_changes = [template[0].revision_suffix, workload_profile_name]
  }

  depends_on = [azurerm_role_assignment.acr_pull, azurerm_role_assignment.table_data]
}
