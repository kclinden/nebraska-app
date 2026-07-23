from flask import Flask, render_template_string, request, redirect, url_for
import boto3

app = Flask(__name__)
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
table = dynamodb.Table("NebraskaPlayers")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Husker Roster</title>
    <style>
        body { font-family: 'Arial', sans-serif; margin: 40px; background-color: #f9f9f9; text-align: center; }
        h1 { color: #E41C38; }
        .container { max-width: 600px; margin: 0 auto; background: white; padding: 20px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); border-radius: 8px; }
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
        <h1>Nebraska Football Roster</h1>

        <button id="playBtn">Play 8-Bit Hail Varsity</button>

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

    <script>
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
        response = table.scan()
        players = response.get("Items", [])
        players = sorted(players, key=lambda x: int(x["JerseyNumber"]))
        return render_template_string(HTML_TEMPLATE, players=players)
    except Exception as exc:
        return f"Error connecting to DynamoDB: {exc}", 500


@app.route("/add", methods=["POST"])
def add_player():
    jersey = request.form.get("jersey")
    name = request.form.get("name")
    position = request.form.get("position")

    if jersey and name and position:
        table.put_item(
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
        table.delete_item(Key={"JerseyNumber": int(jersey)})
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
