provider "aws" {
  region = "us-east-1" # Change to your active region
}

# 1. Read and decode the YAML file
locals {
  roster_data = yamldecode(file("${path.module}/roster.yaml"))
  # Convert the list to a map with the jersey number as the unique key for for_each
  players_map = { for player in local.roster_data.players : tostring(player.jersey) => player }
}

# 2. Define the DynamoDB Table
resource "aws_dynamodb_table" "nebraska_players" {
  name         = "NebraskaPlayers"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "JerseyNumber"

  attribute {
    name = "JerseyNumber"
    type = "N"
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

# 3. Loop over the YAML map and create DynamoDB items dynamically
resource "aws_dynamodb_table_item" "roster_items" {
  for_each = local.players_map

  table_name = aws_dynamodb_table.nebraska_players.name
  hash_key   = aws_dynamodb_table.nebraska_players.hash_key

  item = jsonencode({
    "JerseyNumber" : { "N" : tostring(each.value.jersey) },
    "Name" : { "S" : each.value.name },
    "Position" : { "S" : each.value.position }
  })
}
