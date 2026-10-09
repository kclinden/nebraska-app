import hashlib
import hmac
import os
import secrets
from functools import wraps

from flask import Blueprint, abort, jsonify, redirect, render_template_string, request, session, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash


PAGE = """
<!doctype html>
<html lang="en"><head><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} | Nebraska</title><style>
body { font-family: 'Trebuchet MS', sans-serif; margin: 0; color: #241b1c; background: #fffaf5; }
nav { padding: 16px 24px; background: #a81228; color: white; display: flex; gap: 20px; flex-wrap: wrap; align-items: center; }
nav form { margin: 0; } nav a { overflow-wrap: anywhere; }
nav a { color: white; } main { max-width: 1000px; margin: 24px auto; padding: 0 20px; }
h1 { font-size: 26px; } h2 { font-size: 18px; } table { width: 100%; border-collapse: collapse; } td, th { padding: 10px; border-bottom: 1px solid #ead8cb; text-align: left; }
input, select, button { padding: 8px; font: inherit; max-width: 100%; box-sizing: border-box; }
button { background: #a81228; color: white; border: 0; cursor: pointer; }
form { display: flex; gap: 8px; flex-wrap: wrap; margin: 12px 0; align-items: center; }
label { display: grid; gap: 4px; } .scroll { overflow-x: auto; } .error { color: #a81228; }
</style></head><body>
<nav><a href="/">Nebraska Cornhuskers</a><a href="/admin">Roster</a><a href="/admin/users">Users</a>
{% if user.is_authenticated %}<span>{{ user.record.Username }} ({{ user.record.Role }})</span>
<form method="post" action="/admin/logout"><input type="hidden" name="csrf_token" value="{{ csrf }}"><button>Log out</button></form>{% endif %}</nav>
<main><h1>{{ title }}</h1>{% if error %}<p class="error">{{ error }}</p>{% endif %}
{% if mode == 'login' %}
<form method="post"><input type="hidden" name="csrf_token" value="{{ csrf }}">
<label>Username<input name="username" autocomplete="username" required></label>
<label>Password<input name="password" type="password" autocomplete="current-password" required></label><button>Log in</button></form>
{% elif mode == 'roster' %}
<div class="scroll"><table><tr><th>Jersey</th><th>Name</th><th>Position</th><th></th></tr>
{% for player in players %}<tr><td>{{ player.JerseyNumber }}</td><td>{{ player.Name }}</td><td>{{ player.Position }}</td><td>
{% if user.record.Role == 'admin' %}<form method="post" action="/delete"><input type="hidden" name="csrf_token" value="{{ csrf }}">
<input type="hidden" name="jersey" value="{{ player.JerseyNumber }}"><input type="hidden" name="name" value="{{ player.Name }}"><button>Remove</button></form>{% endif %}</td></tr>{% endfor %}</table></div>
{% if user.record.Role == 'admin' %}<h2>Add Player</h2><form method="post" action="/add"><input type="hidden" name="csrf_token" value="{{ csrf }}">
<label>Jersey<input name="jersey" type="number" min="0" max="999" required></label><label>Name<input name="name" required></label><label>Position<input name="position" required></label><button>Add</button></form>{% endif %}
{% elif mode == 'users' %}
<h2>Create User</h2><form method="post"><input type="hidden" name="csrf_token" value="{{ csrf }}">
<label>Username<input name="username" required></label><label>Initial password<input name="password" type="password" minlength="12" required></label>
<label>Role<select name="role"><option>viewer</option><option>admin</option></select></label><button>Create</button></form>
<div class="scroll"><table><tr><th>Username</th><th>Role</th><th>Status</th><th>Manage</th></tr>
{% for account in accounts %}<tr><td>{{ account.Username }}</td><td>{{ account.Role }}</td><td>{{ 'Active' if account.Active else 'Disabled' }}</td><td>
<form method="post" action="/admin/users/{{ account.Id }}"><input type="hidden" name="csrf_token" value="{{ csrf }}">
<select aria-label="Role" name="role"><option {{ 'selected' if account.Role == 'viewer' }}>viewer</option><option {{ 'selected' if account.Role == 'admin' }}>admin</option></select>
<label><input type="checkbox" name="active" {{ 'checked' if account.Active }}>Active</label>
<input aria-label="Reset password (optional)" name="password" type="password" placeholder="New password" minlength="12"><button>Save</button></form></td></tr>{% endfor %}</table></div>
{% endif %}</main></body></html>
"""


def user_id(username):
    return "user-" + hashlib.sha256(username.strip().lower().encode()).hexdigest()


class Account(UserMixin):
    def __init__(self, record):
        self.record = record
        self.id = record["Id"]

    @property
    def is_active(self):
        return self.record.get("Active", False)


def register_admin(app, store, scores):
    app.config.update(
        SECRET_KEY=os.environ.get("SESSION_SECRET"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true",
    )
    manager = LoginManager(app)
    manager.login_view = "admin.login"
    blueprint = Blueprint("admin", __name__)
    seeded = False

    @app.before_request
    def seed_accounts():
        nonlocal seeded
        if not request.path.startswith(("/admin", "/api/", "/add", "/delete")):
            return
        if not app.secret_key or not os.environ.get("ADMIN_PASSWORD") or not os.environ.get("VIEWER_PASSWORD"):
            return jsonify(error="Admin credentials are not configured"), 503
        if not seeded:
            for username, role, variable in (("admin", "admin", "ADMIN_PASSWORD"), ("viewer", "viewer", "VIEWER_PASSWORD")):
                identity = user_id(username)
                if not store.get_record(identity):
                    store.create_record({
                        "Id": identity, "Kind": "user", "Username": username, "Role": role,
                        "Active": True, "PasswordHash": generate_password_hash(os.environ[variable]),
                        "Version": 1, "Department": "Football operations", "InternalNote": "Synthetic scanner test account",
                    })
                report_id = "report-" + username
                if not store.get_record(report_id):
                    store.create_record({
                        "Id": report_id, "Kind": "report", "OwnerId": identity,
                        "Title": username.title() + " scouting report", "Notes": "Synthetic private scouting data",
                    })
            seeded = True

    @manager.user_loader
    def load_user(identity):
        record = store.get_record(identity)
        if record and record.get("Kind") == "user" and record.get("Active") and session.get("version") == record.get("Version"):
            return Account(record)
        return None

    @manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith("/api/"):
            return jsonify(error="Login required"), 401
        return redirect(url_for("admin.login"))

    def admin_required(function):
        @wraps(function)
        @login_required
        def protected(*args, **kwargs):
            if current_user.record["Role"] != "admin":
                abort(403)
            return function(*args, **kwargs)
        return protected

    def csrf_check():
        token = request.form.get("csrf_token", "")
        if not token or not hmac.compare_digest(token, session.get("csrf_token", "")):
            abort(400, "Invalid CSRF token")

    @app.before_request
    def protect_html_writes():
        if request.method == "POST" and request.path in ("/add", "/delete"):
            if not current_user.is_authenticated:
                return unauthorized()
            if current_user.record["Role"] != "admin":
                abort(403)
            csrf_check()

    def page(title, mode, **context):
        session.setdefault("csrf_token", secrets.token_urlsafe(32))
        return render_template_string(PAGE, title=title, mode=mode, user=current_user,
                                      csrf=session["csrf_token"], **context)

    @blueprint.route("/admin/login", methods=["GET", "POST"])
    def login():
        error = None
        if request.method == "POST":
            csrf_check()
            record = store.get_record(user_id(request.form.get("username", "")))
            if record and record.get("Active") and check_password_hash(record["PasswordHash"], request.form.get("password", "")):
                session.clear()
                session["version"] = int(record["Version"])
                login_user(Account(record))
                return redirect("/admin")
            error = "Invalid username or password"
        return page("Admin Login", "login", error=error), (401 if error else 200)

    @blueprint.post("/admin/logout")
    @login_required
    def logout():
        csrf_check()
        logout_user()
        session.clear()
        return redirect("/")

    @blueprint.get("/admin")
    @login_required
    def roster():
        return page("Roster Administration", "roster", players=store.list_players())

    @blueprint.route("/admin/users", methods=["GET", "POST"])
    @admin_required
    def users():
        error = None
        if request.method == "POST":
            csrf_check()
            username = request.form.get("username", "").strip().lower()
            password = request.form.get("password", "")
            role = request.form.get("role", "viewer")
            if not username or len(username) > 80 or len(password) < 12 or role not in ("admin", "viewer"):
                abort(400)
            created = store.create_record({
                "Id": user_id(username), "Kind": "user", "Username": username, "Role": role,
                "Active": True, "PasswordHash": generate_password_hash(password), "Version": 1,
                "Department": "Football operations", "InternalNote": "Synthetic scanner test account",
            })
            if not created:
                error = "Username already exists"
        accounts = [public_user(record) for record in store.list_records() if record["Kind"] == "user"]
        return page("User Management", "users", accounts=accounts, error=error)

    @blueprint.post("/admin/users/<identity>")
    @admin_required
    def update_user(identity):
        csrf_check()
        record = store.get_record(identity)
        if not record or record["Kind"] != "user":
            abort(404)
        role = request.form.get("role")
        password = request.form.get("password", "")
        if role not in ("admin", "viewer") or (password and len(password) < 12):
            abort(400)
        record.update(Role=role, Active="active" in request.form, Version=int(record["Version"]) + 1)
        if password:
            record["PasswordHash"] = generate_password_hash(password)
        store.save_record(record)
        return redirect("/admin/users")

    @blueprint.get("/api/v1/games")
    def games():
        return jsonify(store.list_games())

    @blueprint.route("/api/v1/session", methods=["GET", "POST", "DELETE"])
    def api_session():
        session.setdefault("csrf_token", secrets.token_urlsafe(32))
        if request.method == "GET":
            return jsonify(csrf_token=session["csrf_token"], authenticated=current_user.is_authenticated)
        token = request.headers.get("X-CSRF-Token", "")
        if not token or not hmac.compare_digest(token, session["csrf_token"]):
            abort(400)
        if request.method == "DELETE":
            logout_user()
            session.clear()
            return "", 204
        body = request.get_json()
        if not isinstance(body, dict) or not isinstance(body.get("username"), str) or not isinstance(body.get("password"), str):
            abort(400)
        record = store.get_record(user_id(body["username"]))
        if not record or not record.get("Active") or not check_password_hash(record["PasswordHash"], body["password"]):
            return jsonify(error="Invalid username or password"), 401
        session.clear()
        session["version"] = int(record["Version"])
        login_user(Account(record))
        session["csrf_token"] = secrets.token_urlsafe(32)
        return jsonify(user=public_user(record), csrf_token=session["csrf_token"])

    @blueprint.get("/api/v1/games/<int:identity>/stats")
    def game_stats(identity):
        game = next((game for game in store.list_games() if int(game["GameId"]) == identity), None)
        if not game:
            abort(404)
        return jsonify(scores.get(game["Opponent"].lower(), {}))

    def player_identity(player):
        return f"{int(player['JerseyNumber'])}-{hashlib.sha1(player['Name'].encode()).hexdigest()}"

    @blueprint.route("/api/v1/players", methods=["GET", "POST"])
    def players():
        if request.method == "GET":
            query = request.args.get("q", "").lower()
            return jsonify([dict(player, Id=player_identity(player)) for player in store.list_players()
                            if query in player["Name"].lower()])
        if not current_user.is_authenticated:
            return unauthorized()
        body = request.get_json()
        try:
            jersey = int(body["JerseyNumber"])
            name, position = body["Name"], body["Position"]
            if not 0 <= jersey <= 999 or not isinstance(name, str) or not name.strip() or not isinstance(position, str):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            abort(400)
        store.add_player(jersey, name, position)
        return jsonify(Id=player_identity({"JerseyNumber": jersey, "Name": name})), 201

    @blueprint.route("/api/v1/players/<identity>", methods=["PATCH", "DELETE"])
    @login_required
    def modify_player(identity):
        player = next((player for player in store.list_players() if player_identity(player) == identity), None)
        if not player:
            abort(404)
        if request.method == "DELETE":
            store.delete_player(int(player["JerseyNumber"]), player["Name"])
            return "", 204
        body = request.get_json()
        position = body.get("Position") if isinstance(body, dict) else None
        if not isinstance(position, str) or not position:
            abort(400)
        store.add_player(int(player["JerseyNumber"]), player["Name"], position)
        return jsonify(dict(player, Position=position, Id=identity))

    @blueprint.route("/api/v1/users/me", methods=["GET", "PATCH"])
    @login_required
    def me():
        record = current_user.record
        if request.method == "PATCH":
            body = request.get_json()
            if not isinstance(body, dict):
                abort(400)
            for key in ("Role", "Department", "InternalNote"):
                if key in body:
                    if not isinstance(body[key], str) or (key == "Role" and body[key] not in ("admin", "viewer")):
                        abort(400)
                    record[key] = body[key]
            store.save_record(record)
        return jsonify(public_user(record))

    @blueprint.get("/api/v1/reports")
    @login_required
    def reports():
        return jsonify([record for record in store.list_records()
                        if record["Kind"] == "report" and record["OwnerId"] == current_user.id])

    @blueprint.get("/api/v1/reports/<identity>")
    @login_required
    def report(identity):
        record = store.get_record(identity)
        if not record or record["Kind"] != "report":
            abort(404)
        return jsonify(record)

    app.register_blueprint(blueprint)

    @app.get("/openapi.json")
    def openapi():
        from api_definition import specification

        return jsonify(specification())

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    def api_error(error):
        if request.path.startswith("/api/"):
            return jsonify(error=error.name), error.code
        return error

    @app.cli.command("seed-users")
    def seed_users():
        with app.test_request_context("/admin/login"):
            result = seed_accounts()
            if result:
                raise RuntimeError("Configure SESSION_SECRET, ADMIN_PASSWORD and VIEWER_PASSWORD")


def public_user(record):
    return {key: value for key, value in record.items() if key not in ("PasswordHash", "Version", "Kind")}