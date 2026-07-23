# Resolve account ID for parameter ARN construction.
data "aws_caller_identity" "current" {}

#create role
resource "aws_iam_role" "instance_role" {
  name = "ec2-instance-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

#fetch and add AmazonSSMManagedInstanceCore
resource "aws_iam_role_policy_attachment" "attach_ssm" {
  role       = aws_iam_role.instance_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}


# 1. Update the DynamoDB IAM Policy to allow PutItem and DeleteItem
resource "aws_iam_policy" "dynamodb_rw_policy" {
  name        = "EC2DynamoDBReadWriteNebraskaRoster"
  description = "Allows EC2 instance to read/write the NebraskaPlayers DynamoDB table"

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
        Resource = "arn:aws:dynamodb:us-east-1:970547350603:table/NebraskaPlayers"
      }
    ]
  })
}

resource "aws_iam_policy" "app_update_ssm_param_read" {
  name        = "EC2ReadHuskerGithubTokenParameter"
  description = "Allows EC2 to read SSM parameter containing GitHub token for app pulls"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadGithubTokenParameter"
        Effect = "Allow"
        Action = [
          "ssm:GetParameter"
        ]
        Resource = "arn:aws:ssm:us-east-1:${data.aws_caller_identity.current.account_id}:parameter${var.github_token_parameter_name}"
      }
    ]
  })
}

# 2. Attach the Policy to your existing Role
resource "aws_iam_role_policy_attachment" "attach_dynamodb_rw" {
  role       = aws_iam_role.instance_role.name
  policy_arn = aws_iam_policy.dynamodb_rw_policy.arn
}

resource "aws_iam_role_policy_attachment" "attach_app_update_ssm_param_read" {
  role       = aws_iam_role.instance_role.name
  policy_arn = aws_iam_policy.app_update_ssm_param_read.arn
}

# 3. Create an Instance Profile for your existing Role
resource "aws_iam_instance_profile" "ec2_profile" {
  name = "HuskerAppInstanceProfile"
  role = aws_iam_role.instance_role.name
}
