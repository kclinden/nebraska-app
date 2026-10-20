locals {
  tables = {
    players  = { suffix = "players", hash = "JerseyNumber", range = "PlayerName", attributes = { JerseyNumber = "N", PlayerName = "S" } }
    schedule = { suffix = "schedule", hash = "GameId", range = null, attributes = { GameId = "N" } }
    users    = { suffix = "users", hash = "Id", range = null, attributes = { Id = "S" } }
  }
  roster = yamldecode(file("${path.module}/../../data/roster.yaml")).players
  games  = yamldecode(file("${path.module}/../../data/schedule.yaml")).games
}

resource "aws_dynamodb_table" "app" {
  for_each     = local.tables
  name         = "${var.cluster_name}-${each.value.suffix}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = each.value.hash
  range_key    = each.value.range

  dynamic "attribute" {
    for_each = each.value.attributes
    content {
      name = attribute.key
      type = attribute.value
    }
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

resource "aws_dynamodb_table_item" "players" {
  for_each = { for index, player in local.roster : tostring(index) => player }

  table_name = aws_dynamodb_table.app["players"].name
  hash_key   = "JerseyNumber"
  range_key  = "PlayerName"
  item = jsonencode({
    JerseyNumber = { N = tostring(each.value.jersey) }
    PlayerName   = { S = each.value.name }
    Name         = { S = each.value.name }
    Position     = { S = each.value.position }
  })
}

resource "aws_dynamodb_table_item" "schedule" {
  for_each = { for game in local.games : tostring(game.game_id) => game }

  table_name = aws_dynamodb_table.app["schedule"].name
  hash_key   = "GameId"
  item = jsonencode({
    GameId   = { N = tostring(each.value.game_id) }
    Date     = { S = each.value.date }
    Opponent = { S = each.value.opponent }
    Location = { S = each.value.location }
    Home     = { BOOL = each.value.home }
  })
}

resource "aws_iam_role" "app" {
  name = "${var.cluster_name}-app"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "pods.eks.amazonaws.com" }
      Action    = ["sts:AssumeRole", "sts:TagSession"]
    }]
  })
}

resource "aws_iam_role_policy" "app" {
  role = aws_iam_role.app.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem", "dynamodb:Scan"]
      Resource = [for table in aws_dynamodb_table.app : table.arn]
    }]
  })
}

resource "aws_iam_role_policy" "app_s3_read_all" {
  count = var.enable_s3_read_all ? 1 : 0
  name  = "${var.cluster_name}-s3-read-all"
  role  = aws_iam_role.app.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ListBuckets"
        Effect   = "Allow"
        Action   = ["s3:ListAllMyBuckets"]
        Resource = "*"
      },
      {
        Sid      = "ListBucketContents"
        Effect   = "Allow"
        Action   = ["s3:GetBucketLocation", "s3:ListBucket"]
        Resource = "arn:${data.aws_partition.current.partition}:s3:::*"
      },
      {
        Sid      = "ReadBucketObjects"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "arn:${data.aws_partition.current.partition}:s3:::*/*"
      }
    ]
  })
}

resource "aws_eks_pod_identity_association" "app" {
  cluster_name    = aws_eks_cluster.main.name
  namespace       = var.namespace
  service_account = "nebraska-app"
  role_arn        = aws_iam_role.app.arn
  depends_on      = [aws_eks_addon.pod_identity, aws_iam_role_policy.app, aws_iam_role_policy.app_s3_read_all]
}