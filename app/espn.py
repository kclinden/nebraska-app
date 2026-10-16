"""Synchronize ESPN data into database snapshots; serve only database-backed reads."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import urllib.request
from zoneinfo import ZoneInfo


TEAM_ID = "158"
BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/football/college-football"


def fetch_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Nebraska-App/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def parse_players(payload):
    players = {}
    for group in payload["athletes"]:
        for athlete in group.get("items", []):
            jersey = str(athlete.get("jersey", ""))
            name = athlete.get("displayName")
            if not jersey.isdecimal() or not name:
                continue
            position = (athlete.get("position") or {}).get("abbreviation", "")
            player = {"JerseyNumber": int(jersey), "Name": name, "Position": position, "EspnAthleteId": str(athlete["id"])}
            players[(player["JerseyNumber"], name)] = player
    if not players:
        raise ValueError("ESPN roster has no usable players")
    return sorted(players.values(), key=lambda player: (player["JerseyNumber"], player["Name"]))


def parse_games(payload):
    events = sorted(payload["events"], key=lambda event: (event["date"], event["id"]))
    games = []
    for number, event in enumerate(events, 1):
        competition = event["competitions"][0]
        competitors = competition["competitors"]
        nebraska = next(team for team in competitors if str(team["team"]["id"]) == TEAM_ID)
        opponent = next(team for team in competitors if str(team["team"]["id"]) != TEAM_ID)
        venue = competition.get("venue", {})
        address = venue.get("address", {})
        location = ", ".join(value for value in (address.get("city"), address.get("state")) if value)
        games.append({
            "GameId": number, "EspnEventId": str(event["id"]),
            "Date": datetime.fromisoformat(event["date"].replace("Z", "+00:00")).astimezone(ZoneInfo("America/Chicago")).date().isoformat(),
            "Opponent": opponent["team"]["location"],
            "Location": location or venue.get("fullName", "TBD"),
            "Home": nebraska["homeAway"] == "home" and not competition.get("neutralSite", False),
        })
    if not games:
        raise ValueError("ESPN schedule has no usable games")
    return games


def sync_sports(store, fetcher=None, season=None, dry_run=False):
    fetcher = fetcher or fetch_json
    season = season or os.environ.get("ESPN_SEASON", "2026")
    if not season.isascii() or not season.isdecimal() or len(season) != 4:
        raise ValueError("ESPN_SEASON must be a four-digit year")
    players = parse_players(fetcher(f"{BASE_URL}/teams/{TEAM_ID}/roster"))
    games = parse_games(fetcher(f"{BASE_URL}/teams/{TEAM_ID}/schedule?season={season}"))
    from storage import snapshot_json

    snapshot_json(players)
    snapshot_json(games)
    status = {
        "Id": "espn-sync-status", "Kind": "sports_sync", "Season": season,
        "SyncedAt": datetime.now(timezone.utc).isoformat(),
        "PlayerCount": len(players), "GameCount": len(games),
    }
    if not dry_run:
        store.save_sports_snapshot("players", players)
        store.save_sports_snapshot("schedule", games)
        store.save_record(status)
    return status


class SyncedSportsStore:
    def __init__(self, backing):
        self.backing = backing

    def __getattr__(self, name):
        return getattr(self.backing, name)

    def list_players(self):
        players = self.backing.get_sports_snapshot("players")
        if players is None:
            players = self.backing.list_players()
        merged = {(int(player["JerseyNumber"]), player["Name"]): player for player in players}
        for record in self.backing.list_records():
            if record.get("Kind") != "roster_override":
                continue
            identity = (int(record["JerseyNumber"]), record["Name"])
            if record.get("Deleted"):
                merged.pop(identity, None)
            else:
                merged[identity] = {key: record[key] for key in ("JerseyNumber", "Name", "Position")}
        return sorted(merged.values(), key=lambda player: (int(player["JerseyNumber"]), player["Name"]))

    def list_games(self):
        games = self.backing.get_sports_snapshot("schedule")
        return games if games is not None else self.backing.list_games()

    def save_override(self, jersey, name, position, deleted):
        identity = hashlib.sha256(f"{int(jersey)}:{name}".encode()).hexdigest()
        self.backing.save_record({
            "Id": "roster-" + identity, "Kind": "roster_override", "JerseyNumber": int(jersey),
            "Name": name, "Position": position, "Deleted": deleted,
        })

    def add_player(self, jersey, name, position):
        self.save_override(jersey, name, position, False)

    def delete_player(self, jersey, name):
        self.save_override(jersey, name, "", True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", default=os.environ.get("ESPN_SEASON", "2026"))
    parser.add_argument("--dry-run", action="store_true", help="Validate ESPN feeds without database access or writes")
    args = parser.parse_args()
    from storage import get_store

    status = sync_sports(None if args.dry_run else get_store(), season=args.season, dry_run=args.dry_run)
    print(json.dumps(status))


if __name__ == "__main__":
    main()