resource "azurerm_container_registry" "app" {
  name                = "crhusker${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = false
}

resource "azurerm_service_plan" "app" {
  name                = "asp-husker-app"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  os_type             = "Linux"
  sku_name            = var.app_service_sku
}

resource "azurerm_linux_web_app" "app" {
  name                = "husker-app-${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  service_plan_id     = azurerm_service_plan.app.id
  https_only          = true

  ftp_publish_basic_authentication_enabled       = false
  webdeploy_publish_basic_authentication_enabled = false

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  site_config {
    always_on                                     = true
    ftps_state                                    = "Disabled"
    minimum_tls_version                           = "1.2"
    health_check_path                             = "/nebraska_football.png"
    health_check_eviction_time_in_min             = 2
    container_registry_use_managed_identity       = true
    container_registry_managed_identity_client_id = azurerm_user_assigned_identity.app.client_id

    application_stack {
      docker_registry_url = "https://${azurerm_container_registry.app.login_server}"
      docker_image_name   = "nebraska-app:${var.image_tag}"
    }
  }

  app_settings = {
    SESSION_SECRET                      = random_password.auth["SESSION_SECRET"].result
    ADMIN_PASSWORD                      = random_password.auth["ADMIN_PASSWORD"].result
    VIEWER_PASSWORD                     = random_password.auth["VIEWER_PASSWORD"].result
    SESSION_COOKIE_SECURE               = "true"
    WEBSITES_PORT                       = "5000"
    WEBSITES_ENABLE_APP_SERVICE_STORAGE = "false"
    STORAGE_BACKEND                     = "azure_table"
    AZURE_STORAGE_TABLE_ENDPOINT        = azurerm_storage_account.data.primary_table_endpoint
    # DefaultAzureCredential needs the client ID to pick the user-assigned identity.
    AZURE_CLIENT_ID = azurerm_user_assigned_identity.app.client_id
  }

  logs {
    detailed_error_messages = true
    failed_request_tracing  = false

    application_logs {
      file_system_level = "Information"
    }

    http_logs {
      file_system {
        retention_in_days = 7
        retention_in_mb   = 35
      }
    }
  }

  depends_on = [azurerm_role_assignment.acr_pull, azurerm_role_assignment.table_data, azurerm_storage_table.users]
}
