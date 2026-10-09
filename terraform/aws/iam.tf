resource "aws_iam_role" "ecs_execution_role" {
  name = "husker-app-ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Role assumed by the running app container
resource "aws_iam_role" "ecs_task_role" {
  name = "husker-app-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_policy" "dynamodb_rw_policy" {
  name        = "HuskerAppDynamoDBReadWrite"
  description = "Allows the app to read/write the Nebraska DynamoDB tables"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBReadWriteAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:Scan",
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:DeleteItem"
        ]
        Resource = [
          aws_dynamodb_table.nebraska_players.arn,
          aws_dynamodb_table.nebraska_schedule_2026.arn,
          aws_dynamodb_table.users.arn,
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "attach_dynamodb_rw" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.dynamodb_rw_policy.arn
}

#add overlly permissive s3 permissions
resource "aws_iam_policy" "s3_overly_permissive" {
  name        = "S3OverlyPermissivePolicy"
  description = "Grants overly permissive access to all S3 buckets"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "S3FullAccess"
        Effect   = "Allow"
        Action   = "s3:*"
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "attach_s3_overly_permissive" {
  role       = aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.s3_overly_permissive.arn
}
