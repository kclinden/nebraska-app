"""Create and seed the DynamoDB tables in DynamoDB Local from the shared YAML files in data/.

Point boto3 at the local endpoint with AWS_ENDPOINT_URL_DYNAMODB (e.g. http://localhost:8000).
"""
import os
import time
from pathlib import Path

import boto3
import yaml
from botocore.exceptions import ClientError, EndpointConnectionError

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))

TABLES = {
    "NebraskaPlayers": {
        "KeySchema": [
            {"AttributeName": "JerseyNumber", "KeyType": "HASH"},
            {"AttributeName": "PlayerName", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "JerseyNumber", "AttributeType": "N"},
            {"AttributeName": "PlayerName", "AttributeType": "S"},
        ],
    },
    "NebraskaSchedule2026": {
        "KeySchema": [{"AttributeName": "GameId", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "GameId", "AttributeType": "N"}],
    },
}


def wait_for_dynamodb(client, attempts=30):
    for _ in range(attempts):
        try:
            client.list_tables()
            return
        except EndpointConnectionError:
            time.sleep(1)
    raise SystemExit("DynamoDB Local did not become reachable")


def ensure_tables(client):
    for name, spec in TABLES.items():
        try:
            client.create_table(TableName=name, BillingMode="PAY_PER_REQUEST", **spec)
            client.get_waiter("table_exists").wait(TableName=name)
            print(f"Created table {name}")
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ResourceInUseException":
                raise


def seed(resource):
    roster = yaml.safe_load((DATA_DIR / "roster.yaml").read_text())["players"]
    schedule = yaml.safe_load((DATA_DIR / "schedule.yaml").read_text())["games"]

    with resource.Table("NebraskaPlayers").batch_writer(overwrite_by_pkeys=["JerseyNumber", "PlayerName"]) as batch:
        for p in roster:
            batch.put_item(Item={
                "JerseyNumber": int(p["jersey"]),
                "PlayerName": p["name"],
                "Name": p["name"],
                "Position": p["position"],
            })

    with resource.Table("NebraskaSchedule2026").batch_writer() as batch:
        for g in schedule:
            batch.put_item(Item={
                "GameId": int(g["game_id"]),
                "Date": str(g["date"]),
                "Opponent": g["opponent"],
                "Location": g["location"],
                "Home": bool(g["home"]),
            })

    print(f"Seeded {len(roster)} players and {len(schedule)} games")


if __name__ == "__main__":
    region = os.environ.get("AWS_REGION", "us-east-1")
    client = boto3.client("dynamodb", region_name=region)
    wait_for_dynamodb(client)
    ensure_tables(client)
    seed(boto3.resource("dynamodb", region_name=region))
