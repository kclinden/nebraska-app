#!/bin/bash
set -euo pipefail

INSTANCE_TAG_NAME="${1:-Husker-Roster-Webserver}"
AWS_REGION="${AWS_REGION:-us-east-1}"

INSTANCE_ID=$(aws ec2 describe-instances \
  --region "$AWS_REGION" \
  --filters "Name=tag:Name,Values=${INSTANCE_TAG_NAME}" "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' \
  --output text)

if [[ -z "$INSTANCE_ID" || "$INSTANCE_ID" == "None" ]]; then
  echo "No running instance found with tag Name=${INSTANCE_TAG_NAME} in ${AWS_REGION}" >&2
  exit 1
fi

COMMAND_ID=$(aws ssm send-command \
  --region "$AWS_REGION" \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --comment "Update Husker app source from GitHub" \
  --parameters commands='["sudo git config --global --add safe.directory /opt/husker-app/repo || true","sudo /usr/local/bin/update-husker-app"]' \
  --query 'Command.CommandId' \
  --output text)

echo "SSM command sent."
echo "Instance: $INSTANCE_ID"
echo "CommandId: $COMMAND_ID"
echo "Track: aws ssm get-command-invocation --region $AWS_REGION --command-id $COMMAND_ID --instance-id $INSTANCE_ID"
