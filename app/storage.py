"""Roster/schedule storage: DynamoDB (AWS and local) or Azure Table Storage, chosen by STORAGE_BACKEND."""
import hashlib
import os

PLAYERS_TABLE = "NebraskaPlayers"
SCHEDULE_TABLE = "NebraskaSchedule2026"


class DynamoStore:
    def __init__(self):
        import boto3

        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        self.players = dynamodb.Table(PLAYERS_TABLE)
        self.schedule = dynamodb.Table(SCHEDULE_TABLE)

    def list_players(self):
        return self.players.scan().get("Items", [])

    def list_games(self):
        return self.schedule.scan().get("Items", [])

    def add_player(self, jersey, name, position):
        self.players.put_item(Item={"JerseyNumber": jersey, "PlayerName": name, "Name": name, "Position": position})

    def delete_player(self, jersey, name):
        self.players.delete_item(Key={"JerseyNumber": jersey, "PlayerName": name})


class AzureTableStore:
    """Players: PartitionKey=jersey, RowKey=sha1(name). Games: PartitionKey=season, RowKey=game id."""

    def __init__(self):
        from azure.data.tables import TableServiceClient
        from azure.identity import DefaultAzureCredential

        service = TableServiceClient(
            endpoint=os.environ["AZURE_STORAGE_TABLE_ENDPOINT"], credential=DefaultAzureCredential()
        )
        self.players = service.get_table_client(PLAYERS_TABLE)
        self.schedule = service.get_table_client(SCHEDULE_TABLE)

    def list_players(self):
        return [dict(e) for e in self.players.list_entities()]

    def list_games(self):
        games = []
        for e in self.schedule.list_entities():
            game = dict(e)
            game["Home"] = str(game.get("Home")).lower() == "true"
            games.append(game)
        return games

    def add_player(self, jersey, name, position):
        self.players.upsert_entity({
            "PartitionKey": str(jersey), "RowKey": _row_key(name),
            "JerseyNumber": str(jersey), "Name": name, "Position": position,
        })

    def delete_player(self, jersey, name):
        self.players.delete_entity(partition_key=str(jersey), row_key=_row_key(name))


def _row_key(name):
    # Matches sha1() in terraform/azure/storage.tf; avoids characters Table Storage keys can't handle.
    return hashlib.sha1(name.encode()).hexdigest()


def get_store():
    if os.environ.get("STORAGE_BACKEND", "dynamodb") == "azure_table":
        return AzureTableStore()
    return DynamoStore()
