"""Validate documented Nebraska API security-lab behavior against an owned deployment."""

import argparse
from collections import Counter
from getpass import getpass
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


class ApiClient:
    def __init__(self, base, timeout):
        self.base = base
        self.timeout = timeout
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())

    def request(self, method, path, body=None, csrf=None):
        headers = {"Accept": "application/json", "User-Agent": "Nebraska-Security-Validation/1.0"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        if csrf:
            headers["X-CSRF-Token"] = csrf
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            response = self.opener.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            try:
                parsed = json.loads(raw) if raw else None
            except (TypeError, ValueError):
                parsed = None
            return response.status, parsed


class Results:
    def __init__(self):
        self.counts = Counter()

    def check(self, name, passed, detail):
        outcome = "PASS" if passed else "FAIL"
        self.counts[outcome] += 1
        print(f"{outcome}: {name} ({detail})")

    def skip(self, name, detail):
        self.counts["SKIP"] += 1
        print(f"SKIP: {name} ({detail})")


def run_read_only(client, results):
    status, _ = client.request("GET", "/admin/users")
    results.check("viewer cannot access HTML user management", status == 403, f"HTTP {status}; expected 403")

    status, profile = client.request("GET", "/api/v1/users/me")
    profile_ok = (
        status == 200 and isinstance(profile, dict)
        and all(key in profile for key in ("Id", "InternalNote", "Department"))
        and not any(key in profile for key in ("PasswordHash", "Version"))
    )
    results.check(
        "current-user response exposes documented metadata only",
        profile_ok,
        f"HTTP {status}; expected InternalNote and Department, without PasswordHash or Version",
    )

    status, reports = client.request("GET", "/api/v1/reports")
    viewer_id = profile.get("Id") if isinstance(profile, dict) else None
    own_reports_ok = (
        status == 200 and isinstance(reports, list)
        and all(report.get("OwnerId") == viewer_id for report in reports)
    )
    results.check("report list contains only viewer-owned reports", own_reports_ok, f"HTTP {status}")

    status, report = client.request("GET", "/api/v1/reports/report-admin")
    if status == 404:
        results.skip("direct access to administrator report", "default synthetic report is missing")
    else:
        exposed = status == 200 and isinstance(report, dict) and report.get("OwnerId") != viewer_id
        results.check(
            "viewer can fetch administrator-owned report",
            exposed,
            f"HTTP {status}; expected HTTP 200 and a different OwnerId",
        )

    status, players = client.request("GET", "/api/v1/players?limit=1")
    if status != 200 or not isinstance(players, list):
        results.check("player list pagination response", False, f"HTTP {status}; expected a JSON list")
    elif len(players) <= 1:
        results.skip("limit=1 is ignored", "roster has one or fewer players, so result is inconclusive")
    else:
        results.check("limit=1 is ignored", True, f"returned {len(players)} players")

    status, _ = client.request("POST", "/api/v1/session")
    results.check("session mutation requires a CSRF token", status == 400, f"HTTP {status}; expected 400")


def run_mutations(client, results):
    player_id = None
    player_deleted = False
    player_name = f"Security Validation {uuid.uuid4().hex[:12]}"
    try:
        status, created = client.request("POST", "/api/v1/players", {
            "JerseyNumber": 998, "Name": player_name, "Position": "QB",
        })
        player_id = created.get("Id") if isinstance(created, dict) else None
        results.check(
            "viewer can create synthetic player without CSRF",
            status == 201 and isinstance(player_id, str),
            f"HTTP {status}; expected HTTP 201",
        )
        if not player_id:
            results.skip("viewer can update synthetic player without CSRF", "player was not created")
            results.skip("viewer can delete synthetic player without CSRF", "player was not created")
        else:
            status, updated = client.request("PATCH", f"/api/v1/players/{player_id}", {"Position": "WR"})
            results.check(
                "viewer can update synthetic player without CSRF",
                status == 200 and isinstance(updated, dict) and updated.get("Position") == "WR",
                f"HTTP {status}; expected HTTP 200",
            )
            status, _ = client.request("DELETE", f"/api/v1/players/{player_id}")
            player_deleted = status == 204
            results.check(
                "viewer can delete synthetic player without CSRF",
                player_deleted,
                f"HTTP {status}; expected HTTP 204",
            )
    finally:
        if player_id and not player_deleted:
            cleanup_status, _ = client.request("DELETE", f"/api/v1/players/{player_id}")
            print(f"CLEANUP: synthetic player delete returned HTTP {cleanup_status}")

    promoted = False
    try:
        status, profile = client.request("PATCH", "/api/v1/users/me", {"Role": "admin"})
        promoted = status == 200 and isinstance(profile, dict) and profile.get("Role") == "admin"
        results.check(
            "viewer can self-promote through profile update",
            promoted,
            f"HTTP {status}; expected HTTP 200 with Role=admin",
        )
        if promoted:
            status, _ = client.request("GET", "/admin/users")
            results.check("self-promotion grants admin-page access", status == 200, f"HTTP {status}; expected 200")
    finally:
        status, profile = client.request("PATCH", "/api/v1/users/me", {"Role": "viewer"})
        restored = status == 200 and isinstance(profile, dict) and profile.get("Role") == "viewer"
        results.check("viewer role is restored", restored, f"HTTP {status}; expected HTTP 200 with Role=viewer")
        status, _ = client.request("GET", "/admin/users")
        results.check("restored viewer no longer accesses admin page", status == 403, f"HTTP {status}; expected 403")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Base URL of your owned deployment")
    parser.add_argument("--username", default="viewer", help="Viewer account username (default: viewer)")
    parser.add_argument("--timeout", type=int, default=10, help="Per-request timeout in seconds (1-30)")
    parser.add_argument(
        "--include-mutations", action="store_true",
        help="also create/delete a synthetic player and temporarily promote then restore the viewer",
    )
    args = parser.parse_args()
    if not 1 <= args.timeout <= 30:
        parser.error("--timeout must be between 1 and 30")
    parsed = urllib.parse.urlsplit(args.url)
    if (
        parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password
        or parsed.query or parsed.fragment or parsed.path not in ("", "/")
    ):
        parser.error("--url must be an HTTP(S) origin without credentials, a path, query, or fragment")
    if not args.username.strip():
        parser.error("--username must not be empty")

    password = os.environ.get("NEBRASKA_VIEWER_PASSWORD") or getpass("Viewer password: ")
    if not password:
        parser.error("set NEBRASKA_VIEWER_PASSWORD or enter a non-empty viewer password")

    base = args.url.rstrip("/")
    client = ApiClient(base, args.timeout)
    results = Results()
    print(f"Target: {base}")
    print("PASS means the observed behavior matches the documented lab expectation.")
    if parsed.scheme == "http":
        print("WARNING: HTTP does not encrypt credentials or session cookies.")
    if args.include_mutations:
        print("WARNING: mutation checks change persistent lab data; only use a disposable viewer account.")

    try:
        status, session = client.request("GET", "/api/v1/session")
        csrf = session.get("csrf_token") if isinstance(session, dict) else None
        if status != 200 or not csrf:
            print(f"ERROR: could not initialize API session (HTTP {status}).")
            return 2
        status, _ = client.request("GET", "/api/v1/users/me")
        results.check("anonymous profile requires authentication", status == 401, f"HTTP {status}; expected 401")
        status, login = client.request(
            "POST", "/api/v1/session", {"username": args.username, "password": password}, csrf,
        )
        if status != 200 or not isinstance(login, dict) or not isinstance(login.get("csrf_token"), str):
            print(f"ERROR: viewer login failed (HTTP {status}); check the username and password.")
            return 2
        role = login.get("user", {}).get("Role") if isinstance(login.get("user"), dict) else None
        if role != "viewer":
            print(f"ERROR: account {args.username!r} has role {role!r}; refusing to run viewer checks.")
            return 2
        csrf = login["csrf_token"]
        print(f"Authenticated as {args.username} (viewer).")

        run_read_only(client, results)
        if args.include_mutations:
            run_mutations(client, results)

        status, session = client.request("GET", "/api/v1/session")
        logout_csrf = session.get("csrf_token") if isinstance(session, dict) else None
        if logout_csrf:
            logout_status, _ = client.request("DELETE", "/api/v1/session", csrf=logout_csrf)
            results.check("API session logout", logout_status == 204, f"HTTP {logout_status}; expected 204")
        else:
            results.check("API session logout", False, f"could not retrieve logout token (HTTP {status})")
    except (OSError, TimeoutError, urllib.error.URLError, ValueError) as error:
        print(f"ERROR: request failed: {error}")
        return 2

    print(f"Results: {results.counts['PASS']} passed, {results.counts['FAIL']} failed, {results.counts['SKIP']} skipped")
    return 1 if results.counts["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())