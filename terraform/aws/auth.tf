resource "aws_dynamodb_table" "users" {
  name         = "NebraskaUsers"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "Id"

  attribute {
    name = "Id"
    type = "S"
  }
}

resource "random_password" "auth" {
  for_each = toset(["SESSION_SECRET", "ADMIN_PASSWORD", "VIEWER_PASSWORD"])
  length   = 40
  special  = false
}

resource "aws_secretsmanager_secret" "auth" {
  name_prefix             = "husker-auth-"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "auth" {
  secret_id     = aws_secretsmanager_secret.auth.id
  secret_string = jsonencode({ for key, password in random_password.auth : key => password.result })
}

resource "aws_iam_role_policy" "read_auth" {
  role = aws_iam_role.ecs_execution_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "secretsmanager:GetSecretValue"
      Resource = aws_secretsmanager_secret.auth.arn
    }]
  })
}

output "bootstrap_passwords" {
  sensitive = true
  value = {
    admin  = random_password.auth["ADMIN_PASSWORD"].result
    viewer = random_password.auth["VIEWER_PASSWORD"].result
  }
}