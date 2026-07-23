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
            background: linear-gradient(180deg, #ef3f4f 0%, #e41c38 60%, #b5122b 100%);
            color: #fff9f0;
            font-family: 'Trebuchet MS', 'Segoe UI', sans-serif;
            font-weight: 700;
            letter-spacing: 0.3px;
            font-size: 18px;
            border: 2px solid #8f0d22;
            margin-bottom: 20px;
            text-shadow: 0 1px 0 #7a0b1c;
            box-shadow: 0 5px 0 #8f0d22, 0 8px 20px rgba(164, 17, 39, 0.35);
            transition: transform 120ms ease, box-shadow 120ms ease, filter 120ms ease;
        }
        #playBtn:hover {
            filter: brightness(1.05);
            transform: translateY(-1px);
            box-shadow: 0 6px 0 #8f0d22, 0 10px 24px rgba(164, 17, 39, 0.4);
        }
        #playBtn:active {
            transform: translateY(3px);
            box-shadow: 0 2px 0 #8f0d22, 0 4px 10px rgba(164, 17, 39, 0.25);
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Nebraska Football 2026</h1>

        <button id="playBtn">Play Hail Varsity</button>

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
                            <input type="hidden" name="name" value="{{ player.Name }}">
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

        const playBtn = document.getElementById('playBtn');
        let activePlayback = null;

        playBtn.addEventListener('click', async () => {
            if (activePlayback) {
                activePlayback.stop();
                activePlayback = null;
                playBtn.textContent = 'Play Hail Varsity';
                return;
            }

            const AudioContext = window.AudioContext || window.webkitAudioContext;
            const ctx = new AudioContext();
            await ctx.resume();

            const tempo = 118;
            const beat = 60 / tempo;
            const H = beat * 0.5;
            const Q = beat;
            const DQ = beat * 1.5;

            const N = {
                E3: 164.81,
                F3: 174.61,
                G3: 196.0,
                A3: 220.0,
                B3: 246.94,
                C4: 261.63,
                D4: 293.66,
                E4: 329.63,
                F4: 349.23,
                G4: 392.0,
                A4: 440.0,
                B4: 493.88,
                C5: 523.25,
                D5: 587.33,
                E5: 659.25
            };

            // Lead phrase approximates Hail Varsity contour with longer playback.
            const lead = [
                [N.G4, Q], [N.B4, Q], [N.C5, Q], [N.B4, Q],
                [N.A4, Q], [N.G4, Q], [N.E4, Q], [N.G4, Q],
                [N.B4, DQ], [N.A4, H], [N.G4, Q], [N.E4, Q],

                [N.G4, Q], [N.B4, Q], [N.C5, Q], [N.D5, Q],
                [N.E5, DQ], [N.D5, H], [N.C5, Q], [N.B4, Q],
                [N.A4, DQ], [N.G4, H], [N.E4, Q], [N.G4, Q],

                [N.A4, Q], [N.B4, Q], [N.C5, Q], [N.B4, Q],
                [N.A4, Q], [N.G4, Q], [N.E4, Q], [N.G4, Q],
                [N.B4, DQ], [N.C5, H], [N.D5, Q], [N.C5, Q],

                [N.B4, Q], [N.A4, Q], [N.G4, DQ], [N.E4, H],
                [N.G4, Q], [N.A4, Q], [N.B4, Q], [N.G4, Q],
                [N.E4, DQ], [N.G4, H], [N.C5, Q], [N.B4, Q],
                [N.A4, Q], [N.G4, DQ]
            ];

            // Bass keeps marching feel under melody.
            const bass = [
                [N.E3, Q], [N.E3, Q], [N.B3, Q], [N.B3, Q],
                [N.C4, Q], [N.C4, Q], [N.G3, Q], [N.G3, Q],
                [N.E3, Q], [N.E3, Q], [N.B3, Q], [N.B3, Q],
                [N.C4, Q], [N.C4, Q], [N.D4, Q], [N.D4, Q],

                [N.E3, Q], [N.E3, Q], [N.B3, Q], [N.B3, Q],
                [N.C4, Q], [N.C4, Q], [N.G3, Q], [N.G3, Q],
                [N.E3, Q], [N.E3, Q], [N.B3, Q], [N.B3, Q],
                [N.C4, Q], [N.C4, Q], [N.D4, Q], [N.D4, Q],

                [N.E3, Q], [N.E3, Q], [N.B3, Q], [N.B3, Q],
                [N.C4, Q], [N.C4, Q], [N.G3, Q], [N.G3, Q],
                [N.E3, Q], [N.E3, Q], [N.B3, Q], [N.B3, Q],
                [N.C4, Q], [N.C4, Q], [N.D4, Q], [N.D4, Q],

                [N.E3, Q], [N.E3, Q], [N.B3, Q], [N.B3, Q],
                [N.C4, Q], [N.C4, Q], [N.G3, Q], [N.G3, Q],
                [N.E3, Q], [N.E3, Q], [N.B3, Q], [N.B3, Q],
                [N.C4, Q], [N.C4, Q], [N.D4, Q], [N.D4, Q]
            ];

            const activeNodes = [];

            function scheduleVoice(sequence, type, volume, startAt, detune = 0) {
                let t = startAt;
                sequence.forEach(([freq, dur]) => {
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();

                    osc.type = type;
                    osc.frequency.value = freq;
                    osc.detune.value = detune;

                    osc.connect(gain);
                    gain.connect(ctx.destination);

                    const attack = Math.min(0.03, dur * 0.2);
                    const release = Math.min(0.1, dur * 0.35);
                    const sustain = Math.max(dur - attack - release, 0.01);
                    const stopAt = t + attack + sustain + release;

                    gain.gain.setValueAtTime(0.0001, t);
                    gain.gain.linearRampToValueAtTime(volume, t + attack);
                    gain.gain.setValueAtTime(volume, t + attack + sustain);
                    gain.gain.exponentialRampToValueAtTime(0.0001, stopAt);

                    osc.start(t);
                    osc.stop(stopAt + 0.01);
                    activeNodes.push({ osc, gain });
                    t += dur;
                });

                return t;
            }

            const startAt = ctx.currentTime + 0.08;
            const endLeadA = scheduleVoice(lead, 'triangle', 0.085, startAt, -4);
            const endLeadB = scheduleVoice(lead, 'sine', 0.04, startAt, 4);
            const endBass = scheduleVoice(bass, 'square', 0.03, startAt, 0);
            const songEndAt = Math.max(endLeadA, endLeadB, endBass);

            playBtn.textContent = 'Stop Hail Varsity';

            const stop = () => {
                const now = ctx.currentTime;
                activeNodes.forEach(({ osc, gain }) => {
                    try {
                        gain.gain.cancelScheduledValues(now);
                        gain.gain.setTargetAtTime(0.0001, now, 0.02);
                        osc.stop(now + 0.05);
                    } catch (e) {
                        // Nodes may already be stopped; ignore.
                    }
                });
                setTimeout(() => {
                    ctx.close().catch(() => {});
                }, 120);
            };

            activePlayback = { stop };

            const msUntilDone = Math.max((songEndAt - ctx.currentTime) * 1000 + 150, 0);
            setTimeout(() => {
                if (activePlayback && activePlayback.stop === stop) {
                    activePlayback = null;
                    playBtn.textContent = 'Play Hail Varsity';
                    ctx.close().catch(() => {});
                }
            }, msUntilDone);
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
        players = sorted(players, key=lambda x: (int(x["JerseyNumber"]), x["Name"]))

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
                "PlayerName": name,
                "Name": name,
                "Position": position,
            }
        )
    return redirect(url_for("index"))


@app.route("/delete", methods=["POST"])
def delete_player():
    jersey = request.form.get("jersey")
    name = request.form.get("name")
    if jersey and name:
        players_table.delete_item(Key={"JerseyNumber": int(jersey), "PlayerName": name})
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
