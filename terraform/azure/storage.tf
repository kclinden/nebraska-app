locals {
  roster_data   = yamldecode(file("${path.module}/../../data/roster.yaml"))
  schedule_data = yamldecode(file("${path.module}/../../data/schedule.yaml"))
  players_map = {
    for idx, player in local.roster_data.players :
    format("%03d-%s-%03d", player.jersey, replace(lower(player.name), " ", "-"), idx) => player
  }
  schedule_map = { for game in local.schedule_data.games : tostring(game.game_id) => game }
}

resource "azurerm_storage_account" "data" {
  name                     = "sthusker${random_string.suffix.result}"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
}

resource "azurerm_storage_table" "players" {
  name               = "NebraskaPlayers"
  storage_account_id = azurerm_storage_account.data.id
}

resource "azurerm_storage_table" "schedule" {
  name               = "NebraskaSchedule2026"
  storage_account_id = azurerm_storage_account.data.id
}

resource "azurerm_storage_table_entity" "roster_items" {
  for_each = local.players_map

  storage_table_id = azurerm_storage_table.players.id
  partition_key    = tostring(each.value.jersey)
  # Hashed because the provider fails on keys containing quotes (e.g. D'Onofrio); must match app/storage.py.
  row_key = sha1(each.value.name)

  entity = {
    JerseyNumber = tostring(each.value.jersey)
    Name         = each.value.name
    Position     = each.value.position
  }
}

resource "azurerm_storage_table_entity" "schedule_items" {
  for_each = local.schedule_map

  storage_table_id = azurerm_storage_table.schedule.id
  partition_key    = "2026"
  row_key          = tostring(each.value.game_id)

  entity = {
    GameId   = tostring(each.value.game_id)
    Date     = each.value.date
    Opponent = each.value.opponent
    Location = each.value.location
    Home     = tostring(each.value.home)
  }
}
