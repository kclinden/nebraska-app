output "app_url" {
  value = "https://${azurerm_linux_web_app.app.default_hostname}"
}

output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "acr_name" {
  value = azurerm_container_registry.app.name
}

output "web_app_name" {
  value = azurerm_linux_web_app.app.name
}

output "storage_account_name" {
  value = azurerm_storage_account.data.name
}
