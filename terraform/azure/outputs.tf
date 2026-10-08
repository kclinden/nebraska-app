output "app_url" {
  value = "https://${azurerm_container_app.app.ingress[0].fqdn}"
}

output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "acr_name" {
  value = azurerm_container_registry.app.name
}

output "container_app_name" {
  value = azurerm_container_app.app.name
}

output "storage_account_name" {
  value = azurerm_storage_account.data.name
}
