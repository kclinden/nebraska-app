resource "azurerm_storage_table" "users" {
  name               = "NebraskaUsers"
  storage_account_id = azurerm_storage_account.data.id
}

resource "random_password" "auth" {
  for_each = toset(["SESSION_SECRET", "ADMIN_PASSWORD", "VIEWER_PASSWORD"])
  length   = 40
  special  = false
}

output "bootstrap_passwords" {
  sensitive = true
  value = {
    admin  = random_password.auth["ADMIN_PASSWORD"].result
    viewer = random_password.auth["VIEWER_PASSWORD"].result
  }
}