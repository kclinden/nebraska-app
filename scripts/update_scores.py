"""Fetch final Nebraska scores from ESPN's public feed and write them to app/scores.json."""
import json
import os
import sys
import urllib.request
from pathlib import Path

NEBRASKA_ESPN_ID = "158"
SEASON = os.environ.get("SEASON", "2026")
URL = (
    "https://site.api.espn.com/apis/site/v2/sports/football/college-football/"
    f"teams/{NEBRASKA_ESPN_ID}/schedule?season={SEASON}"
)
SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary?event={}"
OUTPUT = Path(__file__).resolve().parent.parent / "app" / "scores.json"

STAT_KEYS = [
    "totalYards", "netPassingYards", "rushingYards", "firstDowns",
    "thirdDownEff", "turnovers", "totalPenaltiesYards", "possessionTime",
]


def score_value(competitor):
    score = competitor.get("score")
    if isinstance(score, dict):
        score = score.get("displayValue")
    return int(float(score)) if score not in (None, "") else None


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.load(resp)


def game_stats(event_id):
    summary = fetch_json(SUMMARY_URL.format(event_id))

    by_team = {
        t["team"]["id"]: {s["name"]: s for s in t.get("statistics", [])}
        for t in summary.get("boxscore", {}).get("teams", [])
    }
    ne_stats = by_team.pop(NEBRASKA_ESPN_ID, {})
    opp_stats = next(iter(by_team.values()), {})
    stats = [
        {
            "Label": ne_stats[key]["label"],
            "Nebraska": ne_stats[key]["displayValue"],
            "Opponent": opp_stats.get(key, {}).get("displayValue", "-"),
        }
        for key in STAT_KEYS
        if key in ne_stats
    ]

    leaders = []
    for team in summary.get("leaders", []):
        if team.get("team", {}).get("id") != NEBRASKA_ESPN_ID:
            continue
        for category in team.get("leaders", []):
            if category["name"] in ("passingYards", "rushingYards", "receivingYards") and category.get("leaders"):
                top = category["leaders"][0]
                leaders.append({
                    "Category": category["displayName"],
                    "Player": top["athlete"]["displayName"],
                    "Line": top["displayValue"],
                })
    return stats, leaders


def main():
    data = fetch_json(URL)

    scores = {}
    for event in data.get("events", []):
        comp = event["competitions"][0]
        if not comp.get("status", {}).get("type", {}).get("completed"):
            continue

        nebraska = next(c for c in comp["competitors"] if c["team"]["id"] == NEBRASKA_ESPN_ID)
        opponent = next(c for c in comp["competitors"] if c["team"]["id"] != NEBRASKA_ESPN_ID)
        ne_score, opp_score = score_value(nebraska), score_value(opponent)
        if ne_score is None or opp_score is None:
            continue

        stats, leaders = game_stats(event["id"])

        # Keyed by opponent name to match the Opponent field in schedule.yaml / DynamoDB.
        scores[opponent["team"]["location"].lower()] = {
            "Opponent": opponent["team"]["location"],
            "NebraskaScore": ne_score,
            "OpponentScore": opp_score,
            "Result": "W" if ne_score > opp_score else "L" if ne_score < opp_score else "T",
            "Stats": stats,
            "Leaders": leaders,
        }

    OUTPUT.write_text(json.dumps(scores, indent=2) + "\n")
    print(f"Wrote {len(scores)} final score(s) to {OUTPUT}")
    for s in scores.values():
        print(f"  {s['Result']} {s['NebraskaScore']}-{s['OpponentScore']} vs {s['Opponent']}")


if __name__ == "__main__":
    sys.exit(main())
