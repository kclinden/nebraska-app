import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from espn import SyncedSportsStore, parse_games, parse_players, sync_sports
from storage import AzureTableStore, DynamoStore, FirestoreStore, get_store


ROSTER = {"athletes": [{"items": [
    {"id": "10", "jersey": "12", "displayName": "Example Player", "position": {"abbreviation": "QB"}},
    {"id": "11", "jersey": "12", "displayName": "Another Player", "position": {"abbreviation": "DB"}},
    {"id": "12", "displayName": "No Jersey"},
]}]}
SCHEDULE = {"events": [{
    "id": "401858430", "date": "2026-09-05T16:00Z", "competitions": [{
        "neutralSite": False, "venue": {"address": {"city": "Lincoln", "state": "NE"}},
        "competitors": [
            {"homeAway": "home", "team": {"id": "158", "location": "Nebraska"}},
            {"homeAway": "away", "team": {"id": "195", "location": "Ohio"}},
        ],
    }],
}]}


class EspnSyncTests(unittest.TestCase):
    def setUp(self):
        self.backing = Mock()
        self.records = {}
        self.snapshots = {}
        self.backing.list_records.side_effect = lambda: list(self.records.values())
        self.backing.save_record.side_effect = lambda record: self.records.update({record["Id"]: copy.deepcopy(record)})
        self.backing.get_sports_snapshot.side_effect = lambda kind: copy.deepcopy(self.snapshots.get(kind))
        self.backing.save_sports_snapshot.side_effect = lambda kind, data: self.snapshots.update({kind: copy.deepcopy(data)})
        self.backing.list_players.return_value = [{"JerseyNumber": 99, "Name": "Fallback", "Position": "QB"}]
        self.backing.list_games.return_value = [{"GameId": 1, "Opponent": "Fallback"}]
        self.fetch = Mock(side_effect=lambda url: ROSTER if url.endswith("/roster") else SCHEDULE)
        self.store = SyncedSportsStore(self.backing)

    def sync(self):
        return sync_sports(self.store, fetcher=self.fetch, season="2026")

    def test_roster_mapping_and_stable_athlete_ids(self):
        players = parse_players(ROSTER)
        self.assertEqual([player["Name"] for player in players], ["Another Player", "Example Player"])
        self.assertEqual(players[1]["EspnAthleteId"], "10")

    def test_sync_writes_both_collections_and_success_marker(self):
        status = self.sync()
        self.assertEqual(status["PlayerCount"], 2)
        self.assertEqual(status["GameCount"], 1)
        self.assertEqual(self.snapshots["players"], parse_players(ROSTER))
        self.assertEqual(self.snapshots["schedule"], parse_games(SCHEDULE))
        self.assertEqual(self.records["espn-sync-status"], status)

    def test_reads_never_fetch_espn_and_survive_process_restart(self):
        self.sync()
        with patch("espn.fetch_json", side_effect=AssertionError("Read path contacted ESPN")):
            restarted = SyncedSportsStore(self.backing)
            self.assertEqual(len(restarted.list_players()), 2)
            self.assertEqual(restarted.list_games()[0]["Opponent"], "Ohio")
        self.assertEqual(self.fetch.call_count, 2)

    def test_failed_fetch_or_validation_never_changes_database(self):
        self.sync()
        original = copy.deepcopy(self.snapshots)
        marker = copy.deepcopy(self.records["espn-sync-status"])
        for failure in (OSError("offline"), {"events": []}, {}):
            with self.subTest(failure=failure):
                self.backing.save_sports_snapshot.reset_mock()
                self.fetch.side_effect = [ROSTER, failure]
                with self.assertRaises((OSError, ValueError, KeyError)):
                    self.sync()
                self.assertEqual(self.snapshots, original)
                self.assertEqual(self.records["espn-sync-status"], marker)
                self.backing.save_sports_snapshot.assert_not_called()

    def test_database_write_failure_does_not_advance_success_marker(self):
        self.backing.save_sports_snapshot.side_effect = OSError("database unavailable")
        with self.assertRaises(OSError):
            self.sync()
        self.assertNotIn("espn-sync-status", self.records)

    def test_dry_run_does_not_need_database(self):
        status = sync_sports(None, fetcher=self.fetch, season="2026", dry_run=True)
        self.assertEqual(status["PlayerCount"], 2)
        self.assertEqual(self.snapshots, {})

    def test_seeded_data_used_before_first_sync(self):
        self.assertEqual(self.store.list_players(), self.backing.list_players.return_value)
        self.assertEqual(self.store.list_games(), self.backing.list_games.return_value)
        self.fetch.assert_not_called()

    def test_admin_overrides_survive_sync_and_restart(self):
        self.sync()
        self.store.add_player(12, "Example Player", "WR")
        self.store.delete_player(12, "Another Player")
        self.store.add_player(90, "Local Addition", "DL")
        self.sync()
        players = SyncedSportsStore(self.backing).list_players()
        self.assertEqual([player["Name"] for player in players], ["Example Player", "Local Addition"])
        self.assertEqual(players[0]["Position"], "WR")

    def test_removed_espn_players_disappear_only_after_successful_sync(self):
        self.sync()
        reduced = copy.deepcopy(ROSTER)
        reduced["athletes"][0]["items"] = reduced["athletes"][0]["items"][:1]
        self.fetch.side_effect = [reduced, SCHEDULE]
        self.sync()
        self.assertEqual(len(self.store.list_players()), 1)

    def test_schedule_mapping_and_central_date(self):
        game = parse_games(SCHEDULE)[0]
        self.assertEqual(game["EspnEventId"], "401858430")
        self.assertTrue(game["Home"])
        evening = copy.deepcopy(SCHEDULE)
        evening["events"][0]["date"] = "2026-10-18T00:00Z"
        evening["events"][0]["competitions"][0]["neutralSite"] = True
        self.assertEqual(parse_games(evening)[0]["Date"], "2026-10-17")
        self.assertFalse(parse_games(evening)[0]["Home"])

    def test_invalid_season_prevents_fetches_and_writes(self):
        with self.assertRaises(ValueError):
            sync_sports(self.store, fetcher=self.fetch, season="invalid")
        self.fetch.assert_not_called()
        self.backing.save_sports_snapshot.assert_not_called()

    def test_oversized_snapshot_prevents_all_writes(self):
        huge = copy.deepcopy(ROSTER)
        huge["athletes"][0]["items"][0]["displayName"] = "Example" * 10000
        self.fetch.side_effect = [huge, SCHEDULE]
        with self.assertRaises(ValueError):
            self.sync()
        self.backing.save_sports_snapshot.assert_not_called()

    def test_all_cloud_backends_store_snapshots_in_sports_tables(self):
        for store_class in (DynamoStore, AzureTableStore, FirestoreStore):
            with self.subTest(backend=store_class.__name__):
                backend = store_class.__new__(store_class)
                backend.players = Mock()
                backend.schedule = Mock()
                backend.records = Mock()
                snapshots = {}
                for kind in ("players", "schedule"):
                    table = backend.players if kind == "players" else backend.schedule
                    data = parse_players(ROSTER) if kind == "players" else parse_games(SCHEDULE)
                    backend.save_sports_snapshot(kind, data)
                    if store_class is DynamoStore:
                        item = table.put_item.call_args.kwargs["Item"]
                        table.get_item.return_value = {"Item": item}
                    elif store_class is AzureTableStore:
                        item = table.upsert_entity.call_args.args[0]
                        table.get_entity.return_value = item
                    else:
                        item = table.document.return_value.set.call_args.args[0]
                        table.document.return_value.get.return_value.to_dict.return_value = item
                    snapshots[kind] = backend.get_sports_snapshot(kind)
                    self.assertEqual(snapshots[kind], data)
                    if store_class is FirestoreStore:
                        table.document.assert_called_with("espn-snapshot")
                self.assertEqual(backend.records.mock_calls, [])

    def test_factory_defaults_to_database_reads_and_supports_legacy_mode(self):
        for backend, constructor in (("dynamodb", "DynamoStore"), ("azure_table", "AzureTableStore"), ("firestore", "FirestoreStore")):
            with self.subTest(backend=backend), patch.dict("os.environ", {"STORAGE_BACKEND": backend}, clear=True), patch("storage." + constructor, return_value=self.backing):
                self.assertIsInstance(get_store(), SyncedSportsStore)
                with patch.dict("os.environ", {"SPORTS_DATA_SOURCE": "storage"}):
                    self.assertIs(get_store(), self.backing)


if __name__ == "__main__":
    unittest.main()