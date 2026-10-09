import copy
from decimal import Decimal
import os
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from admin import register_admin, user_id


class MemoryStore:
    def __init__(self):
        self.records = {}
        self.players = []

    def get_record(self, identity):
        return copy.deepcopy(self.records.get(identity))

    def save_record(self, record):
        self.records[record["Id"]] = copy.deepcopy(record)

    def create_record(self, record):
        if record["Id"] in self.records:
            return False
        self.save_record(record)
        return True

    def list_records(self):
        return copy.deepcopy(list(self.records.values()))

    def list_players(self):
        return self.players

    def list_games(self):
        return [{"GameId": 1, "Opponent": "Ohio"}]

    def add_player(self, jersey, name, position):
        self.delete_player(jersey, name)
        self.players.append({"JerseyNumber": jersey, "Name": name, "Position": position})

    def delete_player(self, jersey, name):
        self.players = [player for player in self.players if (player["JerseyNumber"], player["Name"]) != (jersey, name)]


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "SESSION_SECRET": "test-only-session-signing-key", "ADMIN_PASSWORD": "test-admin-password",
            "VIEWER_PASSWORD": "test-viewer-password", "SESSION_COOKIE_SECURE": "false",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.store = MemoryStore()
        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        register_admin(self.app, self.store, {"ohio": {"Result": "W"}})
        self.app.add_url_rule("/add", "add", lambda: "added", methods=["POST"])
        self.client = self.app.test_client()

    def csrf(self, client, path="/admin/login"):
        response = client.get(path)
        return re.search(r'name="csrf_token" value="([^"]+)"', response.text)[1]

    def login(self, client, username="admin", password="test-admin-password"):
        return client.post("/admin/login", data={"username": username, "password": password,
                                                  "csrf_token": self.csrf(client)})

    def test_login_html_roles_and_csrf(self):
        self.assertEqual(self.client.get("/admin").status_code, 302)
        self.assertEqual(self.client.post("/api/v1/players", json={}).status_code, 401)
        self.assertEqual(self.login(self.client, password="wrong").status_code, 401)
        self.assertEqual(self.login(self.client, "viewer", "test-viewer-password").status_code, 302)
        self.assertEqual(self.client.get("/admin/users").status_code, 403)
        self.assertEqual(self.client.post("/add").status_code, 403)
        self.assertEqual(self.login(self.client).status_code, 302)
        self.assertEqual(self.client.post("/add").status_code, 400)
        token = self.csrf(self.client, "/admin")
        self.assertEqual(self.client.post("/add", data={"csrf_token": token}).status_code, 200)
        self.assertNotIn("test-admin-password", self.client.get("/admin/users").text)

    def test_intentional_api_findings(self):
        self.login(self.client, "viewer", "test-viewer-password")
        created = self.client.post("/api/v1/players", json={"JerseyNumber": 99, "Name": "O'Player", "Position": "QB"})
        self.assertEqual(created.status_code, 201)
        identity = created.json["Id"]
        self.assertEqual(self.client.patch("/api/v1/players/" + identity, json={"Position": "WR"}).status_code, 200)
        self.assertEqual(self.client.delete("/api/v1/players/" + identity).status_code, 204)
        reports = self.client.get("/api/v1/reports").json
        self.assertEqual([report["Id"] for report in reports], ["report-viewer"])
        self.assertEqual(self.client.get("/api/v1/reports/report-admin").status_code, 200)
        metadata = self.client.get("/api/v1/users/me").json
        self.assertIn("InternalNote", metadata)
        self.assertNotIn("PasswordHash", metadata)
        promoted = self.client.patch("/api/v1/users/me", json={"Role": "admin", "PasswordHash": "not-accepted"})
        self.assertEqual(promoted.json["Role"], "admin")
        self.assertEqual(self.client.get("/admin/users").status_code, 200)
        self.assertNotEqual(self.store.get_record(user_id("viewer"))["PasswordHash"], "not-accepted")

    def test_management_reset_disable_and_persistence(self):
        self.login(self.client)
        token = self.csrf(self.client, "/admin/users")
        self.assertEqual(self.client.post("/admin/users", data={"csrf_token": token, "username": "analyst",
                             "password": "analyst-test-password", "role": "viewer"}).status_code, 200)
        analyst = self.app.test_client()
        self.assertEqual(self.login(analyst, "analyst", "analyst-test-password").status_code, 302)
        self.client.post("/admin/users/" + user_id("analyst"), data={"csrf_token": token,
                         "role": "viewer", "active": "on", "password": "analyst-new-password"})
        self.assertEqual(analyst.get("/api/v1/users/me").status_code, 401)
        self.assertEqual(self.login(analyst, "analyst", "analyst-new-password").status_code, 302)
        self.client.post("/admin/users/" + user_id("analyst"), data={"csrf_token": token, "role": "viewer"})
        self.assertEqual(analyst.get("/api/v1/users/me").status_code, 401)
        admin_hash = self.store.get_record(user_id("admin"))["PasswordHash"]
        another_app = Flask("restart")
        register_admin(another_app, self.store, {})
        another_app.test_client().get("/admin/login")
        self.assertEqual(self.store.get_record(user_id("admin"))["PasswordHash"], admin_hash)

    def test_missing_secrets_and_invalid_json(self):
        self.login(self.client)
        self.assertEqual(self.client.post("/api/v1/players", json=[]).status_code, 400)
        self.assertEqual(self.client.get("/api/v1/games/1/stats").json, {"Result": "W"})
        with patch.dict(os.environ, {"ADMIN_PASSWORD": ""}):
            self.assertEqual(self.client.get("/admin/login").status_code, 503)

    def test_api_session_and_openapi(self):
        token = self.client.get("/api/v1/session").json["csrf_token"]
        credentials = {"username": "viewer", "password": "test-viewer-password"}
        self.assertEqual(self.client.post("/api/v1/session", json=credentials).status_code, 400)
        response = self.client.post("/api/v1/session", json=credentials, headers={"X-CSRF-Token": token})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.delete("/api/v1/session", headers={"X-CSRF-Token": response.json["csrf_token"]}).status_code, 204)
        self.assertEqual(self.client.get("/api/v1/users/me").status_code, 401)
        document = self.client.get("/openapi.json").json
        self.assertEqual(document["openapi"], "3.0.3")
        self.assertIn("/api/v1/reports/{id}", document["paths"])

    def test_dynamodb_decimal_version(self):
        self.client.get("/admin/login")
        for record in self.store.records.values():
            if record["Kind"] == "user":
                record["Version"] = Decimal("1")
        self.assertEqual(self.login(self.client).status_code, 302)
        self.assertEqual(self.client.get("/api/v1/users/me").status_code, 200)


if __name__ == "__main__":
    unittest.main()