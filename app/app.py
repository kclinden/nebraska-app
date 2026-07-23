from flask import Flask, render_template_string, request, redirect, url_for
import boto3

app = Flask(__name__)
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
players_table = dynamodb.Table("NebraskaPlayers")
schedule_table = dynamodb.Table("NebraskaSchedule2026")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Husker Football 2026</title>
    <style>
        body { font-family: 'Arial', sans-serif; margin: 40px; background-color: #f9f9f9; text-align: center; }
        h1 { color: #E41C38; }
        .container { max-width: 900px; margin: 0 auto; background: white; padding: 20px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); border-radius: 8px; }
        table { margin: 20px auto; width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; border: 1px solid #ddd; text-align: left; }
        th { background-color: #E41C38; color: white; }
        tr:nth-child(even) { background-color: #f2f2f2; }
        .form-group { margin: 15px 0; text-align: left; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input[type="text"], input[type="number"] { width: 95%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; }
        button { background-color: #E41C38; color: white; padding: 10px 15px; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; }
        button:hover { background-color: #b31227; }
        .delete-btn { background-color: #555; padding: 5px 10px; font-size: 12px; }
        .delete-btn:hover { background-color: #333; }
        .tabs { display: flex; gap: 10px; justify-content: center; margin: 20px 0; }
        .tab-btn { background-color: #fff; color: #E41C38; border: 2px solid #E41C38; }
        .tab-btn.active { background-color: #E41C38; color: #fff; }
        .tab-panel { display: none; }
        .tab-panel.active { display: block; }

        #playBtn {
            background-color: #000;
            color: #0f0;
            font-family: monospace;
            font-size: 18px;
            border: 2px solid #0f0;
            margin-bottom: 20px;
            box-shadow: 4px 4px 0px #888;
        }
        #playBtn:hover { background-color: #222; }
        #playBtn:active { box-shadow: 2px 2px 0px #888; transform: translate(2px, 2px); }
    </style>
</head>
<body>
    <div class="container">
        <h1>Nebraska Football 2026</h1>

        <button id="playBtn">Play 8-Bit Hail Varsity</button>

        <div class="tabs">
            <button id="rosterTab" class="tab-btn active" type="button">Roster 2026</button>
            <button id="scheduleTab" class="tab-btn" type="button">Schedule 2026</button>
        </div>

        <div id="rosterPanel" class="tab-panel active">
            <table>
                <tr>
                    <th>Jersey #</th>
                    <th>Name</th>
                    <th>Position</th>
                    <th>Actions</th>
                </tr>
                {% for player in players %}
                <tr>
                    <td>{{ player.JerseyNumber }}</td>
                    <td>{{ player.Name }}</td>
                    <td>{{ player.Position }}</td>
                    <td>
                        <form action="/delete" method="POST" style="display:inline;">
                            <input type="hidden" name="jersey" value="{{ player.JerseyNumber }}">
                            <button type="submit" class="delete-btn">Remove</button>
                        </form>
                    </td>
                </tr>
                {% endfor %}
            </table>

            <hr style="border: 0; border-top: 1px solid #eee; margin: 30px 0;">

            <h3>Add New Player</h3>
            <form action="/add" method="POST">
                <div class="form-group">
                    <label for="jersey">Jersey Number:</label>
                    <input type="number" id="jersey" name="jersey" required>
                </div>
                <div class="form-group">
                    <label for="name">Player Name:</label>
                    <input type="text" id="name" name="name" required>
                </div>
                <div class="form-group">
                    <label for="position">Position:</label>
                    <input type="text" id="position" name="position" required>
                </div>
                <button type="submit">Add Player</button>
            </form>
        </div>

        <div id="schedulePanel" class="tab-panel">
            <table>
                <tr>
                    <th>Week</th>
                    <th>Date</th>
                    <th>Opponent</th>
                    <th>Location</th>
                    <th>Type</th>
                </tr>
                {% for game in schedule %}
                <tr>
                    <td>{{ game.GameId }}</td>
                    <td>{{ game.Date }}</td>
                    <td>{{ game.Opponent }}</td>
                    <td>{{ game.Location }}</td>
                    <td>{{ "Home" if game.Home else "Away" }}</td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </div>

    <script>
        const rosterTab = document.getElementById('rosterTab');
        const scheduleTab = document.getElementById('scheduleTab');
        const rosterPanel = document.getElementById('rosterPanel');
        const schedulePanel = document.getElementById('schedulePanel');

        function activateTab(tabName) {
            const showRoster = tabName === 'roster';
            rosterTab.classList.toggle('active', showRoster);
            scheduleTab.classList.toggle('active', !showRoster);
            rosterPanel.classList.toggle('active', showRoster);
            schedulePanel.classList.toggle('active', !showRoster);
        }

        rosterTab.addEventListener('click', () => activateTab('roster'));
        scheduleTab.addEventListener('click', () => activateTab('schedule'));

        document.getElementById('playBtn').addEventListener('click', () => {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            const ctx = new AudioContext();

            const notes = [
                { f: 392.00, d: 250 },
                { f: 523.25, d: 500 },
                { f: 523.25, d: 250 },
                { f: 523.25, d: 500 },
                { f: 392.00, d: 250 },
                { f: 523.25, d: 500 },
                { f: 523.25, d: 250 },
                { f: 523.25, d: 500 }
            ];

            let time = ctx.currentTime;
            notes.forEach(note => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();

                osc.type = 'square';
                osc.frequency.value = note.f;

                osc.connect(gain);
                gain.connect(ctx.destination);

                osc.start(time);
                osc.stop(time + note.d / 1000);

                gain.gain.setValueAtTime(0.05, time);
                gain.gain.exponentialRampToValueAtTime(0.001, time + note.d / 1000);

                time += note.d / 1000 + 0.05;
            });
        });
    </script>
</body>
</html>
"""


@app.route("/")
def index():
    try:
        players_response = players_table.scan()
        players = players_response.get("Items", [])
        players = sorted(players, key=lambda x: int(x["JerseyNumber"]))

        schedule_response = schedule_table.scan()
        schedule = schedule_response.get("Items", [])
        schedule = sorted(schedule, key=lambda x: int(x["GameId"]))

        return render_template_string(HTML_TEMPLATE, players=players, schedule=schedule)
    except Exception as exc:
        return f"Error connecting to DynamoDB: {exc}", 500


@app.route("/add", methods=["POST"])
def add_player():
    jersey = request.form.get("jersey")
    name = request.form.get("name")
    position = request.form.get("position")

    if jersey and name and position:
        players_table.put_item(
            Item={
                "JerseyNumber": int(jersey),
                "Name": name,
                "Position": position,
            }
        )
    return redirect(url_for("index"))


@app.route("/delete", methods=["POST"])
def delete_player():
    jersey = request.form.get("jersey")
    if jersey:
        players_table.delete_item(Key={"JerseyNumber": int(jersey)})
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
