"""Cloud-backed accounts, roster/schedule snapshots, and persistent admin overrides."""
import hashlib
import json
import os

PLAYERS_TABLE = "NebraskaPlayers"
SCHEDULE_TABLE = "NebraskaSchedule2026"


def snapshot_json(data):
    payload = json.dumps(data, separators=(",", ":"))
    if len(payload.encode("utf-16-le")) > 60000:
        raise ValueError("Sports snapshot exceeds the portable database property limit")
    return payload


class RecordStore:
    def get_record(self, record_id):
        raise NotImplementedError

    def save_record(self, record):
        raise NotImplementedError

    def list_records(self):
        raise NotImplementedError


class DynamoStore(RecordStore):
    def __init__(self):
        import boto3

        dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        self.players = dynamodb.Table(os.environ.get("DYNAMODB_PLAYERS_TABLE", PLAYERS_TABLE))
        self.schedule = dynamodb.Table(os.environ.get("DYNAMODB_SCHEDULE_TABLE", SCHEDULE_TABLE))
        self.records = dynamodb.Table(os.environ.get("DYNAMODB_USERS_TABLE", "NebraskaUsers"))

    def get_record(self, record_id):
        return self.records.get_item(Key={"Id": record_id}).get("Item")

    def save_record(self, record):
        self.records.put_item(Item=record)

    def create_record(self, record):
        from botocore.exceptions import ClientError

        try:
            self.records.put_item(Item=record, ConditionExpression="attribute_not_exists(Id)")
            return True
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            return False

    def list_records(self):
        response = self.records.scan()
        records = response.get("Items", [])
        while response.get("LastEvaluatedKey"):
            response = self.records.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            records.extend(response.get("Items", []))
        return records

    def list_players(self):
        return [item for item in self.players.scan().get("Items", []) if item.get("Kind") != "sports_snapshot"]

    def list_games(self):
        return [item for item in self.schedule.scan().get("Items", []) if item.get("Kind") != "sports_snapshot"]

    def get_sports_snapshot(self, kind):
        table = self.players if kind == "players" else self.schedule
        key = {"JerseyNumber": -1, "PlayerName": "__espn_snapshot__"} if kind == "players" else {"GameId": -1}
        item = table.get_item(Key=key, ConsistentRead=True).get("Item")
        return json.loads(item["Payload"]) if item else None

    def save_sports_snapshot(self, kind, data):
        table = self.players if kind == "players" else self.schedule
        key = {"JerseyNumber": -1, "PlayerName": "__espn_snapshot__"} if kind == "players" else {"GameId": -1}
        table.put_item(Item=dict(key, Kind="sports_snapshot", Payload=snapshot_json(data)))

    def add_player(self, jersey, name, position):
        self.players.put_item(Item={"JerseyNumber": jersey, "PlayerName": name, "Name": name, "Position": position})

    def delete_player(self, jersey, name):
        self.players.delete_item(Key={"JerseyNumber": jersey, "PlayerName": name})


class AzureTableStore(RecordStore):
    """Players: PartitionKey=jersey, RowKey=sha1(name). Games: PartitionKey=season, RowKey=game id."""

    def __init__(self):
        from azure.data.tables import TableServiceClient
        from azure.identity import DefaultAzureCredential

        service = TableServiceClient(
            endpoint=os.environ["AZURE_STORAGE_TABLE_ENDPOINT"], credential=DefaultAzureCredential()
        )
        self.players = service.get_table_client(PLAYERS_TABLE)
        self.schedule = service.get_table_client(SCHEDULE_TABLE)
        self.records = service.get_table_client("NebraskaUsers")

    def get_record(self, record_id):
        import json
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return json.loads(self.records.get_entity("records", record_id)["Payload"])
        except ResourceNotFoundError:
            return None

    def save_record(self, record):
        import json

        self.records.upsert_entity({
            "PartitionKey": "records", "RowKey": record["Id"], "Payload": json.dumps(record),
        })

    def list_records(self):
        import json

        return [json.loads(record["Payload"]) for record in self.records.list_entities()]

    def create_record(self, record):
        import json
        from azure.core.exceptions import ResourceExistsError

        try:
            self.records.create_entity({"PartitionKey": "records", "RowKey": record["Id"], "Payload": json.dumps(record)})
            return True
        except ResourceExistsError:
            return False

    def list_players(self):
        return [dict(entity) for entity in self.players.list_entities() if entity.get("Kind") != "sports_snapshot"]

    def list_games(self):
        games = []
        for e in self.schedule.list_entities():
            if e.get("Kind") == "sports_snapshot":
                continue
            game = dict(e)
            game["Home"] = str(game.get("Home")).lower() == "true"
            games.append(game)
        return games

    def get_sports_snapshot(self, kind):
        from azure.core.exceptions import ResourceNotFoundError

        table = self.players if kind == "players" else self.schedule
        try:
            entity = table.get_entity("__espn_sync__", "snapshot")
        except ResourceNotFoundError:
            return None
        return json.loads(entity["Payload"])

    def save_sports_snapshot(self, kind, data):
        table = self.players if kind == "players" else self.schedule
        table.upsert_entity({
            "PartitionKey": "__espn_sync__", "RowKey": "snapshot",
            "Kind": "sports_snapshot", "Payload": snapshot_json(data),
        })

    def add_player(self, jersey, name, position):
        self.players.upsert_entity({
            "PartitionKey": str(jersey), "RowKey": _row_key(name),
            "JerseyNumber": str(jersey), "Name": name, "Position": position,
        })

    def delete_player(self, jersey, name):
        self.players.delete_entity(partition_key=str(jersey), row_key=_row_key(name))


def _row_key(name):
    # Matches sha1() in terraform/azure/storage.tf and terraform/gcp/firestore.tf; avoids characters keys can't handle.
    return hashlib.sha1(name.encode()).hexdigest()


class FirestoreStore(RecordStore):
    """Player doc id = '<jersey>-<sha1(name)>'; game doc id = game id."""

    def __init__(self):
        from google.cloud import firestore

        client = firestore.Client(
            project=os.environ.get("GOOGLE_CLOUD_PROJECT"), database=os.environ["FIRESTORE_DATABASE"]
        )
        self.players = client.collection(PLAYERS_TABLE)
        self.schedule = client.collection(SCHEDULE_TABLE)
        self.records = client.collection("NebraskaUsers")

    def get_record(self, record_id):
        return self.records.document(record_id).get().to_dict()

    def save_record(self, record):
        self.records.document(record["Id"]).set(record)

    def list_records(self):
        return [record.to_dict() for record in self.records.stream()]

    def create_record(self, record):
        from google.api_core.exceptions import AlreadyExists

        try:
            self.records.document(record["Id"]).create(record)
            return True
        except AlreadyExists:
            return False

    def list_players(self):
        return [item for document in self.players.stream() if (item := document.to_dict()).get("Kind") != "sports_snapshot"]

    def list_games(self):
        return [item for document in self.schedule.stream() if (item := document.to_dict()).get("Kind") != "sports_snapshot"]

    def get_sports_snapshot(self, kind):
        collection = self.players if kind == "players" else self.schedule
        item = collection.document("espn-snapshot").get().to_dict()
        return json.loads(item["Payload"]) if item else None

    def save_sports_snapshot(self, kind, data):
        collection = self.players if kind == "players" else self.schedule
        collection.document("espn-snapshot").set({"Kind": "sports_snapshot", "Payload": snapshot_json(data)})

    def add_player(self, jersey, name, position):
        self.players.document(f"{jersey}-{_row_key(name)}").set(
            {"JerseyNumber": jersey, "Name": name, "Position": position}
        )

    def delete_player(self, jersey, name):
        self.players.document(f"{jersey}-{_row_key(name)}").delete()


def get_store():
    backend = os.environ.get("STORAGE_BACKEND", "dynamodb")
    if backend == "azure_table":
        store = AzureTableStore()
    elif backend == "firestore":
        store = FirestoreStore()
    else:
        store = DynamoStore()
    source = os.environ.get("SPORTS_DATA_SOURCE", "synced")
    if source == "storage":
        return store
    if source != "synced":
        raise ValueError("SPORTS_DATA_SOURCE must be synced or storage")
    from espn import SyncedSportsStore

    return SyncedSportsStore(store)
