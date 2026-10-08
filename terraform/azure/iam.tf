resource "azurerm_role_assignment" "table_data" {
  scope                = azurerm_storage_account.data.id
  role_definition_name = "Storage Table Data Contributor"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

resource "azurerm_role_assignment" "acr_pull" {
  scope                = azurerm_container_registry.app.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# Intentionally overly permissive: blob owner across the whole subscription (mirrors the AWS S3OverlyPermissivePolicy).
resource "azurerm_role_assignment" "blob_overly_permissive" {
  scope                = data.azurerm_subscription.current.id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}
