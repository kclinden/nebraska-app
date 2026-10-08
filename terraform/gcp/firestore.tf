locals {
  roster_data   = yamldecode(file("${path.module}/../../data/roster.yaml"))
  schedule_data = yamldecode(file("${path.module}/../../data/schedule.yaml"))
  players_map = {
    for idx, player in local.roster_data.players :
    format("%03d-%s-%03d", player.jersey, replace(lower(player.name), " ", "-"), idx) => player
  }
  schedule_map = { for game in local.schedule_data.games : tostring(game.game_id) => game }
}

# Firestore database IDs can't be reused right after deletion, so add the random suffix.
resource "google_firestore_database" "app" {
  name                    = "husker-${random_string.suffix.result}"
  location_id             = var.region
  type                    = "FIRESTORE_NATIVE"
  deletion_policy         = "DELETE"
  delete_protection_state = "DELETE_PROTECTION_DISABLED"
}

resource "google_firestore_document" "roster_items" {
  for_each = local.players_map

  database   = google_firestore_database.app.name
  collection = "NebraskaPlayers"
  # Must match FirestoreStore in app/storage.py.
  document_id = "${each.value.jersey}-${sha1(each.value.name)}"

  fields = jsonencode({
    JerseyNumber = { integerValue = tostring(each.value.jersey) }
    Name         = { stringValue = each.value.name }
    Position     = { stringValue = each.value.position }
  })
}

resource "google_firestore_document" "schedule_items" {
  for_each = local.schedule_map

  database    = google_firestore_database.app.name
  collection  = "NebraskaSchedule2026"
  document_id = tostring(each.value.game_id)

  fields = jsonencode({
    GameId   = { integerValue = tostring(each.value.game_id) }
    Date     = { stringValue = each.value.date }
    Opponent = { stringValue = each.value.opponent }
    Location = { stringValue = each.value.location }
    Home     = { booleanValue = each.value.home }
  })
}
