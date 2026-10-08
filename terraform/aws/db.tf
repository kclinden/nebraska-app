# 1. Read and decode the shared YAML data
locals {
  roster_data   = yamldecode(file("${path.module}/../../data/roster.yaml"))
  schedule_data = yamldecode(file("${path.module}/../../data/schedule.yaml"))
  # Use a stable unique key for for_each while still allowing duplicate jersey numbers.
  players_map = {
    for idx, player in local.roster_data.players :
    format("%03d-%s-%03d", player.jersey, replace(lower(player.name), " ", "-"), idx) => player
  }
  schedule_map = { for game in local.schedule_data.games : tostring(game.game_id) => game }
}

# 2. Define the DynamoDB Table
resource "aws_dynamodb_table" "nebraska_players" {
  name         = "NebraskaPlayers"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "JerseyNumber"
  range_key    = "PlayerName"

  attribute {
    name = "JerseyNumber"
    type = "N"
  }

  attribute {
    name = "PlayerName"
    type = "S"
  }

  # Backups: Enable Point-in-Time Recovery (Required by Wiz/Compliance)
  point_in_time_recovery {
    enabled = true
  }

  # Security: Explicitly enable Server-Side Encryption (Required by Wiz/Compliance)
  server_side_encryption {
    enabled = true
  }

  tags = {
    Environment = "Testing"
    Application = "Husker-Roster-App"
  }
}

resource "aws_dynamodb_table" "nebraska_schedule_2026" {
  name         = "NebraskaSchedule2026"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "GameId"

  attribute {
    name = "GameId"
    type = "N"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Environment = "Testing"
    Application = "Husker-Roster-App"
  }
}

# 3. Loop over the YAML map and create DynamoDB items dynamically
resource "aws_dynamodb_table_item" "roster_items" {
  for_each = local.players_map

  table_name = aws_dynamodb_table.nebraska_players.name
  hash_key   = aws_dynamodb_table.nebraska_players.hash_key
  range_key  = aws_dynamodb_table.nebraska_players.range_key

  item = jsonencode({
    "JerseyNumber" : { "N" : tostring(each.value.jersey) },
    "PlayerName" : { "S" : each.value.name },
    "Name" : { "S" : each.value.name },
    "Position" : { "S" : each.value.position }
  })
}

resource "aws_dynamodb_table_item" "schedule_items" {
  for_each = local.schedule_map

  table_name = aws_dynamodb_table.nebraska_schedule_2026.name
  hash_key   = aws_dynamodb_table.nebraska_schedule_2026.hash_key

  item = jsonencode({
    "GameId" : { "N" : tostring(each.value.game_id) },
    "Date" : { "S" : each.value.date },
    "Opponent" : { "S" : each.value.opponent },
    "Location" : { "S" : each.value.location },
    "Home" : { "BOOL" : each.value.home }
  })
}
